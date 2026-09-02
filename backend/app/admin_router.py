"""
Administración: dar de alta clientes y habilitarles servicios.

Sin esto, incorporar un cliente es correr SQL a mano: crear su cuenta, mover
sus usuarios y cargar `cuenta_procesos`. Acá está lo mínimo para hacerlo desde
el portal.

Todo cuelga de `admin_actual`, que sólo deja pasar a los correos de
`ADMIN_EMAILS`. Y responde 404 al resto: quien no administra no tiene por qué
enterarse de que esta sección existe.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from .catalogo import CATALOGO
from .cuenta_router import PACKS
from .db import pool
from .dependencias import admin_actual
from .rut import RutInvalido, normalizar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


class CuentaNueva(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    # Opcional al crear: muchas veces la cuenta se abre antes de tener los
    # datos tributarios del cliente. Se completa después.
    rut: str | None = None


class RutCuenta(BaseModel):
    rut: str = Field(min_length=1, max_length=20)


class ProcesoNuevo(BaseModel):
    """Habilita un servicio para una cuenta, apuntando a un proceso del motor."""

    servicio: str
    # Los tres tienen que coincidir con la fila de iagw_proceso del motor, que
    # además debe tener modo_respuesta_default = 'async'.
    tipo_servicio: str
    proceso_codigo: str
    id_proceso: int
    plantilla_id: str | None = None


class MoverUsuario(BaseModel):
    cuenta_id: str


class ResolverRecarga(BaseModel):
    """Lo que se acredita de una recarga declarada, o por qué se rechaza."""

    # El monto REAL, el de la cartola. Puede no ser el que el cliente declaró,
    # y es el único que mueve saldo.
    monto: int | None = None
    nota: str | None = None


class CargaSaldo(BaseModel):
    """Acreditación manual contra un pago recibido fuera del portal."""

    # Positivo acredita; negativo corrige. Sin tope: si el monto se tecleó mal,
    # se arregla con un movimiento negativo, no borrando el anterior.
    monto: int
    # Obligatoria: es lo que permite reconciliar después con la cartola del
    # banco. Un movimiento de plata sin referencia no se puede auditar.
    referencia: str = Field(min_length=1, max_length=200)


class PlantillaNueva(BaseModel):
    servicio: str
    nombre: str = Field(min_length=1, max_length=200)
    columnas: list[dict]


def _mover_saldo(conn, cuenta_id: str, monto: int, tipo: str, detalle: str, admin: dict) -> dict:
    """
    Suma `monto` al saldo de la cuenta y deja el movimiento.

    Compartido por la carga manual y por la aprobación de una recarga: son la
    misma operación con distinto origen, y tenerla en un solo lugar evita que
    una de las dos se olvide de marcar `contratado_en` o de dejar rastro.

    Asume que el llamador ya bloqueó la fila de la cuenta y validó el monto.
    """
    fila = conn.execute(
        """
        update cuentas
           set saldo = saldo + %s,
               contratado_en = case
                   when %s > 0 then coalesce(contratado_en, now())
                   else contratado_en
               end
         where id = %s
         returning saldo, contratado_en
        """,
        (monto, monto, cuenta_id),
    ).fetchone()

    conn.execute(
        """
        insert into movimientos_saldo (cuenta_id, usuario_id, tipo, monto, detalle)
             values (%s, %s, %s, %s, %s)
        """,
        (cuenta_id, admin["id"], tipo, monto, f"{detalle} — por {admin['email']}"),
    )

    return fila


@router.get("/cuentas")
def listar_cuentas(admin: Annotated[dict, Depends(admin_actual)]):
    """Las cuentas con su saldo, cuántos usuarios tienen y qué servicios."""
    with pool.connection() as conn:
        cuentas = conn.execute(
            """
            select c.id, c.nombre, c.rut, c.saldo, c.contratado_en, c.creada_en,
                   (select count(*) from usuarios u where u.cuenta_id = c.id)
                     as usuarios,
                   (select count(*) from solicitudes s where s.cuenta_id = c.id)
                     as solicitudes
              from cuentas c
             order by c.creada_en desc
            """
        ).fetchall()

        procesos = conn.execute(
            """
            select cp.cuenta_id, cp.servicio, cp.tipo_servicio, cp.proceso_codigo,
                   cp.id_proceso, cp.plantilla_id, p.nombre as plantilla
              from cuenta_procesos cp
              left join plantillas_excel p on p.id = cp.plantilla_id
             where cp.activo
             order by cp.servicio
            """
        ).fetchall()

    por_cuenta: dict = {}
    for fila in procesos:
        por_cuenta.setdefault(fila["cuenta_id"], []).append(dict(fila))

    return {
        "cuentas": [
            {**dict(c), "procesos": por_cuenta.get(c["id"], [])} for c in cuentas
        ]
    }


@router.post("/cuentas", status_code=201)
def crear_cuenta(datos: CuentaNueva, admin: Annotated[dict, Depends(admin_actual)]):
    rut = None
    if datos.rut and datos.rut.strip():
        try:
            rut = normalizar(datos.rut)
        except RutInvalido as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    with pool.connection() as conn:
        fila = conn.execute(
            "insert into cuentas (nombre, rut) values (%s, %s) returning id, nombre, rut, saldo",
            (datos.nombre.strip(), rut),
        ).fetchone()

    logger.info("Cuenta creada por %s: %s", admin["email"], datos.nombre)
    return dict(fila)


@router.post("/cuentas/{cuenta_id}/rut")
def fijar_rut(
    cuenta_id: str,
    datos: RutCuenta,
    admin: Annotated[dict, Depends(admin_actual)],
):
    """
    Fija o corrige el RUT de una cuenta.

    Se valida el dígito verificador acá y no en la base: un RUT mal tecleado no
    se descubre hasta que el SII rechaza la factura, y para entonces hay que
    anularla y reemitir.
    """
    try:
        rut = normalizar(datos.rut)
    except RutInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with pool.connection() as conn:
        # El índice único es parcial (sólo donde hay valor), así que el choque
        # se traduce a un mensaje entendible en vez de un error de constraint.
        otra = conn.execute(
            "select nombre from cuentas where rut = %s and id <> %s",
            (rut, cuenta_id),
        ).fetchone()

        if otra is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Ese RUT ya está en la cuenta '{otra['nombre']}'. "
                    "Si son la misma empresa, fusiónalas."
                ),
            )

        fila = conn.execute(
            "update cuentas set rut = %s where id = %s returning id, nombre, rut",
            (rut, cuenta_id),
        ).fetchone()

    if fila is None:
        raise HTTPException(status_code=404, detail="La cuenta no existe")

    logger.info("%s fijó el RUT %s en la cuenta '%s'", admin["email"], rut, fila["nombre"])
    return dict(fila)


@router.post("/cuentas/{cuenta_id}/saldo")
def cargar_saldo(
    cuenta_id: str,
    datos: CargaSaldo,
    admin: Annotated[dict, Depends(admin_actual)],
):
    """
    Acredita saldo a mano, contra un pago recibido fuera del portal.

    Es el flujo de cobro real mientras no exista pasarela: el cliente
    transfiere a la cuenta corriente y acá se registra lo recibido. Hasta ahora
    el saldo sólo se podía cargar desde `/precios`, que acredita sin cobrar
    nada — servía para probar, no para vender.

    Un monto negativo corrige uno anterior. Se permite a propósito: un monto
    mal tecleado hay que poder revertirlo, y borrar el movimiento original
    dejaría el saldo sin explicación. Lo que no se permite es dejar la cuenta
    en negativo.
    """
    referencia = datos.referencia.strip()
    if not referencia:
        raise HTTPException(status_code=422, detail="La referencia es obligatoria")

    if datos.monto == 0:
        raise HTTPException(status_code=422, detail="El monto no puede ser cero")

    with pool.connection() as conn:
        # `for update`: dos acreditaciones simultáneas no pueden leer el mismo
        # saldo y dejar una de las dos sin efecto.
        cuenta = conn.execute(
            "select id, nombre, saldo from cuentas where id = %s for update",
            (cuenta_id,),
        ).fetchone()

        if cuenta is None:
            raise HTTPException(status_code=404, detail="La cuenta no existe")

        if cuenta["saldo"] + datos.monto < 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"El ajuste dejaría el saldo en negativo: la cuenta tiene "
                    f"${cuenta['saldo']:,}"
                ).replace(",", "."),
            )

        fila = _mover_saldo(
            conn,
            cuenta_id,
            datos.monto,
            "carga" if datos.monto > 0 else "ajuste",
            referencia,
            admin,
        )

    logger.info(
        "%s acreditó %s a la cuenta '%s' (ref: %s)",
        admin["email"], datos.monto, cuenta["nombre"], referencia,
    )
    return {"saldo": fila["saldo"], "contratado": fila["contratado_en"] is not None}


@router.post("/cuentas/{cuenta_id}/procesos", status_code=201)
def habilitar_proceso(
    cuenta_id: str,
    datos: ProcesoNuevo,
    admin: Annotated[dict, Depends(admin_actual)],
):
    """
    Habilita un servicio para la cuenta, o reapunta el que ya tenía.

    Con una fila acá, ese servicio le aparece en /enviar y el backend lo acepta.
    Sin ella, ni se le ofrece ni se le acepta.
    """
    # CATALOGO es un dict indexado por id de servicio.
    if datos.servicio not in CATALOGO:
        raise HTTPException(status_code=422, detail=f"Servicio desconocido: {datos.servicio}")

    with pool.connection() as conn:
        if conn.execute("select 1 from cuentas where id = %s", (cuenta_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="La cuenta no existe")

        # Un servicio por cuenta: reasignar el proceso es actualizar el que hay,
        # no acumular filas que se contradigan.
        conn.execute(
            """
            update cuenta_procesos set activo = false
             where cuenta_id = %s and servicio = %s and activo
            """,
            (cuenta_id, datos.servicio),
        )

        fila = conn.execute(
            """
            insert into cuenta_procesos
                   (cuenta_id, servicio, tipo_servicio, proceso_codigo,
                    id_proceso, plantilla_id)
                 values (%s, %s, %s, %s, %s, %s)
              returning id, servicio, proceso_codigo, id_proceso
            """,
            (
                cuenta_id,
                datos.servicio,
                datos.tipo_servicio,
                datos.proceso_codigo,
                datos.id_proceso,
                datos.plantilla_id,
            ),
        ).fetchone()

    logger.info(
        "%s habilitó '%s' en la cuenta %s (proceso %s)",
        admin["email"],
        datos.servicio,
        cuenta_id,
        datos.proceso_codigo,
    )
    return dict(fila)


@router.delete("/cuentas/{cuenta_id}/procesos/{servicio}")
def quitar_proceso(
    cuenta_id: str,
    servicio: str,
    admin: Annotated[dict, Depends(admin_actual)],
):
    """
    Deshabilita un servicio. No borra la fila: se marca inactiva, para que
    quede el rastro de que estuvo habilitado.
    """
    with pool.connection() as conn:
        afectadas = conn.execute(
            """
            update cuenta_procesos set activo = false
             where cuenta_id = %s and servicio = %s and activo
            """,
            (cuenta_id, servicio),
        ).rowcount

    if not afectadas:
        raise HTTPException(status_code=404, detail="Ese servicio no estaba habilitado")

    logger.info("%s quitó '%s' de la cuenta %s", admin["email"], servicio, cuenta_id)
    return {"ok": True}


@router.get("/usuarios")
def listar_usuarios(admin: Annotated[dict, Depends(admin_actual)]):
    """
    Todos los usuarios y a qué cuenta pertenecen.

    Los que entraron por su cuenta quedaron con una propia: acá se ven para
    moverlos a la de su empresa.
    """
    with pool.connection() as conn:
        filas = conn.execute(
            """
            select u.id, u.email, u.nombre, u.cuenta_id, u.creado_en,
                   u.ultimo_acceso_en, c.nombre as cuenta
              from usuarios u
              left join cuentas c on c.id = u.cuenta_id
             order by u.creado_en desc
            """
        ).fetchall()

    return {"usuarios": [dict(f) for f in filas]}


@router.post("/usuarios/{usuario_id}/cuenta")
def mover_usuario(
    usuario_id: str,
    datos: MoverUsuario,
    admin: Annotated[dict, Depends(admin_actual)],
):
    """
    Mueve un usuario a otra cuenta: es como se junta a varias personas de la
    misma empresa bajo un mismo saldo.

    La cuenta que deja no se borra aunque quede vacía: puede tener expedientes
    y movimientos de saldo colgando.
    """
    with pool.connection() as conn:
        if (
            conn.execute("select 1 from cuentas where id = %s", (datos.cuenta_id,)).fetchone()
            is None
        ):
            raise HTTPException(status_code=404, detail="La cuenta destino no existe")

        afectadas = conn.execute(
            "update usuarios set cuenta_id = %s where id = %s",
            (datos.cuenta_id, usuario_id),
        ).rowcount

    if not afectadas:
        raise HTTPException(status_code=404, detail="El usuario no existe")

    logger.info("%s movió al usuario %s a la cuenta %s", admin["email"], usuario_id, datos.cuenta_id)
    return {"ok": True}


class Fusion(BaseModel):
    origen_id: str


@router.post("/cuentas/{destino_id}/fusionar")
def fusionar_cuenta(
    destino_id: str,
    datos: Fusion,
    admin: Annotated[dict, Depends(admin_actual)],
):
    """
    Traspasa todo de una cuenta a otra y deja la origen vacía.

    Mover un usuario no mueve su saldo ni su historial: quedan en la cuenta que
    deja. Esto es lo que hace falta para consolidar de verdad — típicamente
    cuando alguien entró por su cuenta, acumuló saldo y expedientes, y después
    hay que juntarlo con la cuenta de su empresa.

    Se traspasan usuarios, saldo, la marca de contratación, solicitudes,
    documentos (por cascada) y movimientos. Todo en una transacción: o se
    mueve todo, o no se mueve nada.

    La cuenta origen queda en cero pero no se borra: es el rastro de que
    existió, y borrarla dejaría los movimientos sin referencia.
    """
    if destino_id == datos.origen_id:
        raise HTTPException(status_code=422, detail="No se puede fusionar una cuenta consigo misma")

    with pool.connection() as conn:
        cuentas_halladas = conn.execute(
            "select id, nombre, saldo from cuentas where id in (%s, %s)",
            (destino_id, datos.origen_id),
        ).fetchall()

        if len(cuentas_halladas) != 2:
            raise HTTPException(status_code=404, detail="Alguna de las dos cuentas no existe")

        origen = next(c for c in cuentas_halladas if str(c["id"]) == str(datos.origen_id))
        # Se copian antes de tocar nada: lo que se informa al final tiene que
        # ser lo que había, no lo que quedó.
        nombre_origen = origen["nombre"]
        saldo_origen = origen["saldo"]

        # El saldo se suma al destino y la origen queda en cero. En una sola
        # sentencia cada una: si algo falla, la transacción no deja plata
        # duplicada ni perdida.
        conn.execute(
            "update cuentas set saldo = saldo + %s where id = %s",
            (saldo_origen, destino_id),
        )
        conn.execute("update cuentas set saldo = 0 where id = %s", (datos.origen_id,))

        # `contratado_en` viaja con el saldo. Es la marca de que la cuenta
        # alguna vez cargó, y es lo que decide si el usuario ve el panel o la
        # pantalla de contratación: sin esto, la destino recibe la plata pero
        # sigue pareciendo nueva y se le pide contratar teniendo saldo.
        # Se queda la fecha más antigua de las dos, que es cuando el cliente
        # cargó por primera vez.
        conn.execute(
            """
            update cuentas d
               set contratado_en = least(
                       coalesce(d.contratado_en, o.contratado_en),
                       coalesce(o.contratado_en, d.contratado_en))
              from cuentas o
             where d.id = %s
               and o.id = %s
               and o.contratado_en is not null
            """,
            (destino_id, datos.origen_id),
        )

        conn.execute(
            "update usuarios set cuenta_id = %s where cuenta_id = %s",
            (destino_id, datos.origen_id),
        )
        # Los documentos cuelgan de las solicitudes, así que se mueven con ellas.
        solicitudes = conn.execute(
            "update solicitudes set cuenta_id = %s where cuenta_id = %s",
            (destino_id, datos.origen_id),
        ).rowcount
        conn.execute(
            "update movimientos_saldo set cuenta_id = %s where cuenta_id = %s",
            (destino_id, datos.origen_id),
        )

        # Los servicios habilitados NO se traspasan: apuntan a procesos del
        # motor que pueden no corresponder al cliente destino. Se habilitan a
        # mano, que además obliga a revisar qué proceso es el correcto.
        conn.execute(
            "update cuenta_procesos set activo = false where cuenta_id = %s",
            (datos.origen_id,),
        )

    logger.info(
        "%s fusionó '%s' ($%s, %s solicitudes) en la cuenta %s",
        admin["email"],
        nombre_origen,
        saldo_origen,
        solicitudes,
        destino_id,
    )
    return {
        "ok": True,
        "saldo_traspasado": saldo_origen,
        "solicitudes_traspasadas": solicitudes,
    }


@router.get("/recargas")
def listar_recargas(admin: Annotated[dict, Depends(admin_actual)]):
    """
    Las recargas por verificar, más las últimas resueltas.

    Las pendientes son la bandeja de trabajo: hay que buscar cada una en la
    cartola. Las resueltas van para poder mirar atrás sin ir a la base.
    """
    with pool.connection() as conn:
        filas = conn.execute(
            """
            select r.id, r.estado, r.pack_id, r.monto_declarado, r.referencia,
                   r.monto_acreditado, r.nota, r.creada_en, r.resuelta_en, r.resuelta_por,
                   c.id as cuenta_id, c.nombre as cuenta, c.rut as cuenta_rut,
                   u.email as declarada_por
              from recargas r
              join cuentas c on c.id = r.cuenta_id
              join usuarios u on u.id = r.usuario_id
             order by (r.estado = 'pendiente') desc, r.creada_en desc
             limit 50
            """
        ).fetchall()

    # El bono del pack lo pone el servidor, así que se calcula acá y no en la
    # pantalla: es lo que se va a acreditar de más si el monto declarado calza.
    recargas = []
    for f in filas:
        fila = dict(f)
        pack = PACKS.get(fila["pack_id"] or "")
        fila["bonus"] = pack["bonus"] if pack else 0
        fila["sugerido"] = fila["monto_declarado"] + fila["bonus"]
        recargas.append(fila)

    return {"recargas": recargas}


@router.post("/recargas/{recarga_id}/acreditar")
def acreditar_recarga(
    recarga_id: str,
    datos: ResolverRecarga,
    admin: Annotated[dict, Depends(admin_actual)],
):
    """
    Aprueba una recarga y mueve el saldo.

    El monto que se acredita es el que va en `datos.monto`, o sea **el de la
    cartola**, no el que el cliente declaró. Si transfirió menos de lo que dijo,
    se acredita lo que llegó; la diferencia queda a la vista en la recarga.

    Todo en una transacción: o se acredita y se marca, o no pasa nada. Si el
    saldo se moviera sin marcar la recarga, quedaría lista para acreditarse otra
    vez.
    """
    with pool.connection() as conn:
        # `for update`: dos administradores no pueden aprobar la misma recarga
        # en paralelo y acreditar el doble.
        recarga = conn.execute(
            """
            select r.id, r.estado, r.cuenta_id, r.pack_id, r.monto_declarado, r.referencia,
                   c.nombre as cuenta
              from recargas r join cuentas c on c.id = r.cuenta_id
             where r.id = %s
               for update of r
            """,
            (recarga_id,),
        ).fetchone()

        if recarga is None:
            raise HTTPException(status_code=404, detail="La recarga no existe")

        if recarga["estado"] != "pendiente":
            raise HTTPException(
                status_code=409,
                detail=f"Esta recarga ya está {recarga['estado']}.",
            )

        # Sin monto explícito se usa lo declarado más el bono del pack. Es el
        # caso normal —transfirió lo que dijo— y evita retecleárlo.
        pack = PACKS.get(recarga["pack_id"] or "")
        monto = datos.monto
        if monto is None:
            monto = recarga["monto_declarado"] + (pack["bonus"] if pack else 0)

        if monto <= 0:
            raise HTTPException(status_code=422, detail="El monto a acreditar tiene que ser mayor que cero")

        conn.execute("select saldo from cuentas where id = %s for update", (recarga["cuenta_id"],))

        detalle = f"Recarga {recarga['referencia']}"
        fila = _mover_saldo(conn, recarga["cuenta_id"], monto, "carga", detalle, admin)

        conn.execute(
            """
            update recargas
               set estado = 'acreditada', monto_acreditado = %s, nota = %s,
                   resuelta_en = now(), resuelta_por = %s
             where id = %s
            """,
            (monto, (datos.nota or "").strip() or None, admin["email"], recarga_id),
        )

    logger.info(
        "%s acreditó la recarga %s de '%s': declarado %s, acreditado %s",
        admin["email"], recarga["referencia"], recarga["cuenta"],
        recarga["monto_declarado"], monto,
    )
    return {"saldo": fila["saldo"], "monto_acreditado": monto}


@router.post("/recargas/{recarga_id}/rechazar")
def rechazar_recarga(
    recarga_id: str,
    datos: ResolverRecarga,
    admin: Annotated[dict, Depends(admin_actual)],
):
    """
    Descarta una recarga sin mover saldo.

    La nota es obligatoria: el cliente la va a ver, y "rechazada" sin motivo
    genera una llamada telefónica que se podría haber evitado.

    No se borra la fila. Que alguien declaró una transferencia que no llegó es
    justamente lo que hay que poder revisar después.
    """
    nota = (datos.nota or "").strip()
    if not nota:
        raise HTTPException(
            status_code=422,
            detail="Escribe el motivo: el cliente lo va a ver.",
        )

    with pool.connection() as conn:
        fila = conn.execute(
            """
            update recargas
               set estado = 'rechazada', nota = %s, resuelta_en = now(), resuelta_por = %s
             where id = %s and estado = 'pendiente'
             returning id, referencia
            """,
            (nota, admin["email"], recarga_id),
        ).fetchone()

    if fila is None:
        raise HTTPException(
            status_code=409,
            detail="La recarga no existe o ya estaba resuelta.",
        )

    logger.info("%s rechazó la recarga %s: %s", admin["email"], fila["referencia"], nota)
    return {"ok": True}


@router.get("/plantillas")
def listar_plantillas(admin: Annotated[dict, Depends(admin_actual)]):
    """Las plantillas de Excel disponibles para asignar a un proceso."""
    with pool.connection() as conn:
        filas = conn.execute(
            """
            select id, servicio, nombre, columnas, activa
              from plantillas_excel
             where activa
             order by servicio, nombre
            """
        ).fetchall()

    return {"plantillas": [dict(f) for f in filas]}


@router.post("/plantillas", status_code=201)
def crear_plantilla(datos: PlantillaNueva, admin: Annotated[dict, Depends(admin_actual)]):
    """
    Una plantilla nueva de Excel. Las columnas son las que documenta excel.py:
    cada una con `titulo`, `origen` y `campo` (y `patron` para los documentos).
    """
    if not datos.columnas:
        raise HTTPException(status_code=422, detail="La plantilla necesita al menos una columna")

    for columna in datos.columnas:
        if not columna.get("titulo"):
            raise HTTPException(status_code=422, detail="Cada columna necesita un título")
        if columna.get("origen") not in ("solicitud", "consolidado", "documento"):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Origen inválido en '{columna.get('titulo')}': "
                    "debe ser solicitud, consolidado o documento"
                ),
            )

    with pool.connection() as conn:
        fila = conn.execute(
            """
            insert into plantillas_excel (servicio, nombre, columnas)
                 values (%s, %s, %s)
              returning id, servicio, nombre
            """,
            (datos.servicio, datos.nombre.strip(), Jsonb(datos.columnas)),
        ).fetchone()

    logger.info("%s creó la plantilla '%s'", admin["email"], datos.nombre)
    return dict(fila)


@router.get("/catalogo")
def catalogo_servicios(admin: Annotated[dict, Depends(admin_actual)]):
    """
    Los servicios que existen, para armar el formulario sin escribir sus ids a
    mano. `disponible` indica si el motor procesa sus formatos hoy.
    """
    return {
        "servicios": [
            {
                "id": s.id,
                "nombre": s.nombre,
                "unidad_medida": s.unidad_medida,
                "precio": s.precio,
                "disponible": s.disponible,
            }
            for s in CATALOGO.values()
        ]
    }

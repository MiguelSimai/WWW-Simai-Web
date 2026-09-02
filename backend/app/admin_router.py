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
from .db import pool
from .dependencias import admin_actual

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


class CuentaNueva(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)


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


class PlantillaNueva(BaseModel):
    servicio: str
    nombre: str = Field(min_length=1, max_length=200)
    columnas: list[dict]


@router.get("/cuentas")
def listar_cuentas(admin: Annotated[dict, Depends(admin_actual)]):
    """Las cuentas con su saldo, cuántos usuarios tienen y qué servicios."""
    with pool.connection() as conn:
        cuentas = conn.execute(
            """
            select c.id, c.nombre, c.saldo, c.contratado_en, c.creada_en,
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
    with pool.connection() as conn:
        fila = conn.execute(
            "insert into cuentas (nombre) values (%s) returning id, nombre, saldo",
            (datos.nombre.strip(),),
        ).fetchone()

    logger.info("Cuenta creada por %s: %s", admin["email"], datos.nombre)
    return dict(fila)


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

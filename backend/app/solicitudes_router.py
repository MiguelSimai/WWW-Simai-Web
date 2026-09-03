"""
Recepción de expedientes desde el portal.

Un expediente es lo que en el escritorio del cliente es una carpeta: su número
de solicitud por nombre y un set de documentos dentro. Llega en una sola
petición y se despacha documento por documento al motor.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from . import cuentas, excel, gateway_client, medicion, motor_db
from .catalogo import servicio_por_id
from .db import pool
from .dependencias import conexion, sesion_actual

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/solicitudes", tags=["solicitudes"])

# Tope de documentos por expediente. No es una limitación técnica sino un
# freno: una carga de mil archivos hay que partirla, y así el error aparece al
# subir en vez de a mitad del despacho.
_MAX_DOCUMENTOS = 100


def _codigo(prefijo: str) -> str:
    """Código legible y no adivinable. El cliente lo ve y lo cita en soporte."""
    return f"{prefijo}-{secrets.token_hex(4).upper()}"


def _referencia(codigo: str, numero_cliente: str | None) -> str:
    """
    Con qué identificador viaja el expediente al motor (`id_solicitud_externa`).

    Tiene que ser **único por envío**, no por número de cliente: N8N decide que
    un expediente está completo contando las solicitudes del motor que llevan
    esta referencia, contra la cantidad de archivos declarada. Si dos envíos la
    compartieran, el conteo sumaría los dos y el expediente no se consolidaría
    nunca.

    Y un mismo número sí se reenvía en la práctica: el cliente corrige un
    documento y sube la carpeta de nuevo.

    Por eso lleva el número del cliente más el sufijo del código:

        297541  +  SOL-B178531E   ->  297541-B178531E

    Así el número sigue siendo visible y buscable en el motor (un LIKE
    '297541-%' trae todos sus envíos), y cada envío se cuenta por separado.
    Sin número de carpeta, el código solo ya es único.
    """
    if not numero_cliente:
        return codigo

    sufijo = codigo.rsplit("-", 1)[-1]
    return f"{numero_cliente}-{sufijo}"


# Cuántas solicitudes por página. El panel las lista completas, así que no
# conviene mandar cientos de una vez.
_POR_PAGINA = 25


# Estados que el panel conoce. Se validan acá para no armar un `where` con lo
# que llegue en la URL.
_ESTADOS = ("procesando", "revisar", "completada", "error")


def _filtros(cuenta_id: str, estado, desde, hasta, buscar) -> tuple[str, list]:
    """
    Arma el `where` común de la lista y de los contadores.

    Los dos tienen que filtrar por lo mismo o los números de los chips no
    cuadrarían con lo que se ve debajo.
    """
    condiciones = ["s.cuenta_id = %s"]
    valores: list = [cuenta_id]

    if estado in _ESTADOS:
        condiciones.append("s.estado = %s")
        valores.append(estado)

    if desde:
        condiciones.append("s.creada_en >= %s")
        valores.append(desde)

    if hasta:
        # El `hasta` que el usuario elige es un día completo, no su medianoche.
        condiciones.append("s.creada_en < (%s::date + 1)")
        valores.append(hasta)

    if buscar:
        # Por número de expediente o por código: es como el cliente se refiere
        # a lo que envió cuando llama por teléfono.
        condiciones.append("(s.numero_cliente ilike %s or s.codigo ilike %s)")
        patron = f"%{buscar.strip()}%"
        valores += [patron, patron]

    return " and ".join(condiciones), valores


@router.get("")
def listar_solicitudes(
    usuario: Annotated[dict, Depends(sesion_actual)],
    conn: Annotated[Any, Depends(conexion)],
    pagina: int = 1,
    estado: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    buscar: str | None = None,
):
    """
    Los expedientes de la cuenta, del más reciente al más antiguo.

    Son de la cuenta, no de la persona: dos usuarios de la misma empresa ven lo
    mismo, igual que comparten el saldo.

    **Filtrar y contar se hacen acá, no en el navegador.** Antes el front
    cargaba la primera página y filtraba sobre ella: los expedientes más allá
    del número 25 no aparecían nunca, y los contadores de estado decían cuántos
    había *entre los 25 cargados*, que no es lo que el cliente lee.

    `conteos` viene de la misma consulta filtrada pero **sin** el filtro de
    estado: los chips tienen que decir cuántos hay de cada estado dentro del
    rango y la búsqueda actuales, no cuántos quedan tras aplicarse a sí mismos.

    `etiqueta` es lo que el panel muestra como nombre de lo enviado: el número
    del expediente si subió una carpeta, o el nombre del archivo si fue uno
    suelto. Se arma acá para que el front no tenga que decidirlo.
    """
    pagina = max(1, pagina)
    desplazamiento = (pagina - 1) * _POR_PAGINA

    where, valores = _filtros(usuario["cuenta_id"], estado, desde, hasta, buscar)

    filas = conn.execute(
        f"""
        select s.codigo, s.servicio, s.numero_cliente, s.unidades, s.costo,
               s.estado, s.resumen, s.error, s.creada_en,
               count(d.id)                       as documentos,
               min(d.archivo)                    as primer_archivo
          from solicitudes s
          left join documentos d on d.solicitud_id = s.id
         where {where}
         group by s.id
         order by s.creada_en desc
         limit %s offset %s
        """,
        valores + [_POR_PAGINA + 1, desplazamiento],
    ).fetchall()

    # Los contadores ignoran el filtro de estado, que es el que alimentan.
    where_conteo, valores_conteo = _filtros(usuario["cuenta_id"], None, desde, hasta, buscar)
    por_estado = conn.execute(
        f"select s.estado, count(*) as n from solicitudes s where {where_conteo} group by s.estado",
        valores_conteo,
    ).fetchall()

    conteos = {e: 0 for e in _ESTADOS}
    for fila in por_estado:
        if fila["estado"] in conteos:
            conteos[fila["estado"]] = fila["n"]
    conteos["todas"] = sum(conteos[e] for e in _ESTADOS)

    # Se pidió una de más solo para saber si hay página siguiente.
    hay_mas = len(filas) > _POR_PAGINA
    filas = filas[:_POR_PAGINA]

    return {
        "solicitudes": [_resumir(f) for f in filas],
        "total": conteos["todas"],
        "conteos": conteos,
        "pagina": pagina,
        "por_pagina": _POR_PAGINA,
        "hay_mas": hay_mas,
    }


@router.get("/excel")
def descargar_excel(
    usuario: Annotated[dict, Depends(sesion_actual)],
    desde: str | None = None,
    hasta: str | None = None,
    servicio: str | None = None,
):
    """
    La planilla de los expedientes de un rango de fechas.

    Una fila por expediente, con las columnas que define la plantilla del
    servicio. `desde` y `hasta` en formato YYYY-MM-DD; `hasta` incluye el día
    completo, que es lo que espera cualquiera que escribe una fecha.

    Sólo se incluyen los expedientes ya cerrados: los que están en proceso no
    tienen resultado que reportar, y meterlos con las celdas vacías haría creer
    que el análisis no encontró nada.
    """
    condiciones = ["s.cuenta_id = %s", "s.estado <> 'procesando'"]
    parametros: list = [usuario["cuenta_id"]]

    if desde:
        condiciones.append("s.creada_en >= %s")
        parametros.append(_fecha(desde, "desde"))
    if hasta:
        # Menor que el día siguiente: así "hasta el 23" incluye todo el 23.
        condiciones.append("s.creada_en < %s")
        parametros.append(_fecha(hasta, "hasta") + timedelta(days=1))
    if servicio:
        condiciones.append("s.servicio = %s")
        parametros.append(servicio)

    donde = " and ".join(condiciones)

    with pool.connection() as conn:
        solicitudes = conn.execute(
            f"""
            select s.id, s.codigo, s.servicio, s.numero_cliente, s.unidades,
                   s.costo, s.estado, s.resumen, s.error, s.respuesta_ia,
                   s.creada_en, s.cerrada_en,
                   (select count(*) from documentos d where d.solicitud_id = s.id)
                     as documentos
              from solicitudes s
             where {donde}
             order by s.creada_en
            """,
            parametros,
        ).fetchall()

        if not solicitudes:
            raise HTTPException(
                status_code=404,
                detail="No hay expedientes terminados en ese rango.",
            )

        ids = [s["id"] for s in solicitudes]
        documentos = conn.execute(
            """
            select solicitud_id, archivo, estado, resumen, error, respuesta_ia
              from documentos
             where solicitud_id = any(%s)
             order by archivo
            """,
            (ids,),
        ).fetchall()

        # La plantilla la elige la cuenta para ese servicio: dos clientes con
        # "Análisis de documentos" esperan planillas distintas. Con varios
        # servicios en el rango se usa el del primero, porque mezclar columnas
        # de procesos distintos en una hoja no tendría sentido.
        servicio_hoja = solicitudes[0]["servicio"]
        plantilla = conn.execute(
            """
            select p.nombre, p.columnas
              from cuenta_procesos cp
              join plantillas_excel p on p.id = cp.plantilla_id
             where cp.cuenta_id = %s and cp.servicio = %s and cp.activo and p.activa
            """,
            (usuario["cuenta_id"], servicio_hoja),
        ).fetchone()

    por_solicitud: dict = {}
    for doc in documentos:
        por_solicitud.setdefault(doc["solicitud_id"], []).append(dict(doc))

    filas = [{**dict(s), "documentos_detalle": por_solicitud.get(s["id"], [])} for s in solicitudes]

    columnas = plantilla["columnas"] if plantilla else excel.COLUMNAS_GENERICAS
    nombre_hoja = plantilla["nombre"] if plantilla else "Solicitudes"
    if not plantilla:
        logger.info("El servicio '%s' no tiene plantilla: se usa la genérica.", servicio_hoja)

    contenido = excel.generar(filas, columnas, nombre_hoja)

    marca = (desde or "inicio") + "_" + (hasta or "hoy")
    nombre = f"simai_{servicio_hoja}_{marca}.xlsx"

    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


def _fecha(valor: str, etiqueta: str) -> datetime:
    try:
        return datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"La fecha '{etiqueta}' debe ir como YYYY-MM-DD.",
        ) from None


@router.get("/{codigo}")
def ver_solicitud(
    codigo: str,
    usuario: Annotated[dict, Depends(sesion_actual)],
):
    """Una solicitud con el detalle de sus documentos."""
    with pool.connection() as conn:
        fila = conn.execute(
            """
            select s.id, s.codigo, s.servicio, s.numero_cliente, s.unidades,
                   s.costo, s.estado, s.resumen, s.error, s.respuesta_ia,
                   s.creada_en, s.cerrada_en,
                   count(d.id)    as documentos,
                   min(d.archivo) as primer_archivo
              from solicitudes s
              left join documentos d on d.solicitud_id = s.id
             where s.codigo = %s and s.cuenta_id = %s
             group by s.id
            """,
            (codigo, usuario["cuenta_id"]),
        ).fetchone()

        if fila is None:
            # El filtro por cuenta_id va en el where, así que pedir la
            # solicitud de otro devuelve lo mismo que pedir una inexistente:
            # no se confirma que el código exista.
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")

        documentos = conn.execute(
            """
            select codigo, archivo, unidades, costo, estado, resumen,
                   confianza, error, respuesta_ia, cerrado_en
              from documentos
             where solicitud_id = %s
             order by archivo
            """,
            (fila["id"],),
        ).fetchall()

    # camelCase para todo lo que cruza al front, igual que en el listado: el
    # TypeScript de `SolicitudDetalle` lo consume tal cual.
    detalle = _resumir(fila)
    detalle["respuestaIa"] = fila["respuesta_ia"]
    detalle["cerradaEn"] = fila["cerrada_en"]
    detalle["documentosDetalle"] = [
        {
            "codigo": d["codigo"],
            "archivo": d["archivo"],
            "unidades": d["unidades"],
            "costo": d["costo"],
            "estado": d["estado"],
            "resultado": d["resumen"],
            "confianza": float(d["confianza"]) if d["confianza"] is not None else None,
            "error": d["error"],
            "respuestaIa": d["respuesta_ia"],
        }
        for d in documentos
    ]
    return detalle


def _resumir(fila: dict) -> dict:
    """Forma con que el front consume una solicitud."""
    return {
        "codigo": fila["codigo"],
        "servicio": fila["servicio"],
        "numeroCliente": fila["numero_cliente"],
        # Lo que el panel muestra como nombre: el número del expediente si lo
        # hay, o el archivo si fue uno suelto.
        "etiqueta": fila["numero_cliente"] or fila["primer_archivo"] or fila["codigo"],
        "documentos": fila["documentos"],
        "unidades": fila["unidades"],
        "costo": fila["costo"],
        "estado": fila["estado"],
        "resultado": fila["resumen"] or fila["error"] or "",
        "fecha": fila["creada_en"],
    }


@router.post("", status_code=201)
def crear_solicitud(
    usuario: Annotated[dict, Depends(sesion_actual)],
    conn: Annotated[Any, Depends(conexion)],
    servicio: Annotated[str, Form()],
    archivos: Annotated[list[UploadFile], File(alias="archivo")],
    numero_cliente: Annotated[str | None, Form()] = None,
):
    """
    Recibe un expediente completo, lo cobra y lo despacha al motor.

    El orden importa y no es casual:

      1. Validar y medir todo antes de tocar nada. Si un documento no sirve,
         el expediente no entra: es preferible a dejarlo a medio procesar.
      2. Reservar el saldo. Si no alcanza, nadie gastó nada en Azure.
      3. Registrar el expediente en el motor, para que N8N pueda consolidarlo.
         Sin esto los documentos se procesan pero el resultado nunca llega.
      4. Recién ahí despachar los documentos.
    """
    svc = servicio_por_id(servicio)
    if svc is None:
        raise HTTPException(status_code=422, detail=f"Servicio desconocido: {servicio}")
    if not svc.disponible:
        raise HTTPException(status_code=422, detail=svc.motivo_no_disponible)

    # Qué proceso del motor le toca a esta cuenta, y de paso si tiene el
    # servicio contratado. Va antes de leer los archivos: no tiene sentido
    # subir 100 MB para rechazarlos después.
    if not usuario.get("cuenta_id"):
        raise HTTPException(status_code=403, detail="Tu usuario no tiene una cuenta asociada.")

    try:
        proceso = cuentas.proceso_para(conn, usuario["cuenta_id"], servicio)
    except cuentas.ServicioNoContratado as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not archivos:
        raise HTTPException(status_code=422, detail="No llegó ningún archivo.")
    if len(archivos) > _MAX_DOCUMENTOS:
        raise HTTPException(
            status_code=422,
            detail=f"Un expediente admite hasta {_MAX_DOCUMENTOS} documentos.",
        )

    # ── 1. Validar y medir el expediente completo ────────────────────────────
    documentos: list[dict] = []
    tope_bytes = svc.max_mb * 1024 * 1024

    for subido in archivos:
        nombre = subido.filename or "sin-nombre"
        contenido = subido.file.read()

        if not contenido:
            raise HTTPException(status_code=422, detail=f"{nombre} está vacío.")
        if len(contenido) > tope_bytes:
            raise HTTPException(
                status_code=422,
                detail=f"{nombre} supera el máximo de {svc.max_mb} MB.",
            )

        extension = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
        if extension not in svc.extensiones:
            raise HTTPException(
                status_code=422,
                detail=f"{nombre}: {svc.nombre} no procesa archivos {extension}.",
            )

        try:
            unidades = medicion.medir(svc, nombre, contenido)
        except medicion.ArchivoNoMedible as exc:
            raise HTTPException(status_code=422, detail=f"{nombre}: {exc}") from exc

        documentos.append(
            {
                "codigo": _codigo("DOC"),
                "archivo": nombre,
                "contenido": contenido,
                "unidades": unidades,
                "costo": medicion.costo(svc, unidades),
            }
        )

    unidades_total = sum(d["unidades"] for d in documentos)
    costo_total = sum(d["costo"] for d in documentos)

    # ── 2. Reservar el saldo y crear el expediente ───────────────────────────
    codigo = _codigo("SOL")
    referencia = _referencia(codigo, numero_cliente)

    cuenta_id = usuario["cuenta_id"]

    # Todo lo que sigue va en la conexión del request. El `commit` explícito
    # está donde antes cerraba el `with`: la reserva tiene que quedar firme
    # ANTES de hablar con el motor, porque si el motor falla se compensa con
    # `_anular` y eso necesita que la reserva exista.
    #
    # `for update` sobre la cuenta: dos cargas simultáneas —de la misma persona
    # o de dos usuarios de la misma empresa— no pueden reservar cada una contra
    # el mismo saldo.
    saldo = conn.execute(
        "select saldo from cuentas where id = %s for update",
        (cuenta_id,),
    ).fetchone()["saldo"]

    if saldo < costo_total:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Saldo insuficiente: el expediente cuesta ${costo_total:,} "
                f"y tienes ${saldo:,}."
            ).replace(",", "."),
        )

    solicitud_id = conn.execute(
        """
        insert into solicitudes
               (codigo, cuenta_id, usuario_id, servicio, numero_cliente,
                referencia_motor, unidades, costo)
             values (%s, %s, %s, %s, %s, %s, %s, %s)
          returning id
        """,
        (
            codigo,
            cuenta_id,
            # Quién la subió, que es distinto de a quién se le cobra.
            usuario["id"],
            servicio,
            numero_cliente,
            referencia,
            unidades_total,
            costo_total,
        ),
    ).fetchone()["id"]

    for doc in documentos:
        conn.execute(
            """
            insert into documentos
                   (solicitud_id, codigo, archivo, unidades, costo)
                 values (%s, %s, %s, %s, %s)
            """,
            (solicitud_id, doc["codigo"], doc["archivo"], doc["unidades"], doc["costo"]),
        )

    conn.execute(
        "update cuentas set saldo = saldo - %s where id = %s",
        (costo_total, cuenta_id),
    )
    conn.execute(
        """
        insert into movimientos_saldo
               (cuenta_id, usuario_id, solicitud_id, tipo, monto, detalle)
             values (%s, %s, %s, 'reserva', %s, %s)
        """,
        (cuenta_id, usuario["id"], solicitud_id, -costo_total, f"Expediente {codigo}"),
    )

    # La reserva queda firme acá, y con eso se libera el lock de la cuenta.
    conn.commit()

    # ── 3. Registrar el expediente para que N8N lo consolide ─────────────────
    # Sin esta fila, N8N nunca sabe que el expediente está completo y el
    # resultado no llega. Si falla, se devuelve la reserva y no se despacha.
    try:
        motor_db.registrar_expediente(
            numero_cliente=referencia,
            cantidad_archivos=len(documentos),
            id_proceso=proceso["id_proceso"],
        )
    except Exception as exc:
        logger.error("No se pudo registrar el expediente %s: %s", codigo, exc)
        _anular(solicitud_id, cuenta_id, costo_total, codigo)
        raise HTTPException(
            status_code=503,
            detail="El servicio de procesamiento no está disponible. No se te cobró.",
        ) from exc

    # ── 4. Despachar los documentos al motor ─────────────────────────────────
    fallados: list[str] = []

    for doc in documentos:
        try:
            correlation_id = gateway_client.enviar_documento(
                proceso=proceso,
                referencia_externa=referencia,
                codigo_documento=doc["codigo"],
                nombre_archivo=doc["archivo"],
                contenido=doc["contenido"],
                usuario=usuario["email"],
            )
        except gateway_client.ErrorGateway as exc:
            # Un documento rechazado no bota el expediente: queda marcado con
            # su motivo y el resto sigue. Su costo se devuelve al cerrar.
            logger.warning("Documento %s rechazado: %s", doc["archivo"], exc)
            fallados.append(doc["codigo"])
            _marcar_error(conn, doc["codigo"], str(exc))
            continue

        _guardar_correlation(conn, doc["codigo"], correlation_id)

    # Un solo commit para todos los documentos. Antes cada uno abría su propia
    # conexión: con cuatro documentos eran cuatro aperturas de 1,6 s.
    conn.commit()

    # Si el motor rechazó todo, no hay nada que esperar: se cierra en error y
    # se devuelve la reserva completa.
    if len(fallados) == len(documentos):
        _anular(solicitud_id, cuenta_id, costo_total, codigo, estado="error")
        raise HTTPException(
            status_code=422,
            detail="Ningún documento del expediente pudo procesarse. No se te cobró.",
        )

    logger.info(
        "Expediente %s creado: %s documentos, %s unidades, $%s",
        codigo,
        len(documentos),
        unidades_total,
        costo_total,
    )

    return {"codigo": codigo, "estado": "procesando"}


def _guardar_correlation(conn, codigo_documento: str, correlation_id: str) -> None:
    """No hace commit: lo hace el llamador, una vez por expediente."""
    conn.execute(
        "update documentos set correlation_id = %s where codigo = %s",
        (correlation_id, codigo_documento),
    )


def _marcar_error(conn, codigo_documento: str, detalle: str) -> None:
    """No hace commit: lo hace el llamador, una vez por expediente."""
    conn.execute(
        """
        update documentos
           set estado = 'error', error = %s, cerrado_en = now()
         where codigo = %s
        """,
        (detalle[:500], codigo_documento),
    )


def _anular(
    solicitud_id: str,
    cuenta_id: str,
    monto: int,
    codigo: str,
    estado: str = "error",
) -> None:
    """Devuelve la reserva completa y cierra el expediente sin cobro."""
    with pool.connection() as conn:
        conn.execute(
            "update cuentas set saldo = saldo + %s where id = %s",
            (monto, cuenta_id),
        )
        conn.execute(
            """
            insert into movimientos_saldo (cuenta_id, solicitud_id, tipo, monto, detalle)
                 values (%s, %s, 'devolucion', %s, %s)
            """,
            (cuenta_id, solicitud_id, monto, f"Expediente {codigo} no procesado"),
        )
        conn.execute(
            """
            update solicitudes
               set estado = %s, costo = 0, cerrada_en = now()
             where id = %s
            """,
            (estado, solicitud_id),
        )

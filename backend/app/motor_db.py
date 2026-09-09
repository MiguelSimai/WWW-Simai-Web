"""
Lo único que el portal escribe en la base del motor.

El portal tiene su propia base para todo: usuarios, solicitudes, documentos y
saldo. Lo de acá es la excepción, y son dos tablas que N8N necesita para
consolidar un expediente.

`iagw_n8n_procesos_externo` — la cabecera. N8N decide que un expediente está
completo comparando la cantidad de documentos esperados contra los que ya
procesó el motor, y ese total sale de su `cantidad_archivos`. Tiene que estar
ANTES de que empiecen a llegar los callbacks: si N8N no encuentra la fila, no
consolida nunca y el expediente queda colgado.

`iagw_n8n_proceso_detalle` — una fila por documento. Es lo que le permite a
N8N saber qué documento del expediente corresponde a cada `correlation_id`.
El motor recibe el código del documento y lo devuelve en el callback, pero no
lo guarda en ninguna tabla suya: sin esta fila, el vínculo entre el resultado
del motor y el documento del portal solo existe de paso.

Se mantiene aislado en este módulo a propósito. Es la única parte del portal
que conoce el esquema del motor, así que si ese esquema cambia, se arregla acá
y en ningún otro lugar.
"""

import logging

from .config import config
from .db import Conexiones

logger = logging.getLogger(__name__)

# Marca con que quedan los expedientes del portal en el log del motor, para
# distinguirlos de los que entran por otros pipelines.
TIPO_LOG = "PORTAL SIMAI"

# Una conexión por escritura, igual que en db.py y por el mismo motivo: los
# hilos de fondo del pool de psycopg dejan el proceso colgado bajo Passenger.
# Acá pesa menos todavía, porque se escribe una fila por expediente.
#
# En modo simulado no hay conexión: no se abre ni se usa.
pool = None if config.motor_simulado else Conexiones(config.motor_database_url)


def registrar_expediente(
    numero_cliente: str,
    cantidad_archivos: int,
    id_proceso: int,
) -> None:
    """
    Registra el expediente para que N8N sepa cuándo está completo.

    Si la fila ya existe —un reintento del cliente con el mismo número—, se
    actualiza la cantidad en vez de insertar otra: dos filas con el mismo
    `id_externo` dejarían a N8N comparando contra el total equivocado.

    Lanza la excepción si falla. El expediente no se puede enviar al motor sin
    esto: quedaría procesado pero nunca consolidado, y el cliente pagaría por
    un resultado que no llega.
    """
    if config.motor_simulado:
        logger.info(
            "[motor simulado] Expediente %s con %s documentos — no se escribe nada",
            numero_cliente,
            cantidad_archivos,
        )
        return

    with pool.connection() as conn:
        actualizadas = conn.execute(
            """
            update iagw_n8n_procesos_externo
               set cantidad_archivos   = %s,
                   estado              = 'EN_PROCESO',
                   fecha_actualizacion = now()
             where id_externo = %s
               and tipo_log   = %s
            """,
            (cantidad_archivos, numero_cliente, TIPO_LOG),
        ).rowcount

        if not actualizadas:
            conn.execute(
                """
                insert into iagw_n8n_procesos_externo
                       (fecha_ingreso, id_externo, tipo_log, estado,
                        id_empresa, id_proceso, cantidad_archivos)
                     values (now(), %s, %s, 'EN_PROCESO', %s, %s, %s)
                """,
                (
                    numero_cliente,
                    TIPO_LOG,
                    config.gateway_empresa_id,
                    id_proceso,
                    cantidad_archivos,
                ),
            )

    logger.info(
        "Expediente registrado en el motor: %s con %s documentos",
        numero_cliente,
        cantidad_archivos,
    )


def registrar_documentos(numero_cliente: str, documentos: list[dict]) -> None:
    """
    Registra de una vez el detalle de todos los documentos del expediente.

    Va en lote y no uno por uno a propósito: abrir una conexión a la base del
    motor cuesta ~1,7 s, así que cuatro documentos serían casi siete segundos
    de espera para el cliente, que ya subió sus archivos y mira una barra
    completa sin que pase nada. Es el mismo motivo por el que el router hace un
    solo commit para todos los documentos en la base del portal.

    Cada elemento de `documentos` lleva:
        codigo          código del documento en el portal (va en id_docuware)
        correlation_id  el que devolvió el motor, o None si lo rechazó
        nro_paginas     páginas cobradas, ya descontadas las hojas en blanco
        estado          'EN_PROCESO' o 'error'
        mensaje_error   motivo del rechazo, si lo hubo

    Se reescribe lo que ya exista: un reintento del mismo documento actualiza
    su fila en vez de agregar otra, que dejaría a N8N contando de más.

    A diferencia de `registrar_expediente`, un fallo acá NO interrumpe nada.
    Cuando esto corre los documentos ya se despacharon y ya se cobraron; morir
    en este punto dejaría al motor procesando algo que el portal da por
    fallido. Se registra el problema y se sigue.
    """
    if not documentos:
        return

    if config.motor_simulado:
        logger.info(
            "[motor simulado] %s documento(s) de %s — no se escribe nada",
            len(documentos),
            numero_cliente,
        )
        return

    try:
        with pool.connection() as conn:
            for doc in documentos:
                error = doc.get("mensaje_error")
                datos = (
                    doc["correlation_id"],
                    doc["nro_paginas"],
                    doc["estado"],
                    error[:500] if error else None,
                )

                actualizadas = conn.execute(
                    """
                    update iagw_n8n_proceso_detalle
                       set correlation_id = %s,
                           nro_paginas    = %s,
                           estado         = %s,
                           mensaje_error  = %s
                     where id_externo  = %s
                       and id_docuware = %s
                    """,
                    (*datos, numero_cliente, doc["codigo"]),
                ).rowcount

                if not actualizadas:
                    conn.execute(
                        """
                        insert into iagw_n8n_proceso_detalle
                               (fecha_ingreso, id_externo, id_docuware,
                                nro_paginas, estado, correlation_id, mensaje_error)
                             values (now(), %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            numero_cliente,
                            doc["codigo"],
                            doc["nro_paginas"],
                            doc["estado"],
                            doc["correlation_id"],
                            error[:500] if error else None,
                        ),
                    )
    except Exception as exc:
        logger.error(
            "No se pudo registrar el detalle de %s: %s", numero_cliente, exc
        )
        return

    logger.info(
        "Detalle registrado en el motor: %s documento(s) de %s",
        len(documentos),
        numero_cliente,
    )

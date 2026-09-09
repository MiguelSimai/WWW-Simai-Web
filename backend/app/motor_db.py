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


def registrar_documento(
    numero_cliente: str,
    correlation_id: str | None,
    codigo_documento: str,
    nro_paginas: int,
    estado: str,
    mensaje_error: str | None = None,
) -> None:
    """
    Registra un documento del expediente en el detalle que consume N8N.

    `codigo_documento` viaja en `id_docuware`. El nombre del campo viene del
    pipeline original, que ingestaba desde DocuWare; acá cumple el mismo papel
    —identificar el documento dentro del expediente— con el código del portal.

    Se reescribe si ya existe: un reintento del mismo documento actualiza su
    fila en vez de agregar otra, que dejaría a N8N contando de más.

    A diferencia de `registrar_expediente`, un fallo acá NO interrumpe nada.
    Cuando esto corre el documento ya se despachó al motor y ya se cobró; morir
    en este punto dejaría al motor procesando algo que el portal da por
    fallido. Se registra el problema y se sigue.
    """
    if config.motor_simulado:
        logger.info(
            "[motor simulado] Documento %s de %s (%s páginas) — no se escribe nada",
            codigo_documento,
            numero_cliente,
            nro_paginas,
        )
        return

    try:
        with pool.connection() as conn:
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
                (
                    correlation_id,
                    nro_paginas,
                    estado,
                    mensaje_error[:500] if mensaje_error else None,
                    numero_cliente,
                    codigo_documento,
                ),
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
                        codigo_documento,
                        nro_paginas,
                        estado,
                        correlation_id,
                        mensaje_error[:500] if mensaje_error else None,
                    ),
                )
    except Exception as exc:
        logger.error(
            "No se pudo registrar el detalle del documento %s de %s: %s",
            codigo_documento,
            numero_cliente,
            exc,
        )
        return

    logger.info(
        "Documento registrado en el motor: %s de %s — %s",
        codigo_documento,
        numero_cliente,
        estado,
    )

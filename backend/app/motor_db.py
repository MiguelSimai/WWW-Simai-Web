"""
Única escritura del portal en la base del motor.

El portal tiene su propia base para todo: usuarios, solicitudes, documentos y
saldo. Lo de acá es la excepción, y tiene un solo motivo.

N8N decide que un expediente está completo comparando la cantidad de
documentos esperados contra los que ya procesó el motor. Ese total sale de
`iagw_n8n_procesos_externo.cantidad_archivos`, y tiene que estar registrado
ANTES de que empiecen a llegar los callbacks: si N8N no encuentra la fila, no
consolida nunca y el expediente queda colgado.

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

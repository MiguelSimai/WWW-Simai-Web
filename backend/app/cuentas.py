"""
Qué tiene contratado cada cuenta.

"Análisis de documentos" no es un solo proceso del motor: el de créditos
automotrices de un cliente tiene su prompt y su `schema_salida`, y el de
facturas de otro es un proceso distinto. La tabla `cuenta_procesos` dice, para
cada cuenta y cada servicio, a qué proceso del motor mandar y con qué plantilla
armar el Excel.

Una fila ahí significa además que la cuenta **tiene contratado** ese servicio:
sin fila, el portal no lo ofrece y lo rechaza.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ServicioNoContratado(Exception):
    """La cuenta no tiene ese servicio habilitado."""


def procesos_de(conn: Any, cuenta_id: str) -> list[dict]:
    """Los servicios habilitados de una cuenta, con su proceso del motor."""
    return [
        dict(fila)
        for fila in conn.execute(
            """
            select servicio, tipo_servicio, proceso_codigo, id_proceso, plantilla_id
              from cuenta_procesos
             where cuenta_id = %s and activo
             order by servicio
            """,
            (cuenta_id,),
        ).fetchall()
    ]


def servicios_habilitados(conn: Any, cuenta_id: str | None) -> list[str]:
    """Sólo los nombres, que es lo que el front necesita para armar la pantalla."""
    if not cuenta_id:
        return []
    return [p["servicio"] for p in procesos_de(conn, cuenta_id)]


def proceso_para(conn: Any, cuenta_id: str, servicio: str) -> dict:
    """
    El proceso del motor que le toca a esta cuenta para este servicio.

    Lanza `ServicioNoContratado` si no lo tiene habilitado. Es el control que
    de verdad decide: la pantalla oculta lo que no corresponde, pero una
    petición armada a mano llega igual acá.
    """
    fila = conn.execute(
        """
        select servicio, tipo_servicio, proceso_codigo, id_proceso, plantilla_id
          from cuenta_procesos
         where cuenta_id = %s and servicio = %s and activo
        """,
        (cuenta_id, servicio),
    ).fetchone()

    if fila is None:
        logger.warning(
            "La cuenta %s intentó usar '%s', que no tiene contratado", cuenta_id, servicio
        )
        raise ServicioNoContratado(
            f"Tu cuenta no tiene habilitado el servicio '{servicio}'. "
            "Escríbenos para activarlo."
        )

    return dict(fila)

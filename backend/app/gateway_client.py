"""
Cliente del motor de procesamiento (API del gateway).

Es la única pieza del portal que conoce el contrato del gateway. Si ese
contrato cambia —otra ruta, otros headers, otra forma del body—, se arregla
acá y el resto del portal no se entera.
"""

import base64
import logging
import uuid

import httpx

from .config import config

logger = logging.getLogger(__name__)


class ErrorGateway(Exception):
    """El motor rechazó el documento o no se pudo contactar."""


# El proceso ya no vive acá: lo trae la cuenta desde `cuenta_procesos` (ver
# cuentas.py). Dos clientes pueden usar el mismo servicio con procesos del
# motor distintos —cada uno con su prompt y su schema_salida—, así que un mapa
# global no alcanzaba.
#
# Lo que llega es un dict con `tipo_servicio`, `proceso_codigo` e `id_proceso`.
# Los tres tienen que coincidir con la fila de `iagw_proceso` del motor, que
# además debe tener `modo_respuesta_default = 'async'`, o el gateway responde
# 404.


def _entrada(contenido: bytes) -> dict:
    """
    Cómo viaja el archivo hasta el motor.

    Hoy va en base64 dentro del body. Es el punto único a cambiar para pasar a
    Blob Storage: el gateway ya acepta `url_archivo` y descarga por streaming,
    con `blob.core.windows.net` en su whitelist. Ese cambio es obligatorio
    antes de aceptar los archivos grandes que promete el catálogo — un audio
    de 500 MB son ~666 MB de JSON por acá.
    """
    return {"archivo": base64.b64encode(contenido).decode("ascii")}


def enviar_documento(
    proceso: dict,
    referencia_externa: str,
    codigo_documento: str,
    nombre_archivo: str,
    contenido: bytes,
    usuario: str,
) -> str:
    """
    Encola un documento en el motor y devuelve su `correlation_id`.

    El gateway responde 202 sin haber procesado nada: solo validó el documento
    y lo dejó en la cola. El resultado llega después, por callback.

    `referencia_externa` viaja como `id_solicitud_externa`: es lo que agrupa el
    expediente en el motor y lo que N8N cuenta para saber si está completo. Es
    el número del cliente cuando subió una carpeta, o el código de la solicitud
    cuando subió un archivo suelto.

    `codigo_documento` viaja como `id_transaccion_cliente` y vuelve en el
    callback, así que es la vía para saber qué documento se cerró.
    """
    if config.motor_simulado:
        correlation_id = str(uuid.uuid4())
        logger.info(
            "[motor simulado] %s -> proceso '%s', ref %s, doc %s (%s bytes) => %s",
            nombre_archivo,
            proceso["proceso_codigo"],
            referencia_externa,
            codigo_documento,
            len(contenido),
            correlation_id,
        )
        return correlation_id

    cuerpo = {
        "identificacion": {
            "tipo_servicio": proceso["tipo_servicio"],
            "proceso": proceso["proceso_codigo"],
            "modo_respuesta": "async",
        },
        "entrada": {
            **_entrada(contenido),
            "id_solicitud_externa": referencia_externa,
            "url_callback": f"{config.public_url}/api/callbacks/expediente",
        },
        "metadata": {
            "id_transaccion_cliente": codigo_documento,
            "usuario": usuario,
            "observacion": nombre_archivo,
        },
    }

    cabeceras = {
        "x-empresa-origen": str(config.gateway_empresa_id),
        "x-canal": config.gateway_canal,
    }

    try:
        respuesta = httpx.post(
            f"{config.gateway_url}/api/v1/solicitudes",
            json=cuerpo,
            headers=cabeceras,
            timeout=config.gateway_timeout,
        )
    except httpx.RequestError as exc:
        logger.error("No se pudo contactar el motor: %s", exc)
        raise ErrorGateway("El servicio de procesamiento no responde.") from exc

    if respuesta.status_code >= 400:
        # El gateway explica el rechazo en el cuerpo: formato no permitido,
        # archivo ilegible, proceso inexistente. Se propaga para que el cliente
        # sepa qué le pasó a su documento en vez de un "error" a secas.
        detalle = respuesta.text[:300]
        logger.warning(
            "El motor rechazó %s (HTTP %s): %s",
            nombre_archivo,
            respuesta.status_code,
            detalle,
        )
        raise ErrorGateway(f"El motor rechazó el documento: {detalle}")

    datos = respuesta.json()
    correlation_id = datos.get("correlation_id")
    if not correlation_id:
        raise ErrorGateway("El motor no devolvió correlation_id.")

    return correlation_id

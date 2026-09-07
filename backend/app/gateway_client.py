"""
Cliente del motor de procesamiento (API del gateway).

Es la única pieza del portal que conoce el contrato del gateway. Si ese
contrato cambia —otra ruta, otros headers, otra forma del body—, se arregla
acá y el resto del portal no se entera.
"""

import base64
import logging
import time
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


# Token vigente, cacheado en el proceso. Pedir uno por documento duplicaría
# la latencia de cada envío y, en un expediente de cincuenta archivos, serían
# cincuenta viajes de más contra la puerta de entrada.
_token: dict = {"valor": None, "expira_en": 0.0}


def _obtener_token(forzar: bool = False) -> str | None:
    """
    Devuelve un access token para el gateway, reutilizando el vigente.

    `forzar` descarta el cacheado: se usa cuando el gateway responde 401, que
    es la señal de que el token dejó de servir antes de lo que decía.

    Devuelve None cuando no hay autenticación configurada — el caso del
    gateway local, sin puerta delante.
    """
    if not config.gateway_token_url:
        return None

    # El margen evita usar un token que expire durante el viaje de ida.
    if not forzar and _token["valor"] and _token["expira_en"] > time.monotonic() + 60:
        return _token["valor"]

    try:
        respuesta = httpx.post(
            config.gateway_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": config.gateway_token_client_id,
                "client_secret": config.gateway_token_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
    except httpx.RequestError as exc:
        logger.error("No se pudo pedir el token al gateway: %s", exc)
        raise ErrorGateway("El servicio de procesamiento no responde.") from exc

    if respuesta.status_code >= 400:
        # El cuerpo del error es lo único que distingue credenciales inválidas
        # de una URL equivocada; sin él el diagnóstico es a ciegas.
        logger.error(
            "Token rechazado (HTTP %s): %s", respuesta.status_code, respuesta.text[:300]
        )
        raise ErrorGateway("El portal no pudo autenticarse ante el motor.")

    valor = respuesta.json().get("access_token")
    if not valor:
        logger.error("La respuesta del token no trae access_token: %s", respuesta.text[:300])
        raise ErrorGateway("El portal no pudo autenticarse ante el motor.")

    _token["valor"] = valor
    _token["expira_en"] = time.monotonic() + int(respuesta.json().get("expires_in", 3600))
    logger.info("Token del gateway renovado.")
    return valor


def _cabeceras(token: str | None) -> dict:
    """Headers con que el portal se identifica ante el gateway."""
    cabeceras = {
        "x-empresa-origen": str(config.gateway_empresa_id),
        "x-canal": config.gateway_canal,
    }
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    return cabeceras


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

    url = f"{config.gateway_url}/api/v1/solicitudes"

    def despachar(token: str | None):
        try:
            return httpx.post(
                url,
                json=cuerpo,
                headers=_cabeceras(token),
                timeout=config.gateway_timeout,
            )
        except httpx.RequestError as exc:
            logger.error("No se pudo contactar el motor: %s", exc)
            raise ErrorGateway("El servicio de procesamiento no responde.") from exc

    respuesta = despachar(_obtener_token())

    # Un 401 con token en mano significa que caducó antes de lo previsto: se
    # pide uno nuevo y se reintenta una vez. Encolar es idempotente desde el
    # lado del portal —el gateway aún no había registrado nada— así que el
    # reintento no duplica trabajo.
    if respuesta.status_code == 401 and config.gateway_token_url:
        logger.info("El motor respondió 401 — renovando token y reintentando.")
        respuesta = despachar(_obtener_token(forzar=True))

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

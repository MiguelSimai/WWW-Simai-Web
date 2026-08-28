"""
Adaptador ASGI → WSGI, mínimo y sin hilos.

FastAPI es ASGI y Passenger —el Python Selector de cPanel— sólo habla WSGI.
La librería habitual para esto es `a2wsgi`, pero bajo este Passenger deja la
petición colgada para siempre: arranca un event loop en un hilo de fondo que
aparentemente no puede vivir acá, y ni una app ASGI trivial responde.

Este adaptador evita el problema haciendo lo más simple posible: por cada
petición arma el scope, corre la app con `asyncio.run()` y devuelve la
respuesta. Un loop nuevo por petición, que muere con ella. Nada persistente.

El costo es crear y destruir un event loop por petición —del orden de
microsegundos— y perder el paralelismo entre peticiones dentro del proceso.
Para el volumen de este portal no se nota, y Passenger levanta varios procesos.

No se ejecuta el ciclo de `lifespan`: la app está escrita para no necesitarlo
(ver el comentario en app/main.py).
"""

import asyncio
import sys
from http import HTTPStatus
from typing import Any, Callable, Iterable


def _estado(codigo: int) -> str:
    """
    WSGI espera "200 OK", no "200": el número más su frase.

    Un código que no esté en la tabla estándar se devuelve con una frase
    genérica en vez de fallar.
    """
    try:
        return f"{codigo} {HTTPStatus(codigo).phrase}"
    except ValueError:
        return f"{codigo} Status"


def _cabeceras(environ: dict) -> list[tuple[bytes, bytes]]:
    """
    Cabeceras HTTP en el formato que espera ASGI: pares de bytes en minúscula.

    WSGI las entrega como `HTTP_X_ALGO`; el tipo y largo del cuerpo vienen sin
    ese prefijo, así que van aparte.
    """
    cabeceras: list[tuple[bytes, bytes]] = []

    for clave, valor in environ.items():
        if clave.startswith("HTTP_"):
            nombre = clave[5:].replace("_", "-").lower()
            cabeceras.append((nombre.encode("latin-1"), str(valor).encode("latin-1")))

    if environ.get("CONTENT_TYPE"):
        cabeceras.append((b"content-type", str(environ["CONTENT_TYPE"]).encode("latin-1")))
    if environ.get("CONTENT_LENGTH"):
        cabeceras.append((b"content-length", str(environ["CONTENT_LENGTH"]).encode("latin-1")))

    return cabeceras


# Tope del cuerpo que se acepta leer. El adaptador lo carga completo en
# memoria, así que sin este límite un `Content-Length` enorme podría agotar la
# del proceso —en hosting compartido es poca—. Un expediente de 100 documentos
# de 25 MB no llega a esto; una petición que lo supere es un error o un abuso.
MAX_CUERPO_BYTES = 200 * 1024 * 1024


class CuerpoDemasiadoGrande(Exception):
    pass


def _cuerpo_peticion(environ: dict) -> bytes:
    """
    Lee el cuerpo completo.

    Se lee de una vez porque el `receive` de ASGI se resuelve en un solo
    mensaje. Es aceptable acá: quien sube archivos ya los tiene completos en el
    proceso de todas formas (ver `medicion.py`).
    """
    try:
        largo = int(environ.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        largo = 0

    if largo > MAX_CUERPO_BYTES:
        raise CuerpoDemasiadoGrande(f"{largo} bytes")

    entrada = environ.get("wsgi.input")
    if not entrada or largo <= 0:
        return b""

    # Se lee acotado por el tope y no por lo que declare la cabecera: un
    # `Content-Length` no es una promesa.
    return entrada.read(min(largo, MAX_CUERPO_BYTES))


def _scope(environ: dict) -> dict:
    ruta = environ.get("PATH_INFO", "") or "/"
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": environ.get("SERVER_PROTOCOL", "HTTP/1.1").split("/")[-1],
        "method": environ.get("REQUEST_METHOD", "GET").upper(),
        "scheme": environ.get("wsgi.url_scheme", "http"),
        "path": ruta,
        "raw_path": ruta.encode("latin-1"),
        # La app se monta en la raíz del subdominio, así que no hay prefijo.
        "root_path": "",
        "query_string": (environ.get("QUERY_STRING", "") or "").encode("latin-1"),
        "headers": _cabeceras(environ),
        "client": (environ.get("REMOTE_ADDR", ""), 0),
        "server": (environ.get("SERVER_NAME", ""), int(environ.get("SERVER_PORT") or 0)),
    }


class ASGIaWSGI:
    """Envuelve una app ASGI y la expone como aplicación WSGI."""

    def __init__(self, app: Callable) -> None:
        self._app = app

    def __call__(self, environ: dict, start_response: Callable) -> Iterable[bytes]:
        try:
            estado, cabeceras, cuerpo = asyncio.run(self._responder(environ))
        except CuerpoDemasiadoGrande as exc:
            mensaje = b'{"detail":"El contenido enviado es demasiado grande."}'
            sys.stderr.write(f"Cuerpo rechazado por tamano: {exc}\n")
            sys.stderr.flush()
            start_response(
                "413 Content Too Large",
                [("Content-Type", "application/json"), ("Content-Length", str(len(mensaje)))],
            )
            return [mensaje]
        except Exception:
            # Sin esto un error quedaría como una respuesta vacía, que en el
            # navegador se ve igual que un cuelgue. El traceback va a
            # stderr.log, que es donde se busca.
            import traceback

            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            mensaje = b'{"detail":"Error interno"}'
            start_response(
                "500 Internal Server Error",
                [("Content-Type", "application/json"), ("Content-Length", str(len(mensaje)))],
            )
            return [mensaje]

        start_response(estado, cabeceras)
        return [cuerpo]

    async def _responder(self, environ: dict) -> tuple[str, list[tuple[str, str]], bytes]:
        cuerpo_entrada = _cuerpo_peticion(environ)
        enviado = {"status": 500, "headers": [], "body": b""}
        pendiente = {"cuerpo": True}

        async def receive() -> dict[str, Any]:
            if pendiente["cuerpo"]:
                pendiente["cuerpo"] = False
                return {"type": "http.request", "body": cuerpo_entrada, "more_body": False}
            # La app no debería volver a pedir, pero si lo hace se le dice que
            # el cliente se fue en vez de dejarla esperando.
            return {"type": "http.disconnect"}

        async def send(mensaje: dict[str, Any]) -> None:
            if mensaje["type"] == "http.response.start":
                enviado["status"] = mensaje["status"]
                enviado["headers"] = mensaje.get("headers") or []
            elif mensaje["type"] == "http.response.body":
                enviado["body"] += mensaje.get("body") or b""

        await self._app(_scope(environ), receive, send)

        cabeceras = [
            (
                k.decode("latin-1") if isinstance(k, bytes) else str(k),
                v.decode("latin-1") if isinstance(v, bytes) else str(v),
            )
            for k, v in enviado["headers"]
        ]

        return _estado(enviado["status"]), cabeceras, enviado["body"]

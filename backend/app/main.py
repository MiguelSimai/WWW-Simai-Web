import logging

# Usar el almacén de certificados del sistema operativo en vez del paquete
# `certifi`. Va antes que cualquier import que arme un contexto TLS.
#
# Hace falta cuando algo intercepta el tráfico TLS —antivirus con inspección
# web, proxys corporativos, VPNs—: esos programas firman con su propio
# certificado raíz, que sí está en el almacén del sistema pero nunca en
# certifi. Sin esto, las llamadas a Google fallan con CERTIFICATE_VERIFY_FAILED.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    # En una imagen mínima sin truststore, seguimos con certifi.
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import URL
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .admin_router import router as admin_router
from .auth_router import router as auth_router
from .callbacks_router import router as callbacks_router
from .cuenta_router import router as cuenta_router
from .solicitudes_router import router as solicitudes_router
from .config import config
from .db import pool
from .motor_db import pool as pool_motor

logger = logging.getLogger(__name__)


# SIN lifespan a propósito.
#
# Los pools se abren al importarse (ver db.py y motor_db.py). En un servidor
# ASGI el lifespan sería el lugar natural, pero bajo Passenger —hosting
# compartido, con el adaptador ASGI→WSGI de passenger_wsgi.py— el ciclo de
# lifespan no se completa y el proceso queda colgado: sin responder y sin
# dejar rastro en el log. Costó encontrarlo, así que no volver a ponerlo.
#
# No cerrar los pools explícitamente no es problema: cuando el proceso muere,
# el sistema cierra los sockets, y `max_idle` ya recicla las conexiones ociosas.
if pool_motor is None:
    logger.warning("MOTOR SIMULADO: nada se envía a procesar de verdad.")

def _llego_por_https(scope: Scope) -> bool:
    """
    Si la conexión original venía cifrada.

    `scheme` sale de `wsgi.url_scheme`, que es lo que informa LiteSpeed (ver
    asgi_wsgi.py). `x-forwarded-proto` cubre el caso de un proxy o CDN puesto
    delante que termine el TLS antes de este servidor: ahí el de atrás ve HTTP
    y, sin mirar la cabecera, la aplicación redirigiría en bucle.
    """
    if scope.get("scheme") == "https":
        return True

    for nombre, valor in scope.get("headers", []):
        if nombre == b"x-forwarded-proto":
            return valor.decode("latin-1").split(",")[0].strip() == "https"

    return False


class RedireccionHTTPS:
    """
    Manda a HTTPS lo que llegue en claro.

    Por qué vive en la aplicación y no en el servidor: ver `forzar_https` en
    config.py. Resumido, Passenger atiende la petición antes de que las reglas
    del panel o del .htaccess lleguen a correr.

    Responde **308** y no 301 a propósito. Un 301 obliga al cliente a repetir
    la petición como GET y sin cuerpo: el callback de N8N —POST
    /api/callbacks/expediente— llegaría vacío y con el método cambiado, el
    servidor contestaría 405, y los expedientes se quedarían en "procesando"
    sin que nadie entienda por qué. El 308 conserva método y cuerpo.

    Es ASGI puro y no `BaseHTTPMiddleware` porque no necesita leer ni tocar la
    respuesta: mira el esquema y corta.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _llego_por_https(scope):
            await self.app(scope, receive, send)
            return

        destino = URL(scope=scope).replace(scheme="https")
        # Un Host con ":80" daría "https://api.simai.cl:80", que no resuelve.
        if destino.port == 80:
            destino = destino.replace(port=None)

        await RedirectResponse(str(destino), status_code=308)(scope, receive, send)


# Un año, el valor estándar. El compromiso que crea es real: mientras esté
# vigente, un navegador que ya visitó el dominio se niega a hablarle por HTTP, y
# si el certificado venciera sin renovarse la API queda inaccesible hasta
# arreglarlo. Para desactivarlo no basta con quitar la cabecera —los navegadores
# ya la tienen guardada—: hay que publicar "max-age=0" y esperar a que la vean.
#
# Sin `preload`: eso mete el dominio en una lista que los navegadores traen de
# fábrica, y salir de ahí toma meses.
_HSTS = b"max-age=31536000; includeSubDomains"


class CabecerasSeguridad:
    """
    Agrega HSTS a las respuestas que salieron por HTTPS.

    Esto normalmente lo pone el servidor web —el front lo hace desde su
    `.htaccess`—, pero acá no hay quien lo haga: bajo Passenger esas reglas no
    llegan a aplicarse (ver `forzar_https` en config.py). Así que lo pone la
    aplicación, que es por donde la petición sí pasa.

    Va solo sobre HTTPS. No es por prudencia: sobre HTTP el navegador ignora la
    cabecera por especificación, porque quien pueda alterar una respuesta en
    claro también podría inyectarla o quitarla.

    De paso, esto hace que en local no aparezca nunca —ahí se trabaja sobre
    http://localhost— y no haya que acordarse de apagarla.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _llego_por_https(scope):
            await self.app(scope, receive, send)
            return

        async def enviar(mensaje: dict) -> None:
            if mensaje["type"] == "http.response.start":
                # Lista nueva en vez de `append`: el mensaje lo arma otro
                # middleware y no corresponde modificarle su estructura.
                mensaje["headers"] = list(mensaje.get("headers", [])) + [
                    (b"strict-transport-security", _HSTS)
                ]
            await send(mensaje)

        await self.app(scope, receive, enviar)


app = FastAPI(
    title="SimAI API",
    # En None, FastAPI no registra la ruta: pedirla devuelve el mismo 404 que
    # cualquier dirección inventada, así que ni siquiera confirma que la
    # documentación exista y esté apagada. Ver `docs_publicas` en config.py.
    docs_url="/docs" if config.docs_publicas else None,
    redoc_url="/redoc" if config.docs_publicas else None,
    openapi_url="/openapi.json" if config.docs_publicas else None,
)

# Cookie temporal que sólo sostiene `state` y `nonce` durante el ida y vuelta
# a Google. No es la sesión del usuario: esa vive en Postgres.
app.add_middleware(
    SessionMiddleware,
    secret_key=config.secret_key,
    same_site="lax",
    https_only=config.cookie_secure,
    max_age=600,
)

# El front vive en otro puerto, así que necesita CORS con credenciales.
# allow_origins tiene que ser explícito: con "*" el navegador no manda cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.frontend_url],
    allow_credentials=True,
    # DELETE lo usa la administración para deshabilitar un servicio.
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

# Se agrega DESPUÉS de los otros dos, y el orden importa: Starlette envuelve la
# aplicación en orden inverso, así que el último que se agrega es el primero
# que ve la petición. Esta tiene que ser la primera — una petición en claro se
# corta ahí, sin tocar la sesión, el CORS ni la base.
#
# Apagado no se instala siquiera: en local se trabaja sobre http://localhost y
# no hay nada que redirigir.
app.add_middleware(CabecerasSeguridad)

if config.forzar_https:
    app.add_middleware(RedireccionHTTPS)

app.include_router(auth_router)
app.include_router(cuenta_router)
app.include_router(solicitudes_router)
# Lo llama N8N, no el navegador: no pasa por CORS ni por la cookie de sesión.
# Se autentica con el token compartido de CALLBACK_TOKEN.
app.include_router(callbacks_router)
# Administración interna: sólo los correos de ADMIN_EMAILS. Responde 404 al
# resto, así que no revela que existe.
app.include_router(admin_router)


@app.get("/api/salud")
async def salud(request: Request):
    """
    Señal de vida, y de paso cómo llegó la petición.

    `esquema` es lo que la aplicación cree que fue la conexión, que es
    exactamente la decisión que toma `RedireccionHTTPS`. Está para poder
    comprobarlo ANTES de encender `forzar_https`: pedida por https tiene que
    decir "https", y por http, "http". Si por https dijera "http", encender el
    interruptor dejaría la API en un bucle de redirecciones.
    """
    return {"ok": True, "esquema": request.url.scheme}

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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

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

app = FastAPI(title="SimAI API")

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
async def salud():
    return {"ok": True}

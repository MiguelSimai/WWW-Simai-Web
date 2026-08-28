from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse

from . import cuentas, sesiones, usuarios
from .dependencias import es_administrador
from .config import config
from .db import pool

router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=config.google_client_id,
    client_secret=config.google_client_secret,
    # PKCE: sin esto, alguien que intercepte el `code` puede canjearlo.
    client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
)


def _poner_cookie(respuesta: Response, token: str) -> None:
    respuesta.set_cookie(
        key=sesiones.COOKIE,
        value=token,
        max_age=config.session_hours * 3600,
        httponly=True,           # JavaScript no puede leerla: sobrevive a un XSS
        secure=config.cookie_secure,
        samesite="lax",          # no viaja en peticiones desde otros sitios
        path="/",
    )


def _ruta_interna(destino: str) -> bool:
    """
    Sólo aceptamos rutas relativas del propio portal.

    Sin esto tenemos un redirect abierto: bastaría con enviar a alguien un
    enlace `...?volver=https://sitio-falso.cl` para que termine ahí después
    de un login legítimo, con toda la apariencia de venir de SimAI.
    `//otro.cl` también se rechaza: el navegador lo lee como URL absoluta.
    """
    return destino.startswith("/") and not destino.startswith("//")


@router.get("/login/google")
async def login_google(request: Request):
    """Arranca el flujo. Authlib guarda `state` y `nonce` en la sesión temporal."""
    volver = request.query_params.get("volver", "/panel")
    request.session["volver"] = volver if _ruta_interna(volver) else "/panel"

    return await oauth.google.authorize_redirect(request, config.google_redirect_uri)


@router.get("/retorno")
async def callback_google(request: Request):
    """
    Google vuelve aquí con el `code`. Authlib lo canjea y valida la firma del
    id_token, el emisor, la audiencia y el nonce. Si algo no cuadra, revienta.

    La ruta se llama `/retorno` y no `/callback/google` por un motivo concreto:
    Chrome marcaba la URL anterior como "Sitio peligroso". No había ninguna
    entrada en la lista negra de Safe Browsing —Search Console lo confirmó—,
    era su detección en tiempo real. Y se entiende: un dominio recién creado
    sirviendo `/callback/google?...&iss=https://accounts.google.com` es la
    firma de un phishing que suplanta a Google.

    El parámetro `iss` lo pone Google y no se puede quitar; el path sí. Como
    este endpoint sólo devuelve redirecciones y nunca HTML, el veredicto de
    Chrome se basa en la URL, así que un path sin marca ajena es lo único que
    está en nuestras manos.

    Si se renombra otra vez, hay que cambiar a la par `GOOGLE_REDIRECT_URI` y
    los "URIs de redireccionamiento autorizados" de Google Cloud Console: los
    tres tienen que coincidir carácter por carácter o Google rechaza el login
    con `redirect_uri_mismatch`.
    """
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{config.frontend_url}/ingresar?error=oauth")

    claims = token.get("userinfo") or {}
    sujeto = claims.get("sub")
    email = claims.get("email")

    if not sujeto or not email:
        return RedirectResponse(f"{config.frontend_url}/ingresar?error=incompleto")

    def guardar() -> str:
        with pool.connection() as conn:
            usuario = usuarios.enlazar_o_crear(
                conn,
                proveedor="google",
                sujeto=sujeto,
                email=email,
                nombre=claims.get("name") or email.split("@")[0],
                email_verificado=bool(claims.get("email_verified")),
            )
            return sesiones.crear(
                conn,
                usuario["id"],
                request.client.host if request.client else None,
                request.headers.get("user-agent"),
            )

    # El pool es síncrono: al threadpool, para no bloquear el bucle de eventos.
    try:
        sesion = await run_in_threadpool(guardar)
    except ValueError:
        return RedirectResponse(f"{config.frontend_url}/ingresar?error=correo-no-verificado")

    volver = request.session.pop("volver", "/panel")
    respuesta = RedirectResponse(f"{config.frontend_url}{volver}")
    _poner_cookie(respuesta, sesion)
    return respuesta


@router.get("/me")
def me(request: Request):
    """El front llama esto al arrancar para saber si hay sesión."""
    with pool.connection() as conn:
        usuario = sesiones.usuario_de(conn, request.cookies.get(sesiones.COOKIE))

    if usuario is None:
        return JSONResponse({"detail": "Sin sesión"}, status_code=401)

    # Qué servicios tiene contratados la cuenta: con eso el front sabe qué
    # ofrecer en /enviar. Quien decide de verdad es el backend al recibir el
    # expediente; esto es para no mostrarle al cliente lo que no puede usar.
    with pool.connection() as conn:
        servicios = cuentas.servicios_habilitados(conn, usuario.get("cuenta_id"))

    return {
        "id": str(usuario["id"]),
        "email": usuario["email"],
        "nombre": usuario["nombre"],
        # El saldo y la contratación son de la cuenta, no de la persona.
        "empresa": usuario.get("cuenta_nombre"),
        "saldo": usuario["saldo"],
        # El front usa esto para decidir si mostrar el panel o la contratación.
        "contratado": usuario["contratado_en"] is not None,
        "servicios": servicios,
        # El front usa esto sólo para mostrar el acceso a la administración; el
        # backend valida el correo en cada llamada.
        "esAdmin": es_administrador(usuario),
    }


@router.post("/logout")
def logout(request: Request):
    with pool.connection() as conn:
        sesiones.revocar(conn, request.cookies.get(sesiones.COOKIE))

    respuesta = JSONResponse({"ok": True})
    respuesta.delete_cookie(sesiones.COOKIE, path="/")
    return respuesta

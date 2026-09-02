from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request, Response
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

# Microsoft Entra ID. Se registra sólo si hay credenciales: el portal tiene que
# arrancar igual mientras la app no esté dada de alta.
#
# Se usa el endpoint `organizations` y no `common` a propósito: habilita a
# cualquier empresa con Microsoft 365 —que es el mercado— y deja fuera las
# cuentas personales de Microsoft, cuyo correo no lo respalda ninguna
# organización. Importa porque más abajo el correo corporativo se da por
# verificado.
if config.microsoft_habilitado:
    oauth.register(
        name="microsoft",
        server_metadata_url=(
            "https://login.microsoftonline.com/organizations/v2.0"
            "/.well-known/openid-configuration"
        ),
        client_id=config.microsoft_client_id,
        client_secret=config.microsoft_client_secret,
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )

# Tenant con que llegan las cuentas personales de Microsoft. `organizations` no
# debería dejarlas pasar, pero se verifica igual: acá el correo se trata como
# verificado, y el de una cuenta personal no lo respalda nadie.
TENANT_PERSONAL = "9188040d-6c67-4c5b-b112-36a304b66dad"


def _poner_cookie(respuesta: Response, token: str) -> None:
    # La cookie vive el TOPE, no la ventana. La sesión se renueva sola en la
    # base mientras el usuario esté activo, así que si la cookie muriera a las
    # 3 horas lo echaría igual: la autoridad sobre cuándo termina la sesión es
    # la base, y la cookie sólo tiene que durar lo suficiente para llegar hasta
    # el tope absoluto.
    respuesta.set_cookie(
        key=sesiones.COOKIE,
        value=token,
        max_age=config.session_max_hours * 3600,
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


def _identidad(proveedor: str, claims: dict) -> tuple[str | None, str | None, bool]:
    """
    Saca (sujeto, email, email_verificado) de los claims.

    Cada proveedor los entrega distinto, y esa diferencia se resuelve acá para
    que el resto del flujo sea idéntico.
    """
    sujeto = claims.get("sub")

    if proveedor == "microsoft":
        # Entra no manda `email_verified`, y `email` es un claim opcional que
        # puede no venir. El UPN de `preferred_username` sí está siempre.
        email = claims.get("email") or claims.get("preferred_username")
        # El correo de una cuenta corporativa vive en un dominio que la
        # organización verificó ante Microsoft, así que darlo por verificado es
        # más sólido que confiar en un `email_verified` ajeno. Lo que no vale es
        # una cuenta personal, y eso se comprueba por el tenant.
        tenant = claims.get("tid")
        return sujeto, email, bool(tenant) and tenant != TENANT_PERSONAL

    return sujeto, claims.get("email"), bool(claims.get("email_verified"))


@router.get("/proveedores")
def proveedores():
    """
    Con qué se puede entrar hoy.

    El front pinta un botón por cada uno en vez de tenerlos fijos, así no
    ofrece lo que el servidor no tiene configurado.
    """
    lista = ["google"]
    if config.microsoft_habilitado:
        lista.append("microsoft")
    return {"proveedores": lista}


def _arrancar(request: Request, proveedor: str) -> None:
    """
    Guarda en la sesión temporal a dónde volver y con quién se está entrando.

    El proveedor va en la sesión y no en el path del retorno: ver el porqué en
    el docstring de `retorno()`.
    """
    volver = request.query_params.get("volver", "/panel")
    request.session["volver"] = volver if _ruta_interna(volver) else "/panel"
    request.session["proveedor"] = proveedor


@router.get("/login/google")
async def login_google(request: Request):
    """Arranca el flujo. Authlib guarda `state` y `nonce` en la sesión temporal."""
    _arrancar(request, "google")

    return await oauth.google.authorize_redirect(request, config.google_redirect_uri)


@router.get("/login/microsoft")
async def login_microsoft(request: Request):
    """
    Lo mismo contra Entra ID, para clientes con Microsoft 365.

    Responde 404 si no hay credenciales configuradas, en vez de fallar con un
    error del servidor: sin la app dada de alta en Entra, esta ruta no existe.
    """
    if not config.microsoft_habilitado:
        raise HTTPException(status_code=404, detail="Proveedor no disponible")

    _arrancar(request, "microsoft")

    return await oauth.microsoft.authorize_redirect(request, config.microsoft_redirect_uri)


@router.get("/retorno")
async def retorno(request: Request):
    """
    El proveedor vuelve aquí con el `code`. Authlib lo canjea y valida la firma
    del id_token, el emisor, la audiencia y el nonce. Si algo no cuadra,
    revienta.

    **Es un solo retorno para todos los proveedores**, y cuál fue lo dice
    `proveedor` en la sesión temporal, no el path. Dos motivos: hay un único URI
    de redirección que registrar en cada consola —ya nos costó un
    `redirect_uri_mismatch` tener dos nombres— y se conserva el path neutro, que
    es lo que se explica abajo.

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
    proveedor = request.session.pop("proveedor", "google")
    cliente = oauth.create_client(proveedor)

    # Sin cliente registrado no hay nada que canjear: pasa si alguien llega a
    # esta URL a mano, o si se quitaron las credenciales a mitad de un login.
    if cliente is None:
        return RedirectResponse(f"{config.frontend_url}/ingresar?error=oauth")

    try:
        token = await cliente.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{config.frontend_url}/ingresar?error=oauth")

    claims = token.get("userinfo") or {}
    sujeto, email, email_verificado = _identidad(proveedor, claims)

    if not sujeto or not email:
        return RedirectResponse(f"{config.frontend_url}/ingresar?error=incompleto")

    def guardar() -> str:
        with pool.connection() as conn:
            usuario = usuarios.enlazar_o_crear(
                conn,
                proveedor=proveedor,
                sujeto=sujeto,
                email=email,
                nombre=claims.get("name") or email.split("@")[0],
                email_verificado=email_verificado,
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

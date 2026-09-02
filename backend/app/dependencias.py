from typing import Annotated, Any, Iterator

from fastapi import Depends, HTTPException, Request

from . import sesiones
from .config import config
from .db import pool


def conexion() -> Iterator[Any]:
    """
    UNA conexión por petición, compartida por todo el request.

    Abrir una conexión contra Azure cuesta ~1,6 s —TCP, TLS y autenticación—
    mientras que una consulta sobre una ya abierta cuesta ~250 ms. Con cada
    capa abriendo la suya, el envío de un expediente de cuatro documentos
    pagaba siete aperturas: unos 11 segundos antes de hacer nada útil.

    FastAPI cachea las dependencias por petición, así que todos los que pidan
    `conexion` reciben la misma. No hay pool ni hilos de fondo: sigue siendo
    una conexión que nace y muere con el request, que es lo único que Passenger
    tolera (ver db.py).
    """
    with pool.connection() as conn:
        yield conn


def sesion_actual(
    request: Request,
    conn: Annotated[Any, Depends(conexion)],
) -> dict:
    """
    Usuario dueño de la sesión, o 401 si no hay.

    Devuelve el dict de `sesiones.usuario_de`: id, email, nombre, saldo y
    contratado_en. El saldo que trae es del momento de la consulta, así que
    para cobrar hay que releerlo con el registro bloqueado.
    """
    usuario = sesiones.usuario_de(conn, request.cookies.get(sesiones.COOKIE))

    if usuario is None:
        raise HTTPException(status_code=401, detail="Sin sesión")
    return usuario


def es_administrador(usuario: dict) -> bool:
    return (usuario.get("email") or "").lower() in config.administradores


def admin_actual(usuario: Annotated[dict, Depends(sesion_actual)]) -> dict:
    """
    Como `sesion_actual`, pero sólo para administradores.

    Responde 404 y no 403: quien no administra no tiene por qué enterarse de
    que existe una sección de administración.
    """
    if not es_administrador(usuario):
        raise HTTPException(status_code=404, detail="No encontrado")
    return usuario

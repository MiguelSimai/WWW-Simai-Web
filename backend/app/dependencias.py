from typing import Annotated

from fastapi import Depends, HTTPException, Request

from . import sesiones
from .config import config
from .db import pool


def sesion_actual(request: Request) -> dict:
    """
    Usuario dueño de la sesión, o 401 si no hay.

    Devuelve el dict de `sesiones.usuario_de`: id, email, nombre, saldo y
    contratado_en. El saldo que trae es del momento de la consulta, así que
    para cobrar hay que releerlo con el registro bloqueado.
    """
    with pool.connection() as conn:
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

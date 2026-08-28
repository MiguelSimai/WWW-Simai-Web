import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import config

COOKIE = "simai_sesion"


def _hash(token: str) -> bytes:
    """
    SHA-256 basta aquí: el token lo generamos nosotros con 256 bits de
    entropía, así que no hay nada que adivinar por fuerza bruta. Argon2 es
    para contraseñas elegidas por personas, no para tokens aleatorios.
    """
    return hashlib.sha256(token.encode()).digest()


def crear(conn: Any, usuario_id: str, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(hours=config.session_hours)

    conn.execute(
        """
        insert into sesiones (usuario_id, token_hash, expira_en, ip, user_agent)
             values (%s, %s, %s, %s, %s)
        """,
        (usuario_id, _hash(token), expira, ip, user_agent),
    )
    return token


def usuario_de(conn: Any, token: str | None) -> dict | None:
    """
    Usuario dueño de la sesión, o None si el token no sirve.

    El saldo y `contratado_en` salen de la **cuenta**, no del usuario: contrata
    la empresa, y todos sus usuarios comparten ese saldo.
    """
    if not token:
        return None

    return conn.execute(
        """
        select u.id, u.email, u.nombre, u.cuenta_id,
               c.nombre        as cuenta_nombre,
               c.saldo         as saldo,
               c.contratado_en as contratado_en
          from sesiones s
          join usuarios u on u.id = s.usuario_id
          left join cuentas c on c.id = u.cuenta_id
         where s.token_hash = %s
           and s.revocada_en is null
           and s.expira_en > now()
        """,
        (_hash(token),),
    ).fetchone()


def revocar(conn: Any, token: str | None) -> None:
    if not token:
        return

    conn.execute(
        "update sesiones set revocada_en = now() where token_hash = %s and revocada_en is null",
        (_hash(token),),
    )

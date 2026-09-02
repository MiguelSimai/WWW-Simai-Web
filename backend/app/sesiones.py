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
    # Se borran las sesiones ya vencidas de este usuario antes de crear la
    # nueva. Nada más las limpiaba, así que la tabla crecía para siempre: un
    # login al día por cliente son miles de filas al año que la consulta ya
    # ignora.
    #
    # Va acá y no en una tarea programada porque el login es la operación más
    # rara del sistema, y así el mantenimiento no necesita cron ni
    # infraestructura. Las revocadas no se tocan: conservan el rastro de que
    # alguien cerró sesión, y se van solas cuando les llega su expiración.
    conn.execute(
        "delete from sesiones where usuario_id = %s and expira_en < now()",
        (usuario_id,),
    )

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


def _renovar_si_corresponde(conn: Any, fila: dict) -> None:
    """
    Extiende la sesión cuando le queda poco de vida.

    Sin esto la sesión moría a las N horas del login pasara lo que pasara, y
    quien estaba trabajando se caía a media tarea.

    Se renueva sólo cuando queda **menos de un cuarto** de la ventana, no en
    cada petición: cada escritura contra Azure cuesta unos 250 ms y no hay por
    qué pagarla en todos los requests.

    El tope absoluto se respeta siempre. Una vez alcanzado, la sesión muere a
    su hora aunque el usuario siga activo, y tiene que volver a entrar.
    """
    ventana = timedelta(hours=config.session_hours)
    ahora = datetime.now(timezone.utc)

    if fila["_expira_en"] - ahora > ventana / 4:
        return

    tope = fila["_creado_en"] + timedelta(hours=config.session_max_hours)
    nuevo = min(ahora + ventana, tope)

    if nuevo <= fila["_expira_en"]:
        return

    conn.execute(
        "update sesiones set expira_en = %s where id = %s",
        (nuevo, fila["_sesion_id"]),
    )
    fila["_expira_en"] = nuevo


def usuario_de(conn: Any, token: str | None) -> dict | None:
    """
    Usuario dueño de la sesión, o None si el token no sirve.

    El saldo y `contratado_en` salen de la **cuenta**, no del usuario: contrata
    la empresa, y todos sus usuarios comparten ese saldo.

    Las claves con guion bajo son de la sesión misma y no del usuario: sólo las
    usa la renovación de acá abajo.
    """
    if not token:
        return None

    fila = conn.execute(
        """
        select u.id, u.email, u.nombre, u.cuenta_id,
               c.nombre        as cuenta_nombre,
               c.saldo         as saldo,
               c.contratado_en as contratado_en,
               s.id            as _sesion_id,
               s.expira_en     as _expira_en,
               s.creado_en     as _creado_en
          from sesiones s
          join usuarios u on u.id = s.usuario_id
          left join cuentas c on c.id = u.cuenta_id
         where s.token_hash = %s
           and s.revocada_en is null
           and s.expira_en > now()
        """,
        (_hash(token),),
    ).fetchone()

    if fila is None:
        return None

    _renovar_si_corresponde(conn, fila)
    return fila


def revocar_todas(conn: Any, usuario_id: str) -> int:
    """
    Cierra todas las sesiones abiertas de un usuario. Devuelve cuántas cerró.

    Es la contraparte de guardar las sesiones en la base en vez de emitir un
    JWT: `revocar()` necesita el token, y ese sólo lo tiene el navegador del
    usuario. Sin esta función, dar de baja a alguien no le quita el acceso —
    su cookie sigue sirviendo hasta que expire.

    No se borran las filas: quedan marcadas, para que después se pueda ver que
    el corte existió y cuándo.
    """
    return conn.execute(
        """
        update sesiones
           set revocada_en = now()
         where usuario_id = %s
           and revocada_en is null
           and expira_en > now()
        """,
        (usuario_id,),
    ).rowcount


def revocar(conn: Any, token: str | None) -> None:
    if not token:
        return

    conn.execute(
        "update sesiones set revocada_en = now() where token_hash = %s and revocada_en is null",
        (_hash(token),),
    )

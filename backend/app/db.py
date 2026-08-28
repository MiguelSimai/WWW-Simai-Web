from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from .config import config

# Una conexión por petición, sin pool.
#
# `psycopg_pool.ConnectionPool` mantiene hilos de fondo para reponer y vigilar
# las conexiones, y bajo Passenger —el Python Selector de cPanel— esos hilos
# dejan el proceso colgado: la app no arranca y no queda rastro en el log. Es
# el mismo motivo por el que `a2wsgi` no sirvió (ver asgi_wsgi.py).
#
# No es una pérdida grande, y en este caso casi ninguna: la DATABASE_URL de
# Neon apunta a su *pooler*, así que el pooling lo hace el servidor. Un pool
# local encima era redundante.
#
# Lo que cuesta es el saludo TCP+TLS de cada petición. Si algún día la API se
# mueve a un servidor propio con uvicorn, volver al pool es cambiar sólo este
# archivo: el resto del código usa `pool.connection()` y no sabe qué hay detrás.

# Timeouts cortos a propósito: sin ellos, una base inalcanzable —un firewall de
# salida bloqueando el puerto, por ejemplo— deja la petición esperando para
# siempre, y en el navegador eso se ve igual que un servidor caído. Es mejor un
# error en diez segundos que un cuelgue eterno.
CONEXION_TIMEOUT_SEG = 10


class Conexiones:
    """
    Lo mínimo del pool que usa la aplicación: `connection()`.

    Se mantiene el nombre y la forma de `ConnectionPool` para que los routers
    no cambien, y para poder volver al pool sin tocarlos.
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """
        Abre una conexión, la entrega y la cierra.

        Igual que `pool.connection()`: al salir sin excepción hace commit, y
        con excepción hace rollback. Eso lo garantiza psycopg al usar la
        conexión como gestor de contexto.
        """
        with psycopg.connect(
            self._conninfo,
            connect_timeout=CONEXION_TIMEOUT_SEG,
            row_factory=dict_row,
        ) as conexion:
            yield conexion

    # Compatibilidad con el pool: la app ya no las llama, pero un `open()` o un
    # `close()` sueltos no deberían romper nada.
    def open(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def close(self) -> None:
        pass


pool = Conexiones(config.database_url)

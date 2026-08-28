"""
Diagnóstico de conectividad desde el servidor hacia la base de datos.

Sirve para saber si el hosting puede llegar a Neon, o si su firewall de salida
lo bloquea. Es la diferencia entre "hay que arreglar el código" y "hay que
pedirle algo al proveedor".

Cómo correrlo en cPanel:

    Python App -> "Ejecutar script python" -> diagnostico.py -> Ejecutar script

Escribe el resultado en `diagnostico.txt`, al lado de este archivo, porque la
salida del panel a veces no se muestra. Ábrelo con el File Manager.
"""

import os
import socket
import sys
import time
from urllib.parse import urlparse

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico.txt")
lineas: list[str] = []


def anotar(texto: str = "") -> None:
    print(texto)
    lineas.append(texto)


anotar("=" * 60)
anotar("DIAGNOSTICO DE CONECTIVIDAD")
anotar("=" * 60)
anotar(f"Python  : {sys.version.split()[0]}")
anotar(f"Carpeta : {os.path.dirname(os.path.abspath(__file__))}")
anotar()

# ── 1. ¿Se leyó la configuración? ────────────────────────────────────────────
try:
    from app.config import config

    url = config.database_url
    anotar("1. Configuracion: OK, el .env se leyo")
except Exception as exc:
    anotar(f"1. Configuracion: FALLA -> {type(exc).__name__}: {exc}")
    anotar()
    anotar("   Sin configuracion no se puede seguir. Revisa el .env.")
    open(SALIDA, "w", encoding="utf-8").write("\n".join(lineas))
    sys.exit(1)

partes = urlparse(url)
host = partes.hostname or ""
puerto = partes.port or 5432
anotar(f"   host: {host}")
anotar(f"   puerto: {puerto}")
anotar()

# ── 2. ¿Resuelve el nombre? ──────────────────────────────────────────────────
try:
    inicio = time.time()
    direcciones = socket.getaddrinfo(host, puerto, proto=socket.IPPROTO_TCP)
    ips = sorted({d[4][0] for d in direcciones})
    anotar(f"2. DNS: OK en {time.time() - inicio:.2f}s -> {', '.join(ips)}")
except Exception as exc:
    anotar(f"2. DNS: FALLA -> {type(exc).__name__}: {exc}")
    ips = []
anotar()

# ── 3. ¿Se puede abrir el socket TCP? ────────────────────────────────────────
# Esta es la prueba que importa: si el firewall de salida bloquea el puerto,
# acá se ve como timeout.
if ips:
    anotar(f"3. Conexion TCP a {host}:{puerto}")
    for ip in ips[:2]:
        s = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        inicio = time.time()
        try:
            s.connect((ip, puerto))
            anotar(f"   {ip}: ABIERTO en {time.time() - inicio:.2f}s")
        except socket.timeout:
            anotar(f"   {ip}: TIMEOUT tras {time.time() - inicio:.1f}s")
            anotar("      -> el puerto de salida esta bloqueado por el hosting")
        except Exception as exc:
            anotar(f"   {ip}: {type(exc).__name__}: {exc}")
        finally:
            s.close()
else:
    anotar("3. Conexion TCP: no se probo, el DNS no resolvio")
anotar()

# ── 4. ¿Sale trafico a otros puertos? ────────────────────────────────────────
# Para distinguir "bloquean todo lo saliente" de "bloquean solo el 5432".
anotar("4. Otras salidas, para comparar")
for destino, puerto_prueba, etiqueta in [
    ("accounts.google.com", 443, "HTTPS (necesario para el login)"),
    ("google.com", 80, "HTTP"),
]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(8)
    inicio = time.time()
    try:
        s.connect((destino, puerto_prueba))
        anotar(f"   {destino}:{puerto_prueba} ABIERTO ({etiqueta})")
    except Exception as exc:
        anotar(f"   {destino}:{puerto_prueba} {type(exc).__name__} ({etiqueta})")
    finally:
        s.close()
anotar()

# ── 5. ¿Conecta psycopg de verdad? ───────────────────────────────────────────
anotar("5. Conexion real con psycopg")
try:
    import psycopg

    inicio = time.time()
    with psycopg.connect(url, connect_timeout=12) as conexion:
        version = conexion.execute("select version()").fetchone()[0]
        tablas = conexion.execute(
            """
            select count(*) from information_schema.tables
             where table_schema = 'public'
            """
        ).fetchone()[0]
    anotar(f"   OK en {time.time() - inicio:.2f}s")
    anotar(f"   {version[:60]}")
    anotar(f"   tablas en public: {tablas}")
    anotar()
    anotar("   >>> La base es alcanzable. El problema no es de red. <<<")
except Exception as exc:
    anotar(f"   FALLA tras {time.time() - inicio:.1f}s")
    anotar(f"   {type(exc).__name__}: {str(exc)[:300]}")
    anotar()
    anotar("   >>> Si el paso 3 dio TIMEOUT y el paso 4 abrio, el hosting")
    anotar("   >>> bloquea la salida al puerto de Postgres. Hay que pedirselo. <<<")

anotar()
anotar("=" * 60)

open(SALIDA, "w", encoding="utf-8").write("\n".join(lineas) + "\n")
print(f"\nResultado escrito en: {SALIDA}")

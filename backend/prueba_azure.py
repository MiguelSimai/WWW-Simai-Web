"""
¿Este hosting alcanza la base de Azure?

Temporal: se corre una vez desde cPanel para saber si V2network deja salir al
puerto de Postgres, ANTES de repuntar DATABASE_URL a Azure. Si se cambia la
variable sin saber esto, el sitio queda caído hasta descubrirlo.

    cPanel -> Setup Python App -> "Ejecutar script python" -> prueba_azure.py

Escribe el resultado en `prueba_azure.txt`, al lado de este archivo, porque la
salida del panel a veces no se muestra. Ábrelo con el Administrador de archivos.

No usa el .env ni las variables del panel a propósito: prueba Azure sin tocar
la configuración que hoy sostiene el sitio en producción.
"""

import os
import socket
import time
import urllib.request

HOST = "simai-db.postgres.database.azure.com"
PUERTO = 5432

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prueba_azure.txt")
lineas = []


def anotar(texto=""):
    print(texto)
    lineas.append(texto)


anotar("=" * 55)
anotar("PRUEBA DE SALIDA HACIA AZURE POSTGRES")
anotar("=" * 55)

# ── 1. IP de salida ──────────────────────────────────────────────────────────
# La que ve Azure, y la que hay que autorizar en su firewall. No tiene por qué
# ser la IP compartida que muestra cPanel: esa es la de entrada.
anotar("\n1. IP de salida de este hosting")
try:
    ip = urllib.request.urlopen("https://api.ipify.org", timeout=10).read().decode()
    anotar(f"   {ip}")
    anotar("   -> esta es la que va en la regla de firewall de Azure")
except Exception as exc:
    anotar(f"   No se pudo averiguar: {type(exc).__name__}: {exc}")

# ── 2. ¿Resuelve el nombre? ──────────────────────────────────────────────────
anotar("\n2. DNS")
try:
    ips = sorted({d[4][0] for d in socket.getaddrinfo(HOST, PUERTO, proto=socket.IPPROTO_TCP)})
    anotar(f"   {HOST} -> {', '.join(ips)}")
except Exception as exc:
    anotar(f"   FALLA: {type(exc).__name__}: {exc}")
    ips = []

# ── 3. La prueba que importa ─────────────────────────────────────────────────
# Si el firewall de salida bloquea el puerto, acá se ve como timeout.
anotar(f"\n3. Conexion TCP a {HOST}:{PUERTO}")
abierto = False
for ip in ips[:2]:
    s = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    inicio = time.time()
    try:
        s.connect((ip, PUERTO))
        anotar(f"   {ip}: ABIERTO en {time.time() - inicio:.2f}s")
        abierto = True
    except socket.timeout:
        anotar(f"   {ip}: TIMEOUT tras {time.time() - inicio:.1f}s")
    except Exception as exc:
        anotar(f"   {ip}: {type(exc).__name__}: {exc}")
    finally:
        s.close()

# ── 4. Comparacion ───────────────────────────────────────────────────────────
# Para distinguir "bloquean todo lo saliente" de "bloquean solo el 5432".
anotar("\n4. Otra salida, para comparar")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.connect(("google.com", 443))
    anotar("   google.com:443 ABIERTO")
except Exception as exc:
    anotar(f"   google.com:443 {type(exc).__name__}")
finally:
    s.close()

anotar("\n" + "=" * 55)
if abierto:
    anotar(">>> El hosting alcanza Azure. Se puede repuntar DATABASE_URL. <<<")
else:
    anotar(">>> Bloqueado. Hay que pedirle a V2network que habilite la    <<<")
    anotar(">>> salida TCP al puerto 5432 (y 6432 si usaras PgBouncer).   <<<")
anotar("=" * 55)

open(SALIDA, "w", encoding="utf-8").write("\n".join(lineas) + "\n")
print(f"\nResultado en: {SALIDA}")

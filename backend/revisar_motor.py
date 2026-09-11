"""
Qué credenciales del motor está viendo realmente la aplicación.

Cuando `registrar_expediente` falla con "password authentication failed" hay
tres candidatos y desde fuera no se distinguen: la variable del panel quedó
mal, quedó bien pero Passenger no la recargó, o hay un `.env` en el servidor
con un valor viejo que está ganando.

Este script los separa. No importa la contraseña: muestra una huella corta de
cada una, que basta para comparar contra la que sí funciona sin exponerla en
un archivo de texto.

Cómo correrlo en cPanel:

    Setup Python App -> "Ejecutar script python" -> revisar_motor.py

Escribe el resultado en `revisar_motor.txt`, al lado de este archivo, porque
la salida del panel a veces no se muestra. Ábrelo con el File Manager.
"""

import hashlib
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).parent
SALIDA = RAIZ / "revisar_motor.txt"
lineas: list[str] = []


def anotar(texto: str = "") -> None:
    print(texto)
    lineas.append(texto)


def huella(valor: str | None) -> str:
    """Identifica un secreto sin revelarlo."""
    if not valor:
        return "(vacío)"
    return hashlib.sha256(valor.encode()).hexdigest()[:10]


def describir(etiqueta: str, url: str | None) -> None:
    if not url:
        anotar(f"  {etiqueta}: (no definida)")
        return
    try:
        u = urlparse(url)
    except Exception as exc:
        anotar(f"  {etiqueta}: no se pudo interpretar — {exc}")
        return
    anotar(f"  {etiqueta}:")
    anotar(f"     usuario   : {u.username}")
    anotar(f"     servidor  : {u.hostname}:{u.port}")
    anotar(f"     base      : {(u.path or '').lstrip('/').split('?')[0]}")
    anotar(f"     clave     : huella {huella(u.password)}  ({len(u.password or '')} caracteres)")
    anotar(f"     sslmode   : {'sí' if 'sslmode' in (u.query or '') else 'NO declarado'}")


anotar("=" * 70)
anotar("CREDENCIALES DEL MOTOR — QUÉ VE LA APLICACIÓN")
anotar("=" * 70)
anotar()

# ── 1. Lo que llega por variable de entorno (el panel de cPanel) ─────────────
anotar("1. Variables de entorno del proceso")
anotar()
for nombre in ("MOTOR_SIMULADO", "GATEWAY_URL", "GATEWAY_CANAL", "GATEWAY_EMPRESA_ID",
               "PUBLIC_URL", "GATEWAY_TOKEN_URL"):
    anotar(f"  {nombre:24s} = {os.environ.get(nombre, '(no definida)')}")
for nombre in ("CALLBACK_TOKEN", "GATEWAY_TOKEN_CLIENT_ID", "GATEWAY_TOKEN_CLIENT_SECRET"):
    anotar(f"  {nombre:24s} = huella {huella(os.environ.get(nombre))}")
anotar()
describir("MOTOR_DATABASE_URL (entorno)", os.environ.get("MOTOR_DATABASE_URL"))
anotar()

# ── 2. Lo que hay en el archivo .env, si es que existe ───────────────────────
anotar("2. Archivo .env en el servidor")
anotar()
ruta_env = RAIZ / ".env"
if not ruta_env.exists():
    anotar("  No existe. Manda solo lo del panel, que es lo deseable.")
else:
    valores = {}
    for linea in ruta_env.read_text(encoding="utf-8", errors="replace").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            valores[k.strip()] = v.strip()
    anotar(f"  Existe, con {len(valores)} variables.")
    describir("MOTOR_DATABASE_URL (.env)", valores.get("MOTOR_DATABASE_URL"))
    anotar()
    anotar("  ATENCIÓN: pydantic lee primero el entorno, así que el panel gana")
    anotar("  sobre este archivo. Pero si una variable NO está en el panel, la")
    anotar("  toma de acá — y un valor viejo pasa desapercibido.")
anotar()

# ── 3. Lo que la aplicación resuelve de verdad ──────────────────────────────
anotar("3. Lo que resuelve la configuración de la aplicación")
anotar()
sys.path.insert(0, str(RAIZ))
try:
    from app.config import config
    describir("MOTOR_DATABASE_URL (efectiva)", config.motor_database_url)
    anotar()
    describir("DATABASE_URL del portal", config.database_url)
except Exception as exc:
    anotar(f"  No se pudo cargar la configuración: {exc}")
anotar()

# ── 4. La prueba que importa: ¿conecta? ─────────────────────────────────────
anotar("4. Conexión real a cada base")
anotar()
try:
    import psycopg
    from app.config import config

    for etiqueta, url in (("portal", config.database_url),
                          ("motor ", config.motor_database_url)):
        try:
            with psycopg.connect(url, connect_timeout=15) as conexion:
                usuario = conexion.execute("select current_user").fetchone()[0]
                base = conexion.execute("select current_database()").fetchone()[0]
            anotar(f"  {etiqueta}: CONECTA — usuario '{usuario}', base '{base}'")
        except Exception as exc:
            anotar(f"  {etiqueta}: FALLA — {str(exc)[:200]}")
except Exception as exc:
    anotar(f"  No se pudo probar: {exc}")

anotar()
anotar("=" * 70)

SALIDA.write_text("\n".join(lineas), encoding="utf-8")
print(f"\nResultado escrito en {SALIDA}")

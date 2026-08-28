"""
Lleva cualquier base de Postgres al modelo de datos del portal.

    .venv\\Scripts\\python.exe migrar.py            aplica lo que falte
    .venv\\Scripts\\python.exe migrar.py --estado   solo muestra qué falta
    .venv\\Scripts\\python.exe migrar.py --url ...  contra otra base

Cambiar de base —de local a Azure, de Neon a local— es esto: apuntas
DATABASE_URL al destino nuevo, corres esto, y el modelo queda idéntico. No hay
que recordar qué se aplicó ni en qué orden: cada base lleva su propia cuenta
en la tabla `migraciones`.

Para agregar un cambio al modelo, crea un archivo nuevo en `migraciones/` con
el número siguiente. No edites uno ya aplicado: las bases que lo corrieron no
lo volverán a correr, y quedarían distintas entre sí. Un cambio nuevo es
siempre un archivo nuevo.

Los archivos se aplican en orden de nombre, cada uno en su propia transacción:
si uno falla, ese queda sin aplicar y los anteriores se conservan.
"""

import sys
from pathlib import Path

import psycopg

CARPETA = Path(__file__).parent / "migraciones"

# Lleva la cuenta de lo aplicado en la propia base, que es el único lugar que
# viaja con ella.
TABLA = """
create table if not exists migraciones (
  nombre      text primary key,
  aplicada_en timestamptz not null default now()
)
"""


def aplicadas(conexion) -> set[str]:
    """
    Qué migraciones ya corrieron en esta base. Solo lectura.

    Si la tabla de control no existe, la base nunca fue migrada y no hay
    ninguna aplicada. No se crea acá para que `--estado` pueda mirar una base
    sin escribirle nada.
    """
    existe = conexion.execute(
        "select to_regclass('public.migraciones') is not null"
    ).fetchone()[0]

    if not existe:
        return set()

    return {fila[0] for fila in conexion.execute("select nombre from migraciones").fetchall()}


def main() -> int:
    argumentos = sys.argv[1:]
    solo_estado = "--estado" in argumentos

    url = None
    if "--url" in argumentos:
        url = argumentos[argumentos.index("--url") + 1]
    else:
        from app.config import config

        url = config.database_url

    # El destino se muestra sin credenciales: este comando se pega en chats y
    # en tickets.
    visible = url.split("@")[-1] if "@" in url else url
    print(f"Base: {visible}\n")

    archivos = sorted(CARPETA.glob("*.sql"))
    if not archivos:
        print(f"No hay migraciones en {CARPETA}")
        return 1

    with psycopg.connect(url, connect_timeout=30) as conexion:
        ya = aplicadas(conexion)
        faltan = [a for a in archivos if a.name not in ya]

        for archivo in archivos:
            marca = "pendiente" if archivo in faltan else "aplicada "
            print(f"  {marca}  {archivo.name}")

        if not faltan:
            print("\nLa base está al día.")
            return 0

        if solo_estado:
            print(f"\nFaltan {len(faltan)}. Corre sin --estado para aplicarlas.")
            return 0

        # Recién acá se crea la tabla de control: --estado no escribe nada.
        conexion.execute(TABLA)
        conexion.commit()

        print()
        for archivo in faltan:
            print(f"Aplicando {archivo.name}...", end=" ", flush=True)
            try:
                conexion.execute(archivo.read_text(encoding="utf-8"))
                conexion.execute(
                    "insert into migraciones (nombre) values (%s)", (archivo.name,)
                )
                conexion.commit()
                print("ok")
            except Exception as exc:
                conexion.rollback()
                print("FALLÓ")
                print(f"\n  {type(exc).__name__}: {exc}")
                print(f"\n  Quedó sin aplicar desde {archivo.name}.")
                print("  Corrige el archivo y vuelve a correr: lo anterior se conserva.")
                return 1

    print(f"\nListo: {len(faltan)} migración(es) aplicada(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

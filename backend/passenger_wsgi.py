"""
Punto de entrada para Passenger (Python Selector de cPanel).

Passenger habla **WSGI** y FastAPI es **ASGI**: no se pueden conectar directo.
Traducir entre los dos es lo único que hace este archivo, con el adaptador de
`asgi_wsgi.py`.

En un servidor propio esto no existe: ahí se levanta con
`uvicorn app.main:app`, que es ASGI nativo y más eficiente. Este adaptador es
el precio de correr en hosting compartido.

Este Passenger tiene una limitación que conviene saber antes de tocar nada:
**no tolera hilos de fondo**. Eso descartó `a2wsgi` (ver `asgi_wsgi.py`) y
también el pool de conexiones de psycopg (ver `app/db.py`). Si algún día la
app deja de arrancar sin dejar rastro en el log, ese es el primer sospechoso.

Configuración en cPanel → Setup Python App:

    Application root        la carpeta donde subiste `backend/`
    Application URL         api.simai.cl  (o el subdominio que uses)
    Application startup     passenger_wsgi.py
    Python version          3.10 o superior — el código usa `str | None`

Después, en la misma pantalla:

  1. "Configuration files" → agrega `requirements.txt` y ejecuta
     "Run Pip Install".
  2. "Environment variables" → carga las mismas del `.env`
     (DATABASE_URL, GOOGLE_*, SECRET_KEY, COOKIE_SECURE=true, FRONTEND_URL,
     PUBLIC_URL, CALLBACK_TOKEN, ADMIN_EMAILS, MOTOR_*). Las variables del
     panel ganan sobre el archivo, así que el `.env` no hace falta ahí — y es
     mejor no subirlo.
  3. "Restart" cada vez que cambies código o variables: Passenger cachea el
     proceso.
"""

from asgi_wsgi import ASGIaWSGI

from app.main import app as asgi_app

# Passenger busca exactamente este nombre.
#
# El adaptador es propio y no `a2wsgi`: esa librería deja la petición colgada
# bajo este Passenger, incluso con una app ASGI trivial. Ver asgi_wsgi.py.
application = ASGIaWSGI(asgi_app)

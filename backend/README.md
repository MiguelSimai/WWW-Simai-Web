# Backend — SimAI

FastAPI + Postgres. Resuelve tres cosas: el login con Google, el saldo de la
cuenta y el envío de expedientes al motor de procesamiento.

El navegador nunca recibe un token de Google: solo una cookie de sesión
`httpOnly` que JavaScript no puede leer.

## Puesta en marcha

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

copy .env.example .env          # y completa los valores

python migrar.py                # crea el modelo de datos

uvicorn app.main:app --reload --port 8000
```

## Cambiar de base de datos

El modelo vive en `migraciones/`, y cada base lleva la cuenta de lo que ya
aplicó en su propia tabla `migraciones`. Mudarse —de local a Azure, de Neon a
local— es esto:

```bash
# 1. apunta DATABASE_URL al destino nuevo en el .env
# 2. mira qué falta (no escribe nada)
python migrar.py --estado
# 3. aplícalo
python migrar.py
```

También se puede apuntar a otra base sin tocar el `.env`:

```bash
python migrar.py --url "postgresql://usuario:clave@servidor:5432/simai"
```

Nada más en el código conoce la base: todo pasa por `DATABASE_URL`.

**Para cambiar el modelo**, crea un archivo nuevo en `migraciones/` con el
número siguiente. No edites uno ya aplicado: las bases que lo corrieron no lo
volverán a correr y quedarían distintas entre sí. Un cambio nuevo es siempre un
archivo nuevo.

Las migraciones se aplican en orden de nombre, cada una en su transacción: si
una falla, esa queda sin aplicar y las anteriores se conservan.

## Credenciales de Google

1. Entra a <https://console.cloud.google.com/apis/credentials>
2. Crea un proyecto (o usa uno existente)
3. **Crear credenciales → ID de cliente de OAuth 2.0 → Aplicación web**
4. En *URI de redirección autorizados* agrega exactamente:
   `http://localhost:8000/api/auth/retorno`
5. Copia el *client ID* y el *client secret* al `.env`

En producción, repite el paso 4 con la URL real y actualiza `GOOGLE_REDIRECT_URI`.

La ruta se llama `/retorno` a propósito, y no `/callback/google`: Chrome marcaba
la URL anterior como "Sitio peligroso" por su detección en tiempo real. El
motivo está explicado en `app/auth_router.py`. Si la renombras, los tres lugares
—la ruta, `GOOGLE_REDIRECT_URI` y Google Cloud Console— tienen que coincidir
exactamente.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/auth/login/google` | Redirige a Google |
| GET | `/api/auth/retorno` | Valida, crea la sesión, deja la cookie y vuelve al portal |
| GET | `/api/auth/me` | Devuelve el usuario, o 401 si no hay sesión |
| POST | `/api/auth/logout` | Revoca la sesión y borra la cookie |
| POST | `/api/cuenta/contratar/{pack_id}` | Acredita el saldo de un pack |
| POST | `/api/solicitudes` | Recibe un expediente y lo despacha al motor |
| GET | `/api/solicitudes` | Los expedientes del usuario, 25 por página |
| GET | `/api/solicitudes/{codigo}` | Uno, con el detalle de sus documentos |
| GET | `/api/solicitudes/excel` | Planilla de un rango (`?desde=&hasta=` en YYYY-MM-DD) |
| POST | `/api/callbacks/expediente` | Recibe el resultado desde N8N |

Los GET devuelven camelCase, que es lo que consume el TypeScript del front.
Pedir una solicitud ajena responde 404, no 403: no se confirma que el código
exista.

## Expedientes

Un expediente es lo que en el escritorio del cliente es una carpeta: su número
de solicitud por nombre y un set de documentos dentro.

```
297541/                          →  una solicitud
  CARTA COMPROMISO DE PAGO.pdf   →  un documento, una llamada al gateway
  CAV FINAL.pdf                  →  otra
  CONTRATO.pdf                   →  otra
  PAGARE.pdf                     →  otra
```

Llega completo en una petición y se despacha documento por documento. El
número de la carpeta viaja al motor como `id_solicitud_externa`, así que el
mismo número cruza los dos sistemas. Un archivo suelto es un expediente de un
documento, y usa el código de la solicitud como referencia.

El orden de `solicitudes_router.py` no es casual:

1. **Validar y medir todo** antes de tocar nada. Si un documento no sirve, el
   expediente no entra: es preferible a dejarlo a medio procesar
2. **Reservar el saldo.** Si no alcanza, nadie gastó nada en Azure
3. **Registrar el expediente** en `iagw_n8n_procesos_externo`, la única
   escritura del portal en la base del motor (ver `motor_db.py`). Sin esa fila
   N8N no sabe cuándo el expediente está completo y el resultado nunca llega
4. **Despachar** los documentos

Si el paso 3 falla, se devuelve la reserva y no se despacha nada. Si el motor
rechaza un documento, el resto sigue y ese no se cobra. Si rechaza todos, se
devuelve todo.

## El callback de N8N

El motor manda cada documento a N8N. N8N espera a que el expediente esté
completo, lo consolida y hace un POST acá. **El portal recibe un callback por
expediente, no uno por documento.**

```
POST /api/callbacks/expediente
X-Callback-Token: <CALLBACK_TOKEN>

{
  "numero_solicitud": "297541",
  "estado": "procesado",
  "respuesta_ia": { ... },
  "error_ia": null,
  "documentos": [
    {
      "id_transaccion_cliente": "DOC-1A2B3C4D",
      "estado": "procesado",
      "respuesta_ia": { ... },
      "confianza": 0.94,
      "error_ia": null
    }
  ]
}
```

Solo `numero_solicitud` es obligatorio. `documentos` es opcional pero
recomendado: sin él, todos los documentos toman el estado global y se cobra el
expediente completo; con él, cada uno se cierra con lo suyo y lo que falló se
devuelve.

Los nombres son los que ya usa el stack —los del payload que capa 3 manda a
N8N y los que arma su `Code Consolidar`—, y además se aceptan alias
(`id_externo`, `datos`, `resultado`, `error`…). Ver `_ALIAS_*` en
`callbacks_router.py`.

**Confianza**: se acepta en 0..1 o en 0..100 y se normaliza. Bajo 75 el
resultado queda en `revisar` en vez de `completada`.

**Idempotente**: N8N reintenta con backoff, y un expediente ya cerrado
responde 200 sin volver a cobrar. El índice
`movimientos_unicos_por_solicitud` lo garantiza también en la base.

### El flujo N8N hay que clonarlo, no reusarlo

De `IA-Core (Callback Homologador)` sirve tal cual la mitad genérica: el
webhook, la normalización, el conteo del expediente
(`Valida solicitud completada` + `If Todos Procesados`), la consolidación y los
reintentos. Lo que es de otro negocio y hay que reemplazar: `Constructor Json`,
`HTTP Request Legacy` con su `Token Insert`, y el `Switch Rutas`.

En el clon, la entrega es un POST a este endpoint con el token compartido.

## Decisiones

**Sesiones en Postgres, no JWT.** Un JWT sigue siendo válido hasta que expira
aunque desactives al usuario. Con sesiones en base puedes cortar el acceso al
instante, y mostrarle al usuario sus sesiones abiertas.

**Solo se guarda el hash del token.** Si te roban la base, esos hashes no
sirven para entrar. Mismo criterio que una contraseña.

**La identidad se enlaza por el `sub` de Google, no por el correo.** Un correo
puede cambiar de dueño dentro de una empresa; el `sub` es permanente. Ver
`usuarios.py` para las reglas de enlace.

**PKCE activado.** Sin él, quien intercepte el `code` puede canjearlo por un
token.

## HTTPS obligatorio

La API respondía también por HTTP plano: `http://api.simai.cl/api/salud`
devolvía 200 en vez de mandar a HTTPS. La cookie de sesión lleva `Secure`, así
que nunca viajó en claro; lo que quedaba expuesto era el resto —los documentos
que se suben y las respuestas— ante quien estuviera en la misma red.

Hoy redirigen **dos capas**, y conviene entender por qué hay dos.

La del servidor es el switch **"Force HTTPS Redirect"** de cPanel (Dominios →
api.simai.cl). Estuvo encendido un buen tiempo sin hacer nada: la API contestaba
200 en claro igual. Lo que lo destrabó fue borrar un `.htaccess` del front que
alguien había descomprimido por error dentro de la carpeta de la aplicación
—`simai-api/`, junto con todo el build de Angular—; al sacarlo de ahí y
reiniciar, el switch empezó a aplicar su 301. La relación causa-efecto no está
confirmada al cien por ciento, pero el orden de los hechos fue ese.

La de la aplicación es `RedireccionHTTPS`, en `app/main.py`, gobernada por la
variable `FORZAR_HTTPS`. Está porque la del servidor ya falló una vez en
silencio —el panel decía que estaba activa y no lo estaba— y eso no se nota
hasta que alguien lo mide desde fuera. Si vuelve a caerse, la aplicación sigue
redirigiendo. Responde 308 y no 301 a propósito: un 301 convierte el POST del
callback de N8N en un GET sin cuerpo.

En la práctica la del servidor atiende primero y la de la aplicación casi nunca
llega a ejecutarse. Es una red de seguridad, y cuesta una comparación de texto
por petición.

Encenderla es en dos pasos, y el orden importa. Si el servidor informara mal el
esquema de la conexión, la app redirigiría a HTTPS algo que YA es HTTPS y la
API quedaría en un bucle. Por eso primero se comprueba:

```bash
# 1. Con FORZAR_HTTPS todavía apagado, subir el código y reiniciar la app.
curl -sS https://api.simai.cl/api/salud    # {"ok":true,"esquema":"https"}  <- tiene que decir https
curl -sS http://api.simai.cl/api/salud     # {"ok":true,"esquema":"http"}

# 2. Recién ahí, FORZAR_HTTPS=true en las variables de la app y reiniciar.
curl -sS -o /dev/null -w "%{http_code} %{redirect_url}\n" http://api.simai.cl/api/salud
# 308 https://api.simai.cl/api/salud
```

Si algo saliera mal, se apaga poniendo `FORZAR_HTTPS=false` en el panel y
reiniciando: no hay que volver a subir archivos.

Antes de encenderla conviene revisar que nada llame a la API por HTTP, porque
el redirect agrega un salto a cada petición: `PUBLIC_URL` y
`GOOGLE_REDIRECT_URI` en las variables de la app, la URL del callback en el
flujo de N8N y `apiUrl` en `src/environments/environment.ts`.

## HSTS

`Strict-Transport-Security: max-age=31536000; includeSubDomains`, en los dos
dominios.

Es lo que la redirección sola no puede dar. Con solo el 301, la primera
petición del día sigue saliendo en claro y alguien en la misma red puede
quedarse con ella antes de que la respuesta llegue. Con HSTS el navegador ni
siquiera la manda: recuerda que este dominio es HTTPS y reescribe la URL él
mismo.

Cada dominio la sirve por su lado, y no por gusto:

- **simai.cl** desde `public/.htaccess`, que Angular copia al `dist` en cada
  build.
- **api.simai.cl** desde `CabecerasSeguridad`, en `app/main.py`, porque bajo
  Passenger un `.htaccess` no llega a aplicarse.

El `includeSubDomains` de simai.cl ya alcanza a api.simai.cl; que la API mande
además la suya es a propósito, para que no dependa de que el visitante haya
pasado antes por el front.

Dos cosas que hay que tener presentes, porque HSTS no se deshace apretando un
botón:

- **El certificado pasa a ser crítico.** Si venciera sin renovarse, el sitio
  queda inaccesible: el navegador ya no ofrece el "continuar de todos modos".
  Vale la pena mirar de vez en cuando que el AutoSSL de cPanel esté renovando.
- **Para desactivarlo** no basta con quitar la cabecera: los navegadores que ya
  la vieron la tienen guardada por un año. Hay que publicar `max-age=0` y
  esperar a que cada uno vuelva a pasar.

No se usa `preload`, que metería el dominio en una lista que los navegadores
traen de fábrica y de la que salir toma meses.

## La documentación de la API no es pública

`/docs`, `/redoc` y `/openapi.json` salen solo si `DOCS_PUBLICAS` lo dice, y por
defecto no lo dice. Estuvieron abiertos un tiempo: ese JSON es el mapa completo
—las rutas de administración, el endpoint del callback, la forma exacta de cada
petición— y no hay motivo para regalarlo.

Apagado, FastAPI ni siquiera registra las rutas, así que pedirlas devuelve el
mismo 404 que cualquier dirección inventada: no se confirma que existan.

En local conviene `DOCS_PUBLICAS=true` en el `.env`, que es para lo que sirve.

## Antes de publicar

- [ ] `COOKIE_SECURE=true` y el redirect a HTTPS puesto (ver arriba)
- [ ] `SECRET_KEY` aleatorio y fuera del repositorio
- [ ] `DOCS_PUBLICAS` sin definir o en `false`
- [ ] Front y API bajo el mismo dominio (`simai.cl` y `api.simai.cl`), para que
      la cookie `SameSite=Lax` viaje sin problemas
- [ ] Limitar intentos por IP en `/api/auth/login/google`
- [ ] Tarea periódica que borre sesiones vencidas

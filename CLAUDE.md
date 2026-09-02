# SimAI — simai.cl

Sitio y portal de **SimAI**, empresa de servicios de inteligencia artificial aplicada.
El nombre viene de *Simple* + *AI*: IA que se contrata y se usa el mismo día, sin
proyecto de implementación de por medio. Proyecto personal e independiente.

Cuatro servicios, todos con el mismo saldo y la misma tarifa por API o por portal:

| Servicio | Se cobra por |
|---|---|
| Transcripción de audio y video | minuto de audio |
| Análisis de documentos | página |
| Análisis de conversaciones | minuto analizado |
| Automatización de procesos | ejecución |

Modelo comercial: **pago por uso**. El cliente carga saldo, se descuenta a medida que
procesa, no hay licencias por usuario ni mínimo mensual.

SimAI vende el mismo motor por **dos vías**, con el mismo saldo y la misma tarifa: una API
para que el cliente integre desde sus sistemas, y el portal para que suba archivos a mano.
Hoy existe el portal; la API es el siguiente objetivo y reusa el mismo núcleo cambiando solo
la autenticación.

## Estado actual

El repositorio tiene **dos piezas**: el front Angular en la raíz y un backend FastAPI en
[backend/](backend/).

Lo que ya funciona de punta a punta:

- **Login con Google** (OAuth 2.0 + PKCE), sesión en Postgres y cookie `httpOnly`
- **Saldo y contratación** — `POST /api/cuenta/contratar/{pack_id}` acredita el pack
- **Envío de expedientes** — subir carpetas o archivos, medirlos, reservar el saldo y
  despacharlos al motor documento por documento
- **Panel real** — expedientes con su estado, costo y documentos, con polling mientras haya
  algo en proceso
- **Administración** — `/admin`: alta de cuentas, servicios habilitados, mover usuarios,
  fusionar cuentas y plantillas de Excel

Lo que sigue pendiente:

- **La modalidad API.** Credenciales por cliente, consumo y documentación. Por eso el saldo,
  el cobro y las solicitudes viven en módulos que no saben de dónde viene la petición
- **No hay pasarela de pago.** `contratar` acredita el saldo directo. Cuando exista el
  cobro, ese endpoint debe crear la intención de pago y el saldo acreditarse recién en el
  webhook de confirmación, nunca ahí mismo
- **Nada se ha corrido contra el motor real.** Todo el circuito está verificado con dobles y
  con `MOTOR_SIMULADO=true`. Falta crear los procesos en la base del motor, apuntarles
  `id_proceso` reales en `cuenta_procesos` de cada cliente, y clonar el flujo N8N
- **Formatos.** El catálogo comercial ofrece video, Office y ZIP; el portal solo acepta lo
  que el motor procesa hoy (audio, PDF, imágenes). El resto está marcado como no disponible
- **Sin pantalla de detalle propia.** Los documentos se ven en un desplegable del panel; no
  hay `/solicitud/:codigo` ni descarga del resultado

## Cuentas: quién contrata

**Contrata la empresa, no la persona.** El saldo, los servicios habilitados y la plantilla del
Excel viven en `cuentas`; los usuarios pertenecen a una y comparten todo — incluidos los
expedientes, que son de la cuenta.

```
cuentas                       saldo · contratado_en
   │
   ├── usuarios               ana@acme.cl, pedro@acme.cl → mismo saldo
   │
   └── cuenta_procesos        qué servicios tiene, y con qué proceso del motor
         documentos  →  simai_doc_acme (id 7) · plantilla "Operaciones"
```

**`cuenta_procesos` es la pieza que hace multicliente al portal.** "Análisis de documentos" no
es un solo proceso del motor: el de créditos automotrices tiene su prompt y su `schema_salida`,
y el de facturas de otro cliente es otro proceso distinto. Antes había un mapa global
hardcodeado en `gateway_client`, que no aguantaba dos clientes.

Una fila ahí significa además que la cuenta **tiene contratado** ese servicio. Sin fila:
`/enviar` no lo ofrece, y el backend responde 403 si la petición llega igual. La pantalla guía,
el servidor decide — ver [cuentas.py](backend/app/cuentas.py).

`/api/auth/me` devuelve `servicios` con lo habilitado, y el front cruza esa lista con lo que el
motor puede procesar (`SERVICIOS_DISPONIBLES`). Una cuenta sin servicios ve un aviso en vez de
una pantalla que va a rechazar todo.

Al entrar por primera vez, cada usuario recibe su propia cuenta. Juntar a varias personas bajo
la cuenta de su empresa se hace desde la administración: deducirlo por el dominio del correo
mezclaría saldos de gente sin relación (`gmail.com`, por ejemplo).

### Administración

Hay **dos** consolas, y conviene no confundirlas:

| Consola | Qué administra |
|---|---|
| **IA-ADMIN** (proyecto aparte) | El motor: procesos, prompts, `schema_salida`, catálogos, homologación |
| **`/admin`** (este portal) | Lo comercial: cuentas, saldo, servicios habilitados, usuarios |

El orden al incorporar un cliente es: primero el proceso en IA-ADMIN —que devuelve su código y
su id—, y después en `/admin` se crea la cuenta y se le apunta ese proceso.

`/admin` evita tocar SQL para crear cuentas, habilitar servicios y mover usuarios entre
cuentas.

**Mover un usuario no mueve su saldo ni su historial**: quedan en la cuenta que deja. Para
consolidar de verdad hay que **fusionar** (`Absorber cuenta…`), que traspasa usuarios, saldo, la
marca de contratación (`contratado_en`), expedientes y movimientos en una transacción, y deja
la origen en cero. Es el caso típico de
alguien que entró por su cuenta, acumuló saldo y expedientes, y después hay que juntarlo con la
cuenta de su empresa.

Al fusionar, los servicios de la cuenta origen **no** se traspasan: apuntan a procesos del motor
que pueden no corresponder al cliente destino, así que se habilitan a mano.

Quién entra sale de **`ADMIN_EMAILS`** en el `.env`, no de la base: quién administra el producto
no debería poder cambiarse desde el producto mismo. Los endpoints responden **404** —no 403— a
quien no administra, así que la sección no se delata.

El guard del front es sólo comodidad de navegación: quien fuerce la URL verá la pantalla vacía,
porque el backend le responde 404 a cada llamada.

## Expedientes

La unidad del producto no es el archivo, es el **expediente**: lo que en el escritorio del
cliente es una carpeta con el número de solicitud por nombre.

```
297541/                          →  una solicitud (numero_cliente = 297541)
  CARTA COMPROMISO DE PAGO.pdf   →  un documento, una llamada al gateway
  CAV FINAL.pdf                  →  otra
  CONTRATO.pdf                   →  otra
  PAGARE.pdf                     →  otra
```

Un archivo suelto es un expediente de uno. Tres niveles, y cada uno existe en el mundo del
cliente:

| Nivel | Dónde vive |
|---|---|
| Carga | La pantalla `/enviar`; no se guarda |
| Solicitud | Tabla `solicitudes`. Una fila del panel. Unidad de cobro y de estado |
| Documento | Tabla `documentos`. Una llamada al motor |

**Cómo se asocia el número.** En el front, cada archivo llega con `webkitRelativePath`
(`297541/CONTRATO.pdf`) y se agrupa por la carpeta que lo contiene directamente —la última
del camino, no la primera—, así da igual si el cliente eligió `297541` o la carpeta que la
agrupa. Ver `carpetaDe()` en
[enviar.component.ts](src/app/pages/enviar/enviar.component.ts).

**Una petición HTTP por carpeta**, con sus documentos dentro: cincuenta expedientes de cuatro
son cincuenta subidas, no doscientas. Y el saldo se valida por expediente completo.

### El ciclo completo

```
/enviar          agrupa por carpeta
   │
POST /api/solicitudes        mide, reserva saldo, crea solicitud + documentos
   │
   ├→ iagw_n8n_procesos_externo   (base del motor) id_externo + cantidad_archivos
   │
   └→ POST /api/v1/solicitudes    del gateway, uno por documento
          entrada.id_solicitud_externa    = referencia del expediente
          metadata.id_transaccion_cliente = código del documento
   │
motor → N8N       espera el expediente completo y lo consolida
   │
POST /api/callbacks/expediente     cierra, ajusta el cobro, deriva el resumen
```

**El portal recibe un callback por expediente, no uno por documento**: la espera y la
consolidación las hace N8N, que ya tenía ese mecanismo.

### Cobro

**Reserva al enviar, ajuste al cerrar.** Se mide y se reserva el expediente completo; si no
alcanza el saldo se rechaza con 402 antes de gastar en Azure. Al cerrarse, lo que falló se
devuelve: no se cobra lo que no se entregó.

Las unidades **las mide el servidor** ([medicion.py](backend/app/medicion.py)): páginas con
`pypdf`, minutos con `mutagen`. No se toman del navegador, porque el cliente puede mentir, ni
del motor, porque quien factura es el portal. El precio sale de
[backend/app/catalogo.py](backend/app/catalogo.py), que es la fuente de verdad del cobro — el
catálogo del front es para mostrar, y los dos tienen que decir lo mismo.

Cada movimiento queda en `movimientos_saldo`, así que la cifra de `cuentas.saldo` siempre se
puede explicar.

### Estados

El motor maneja `recibido | encolado | procesando | procesado | error | rechazado`; el portal
los cuatro de `modelos.ts`. Un documento cae en `revisar` cuando su confianza queda bajo 75
(`UMBRAL_REVISION`). El estado del expediente se deriva de sus documentos: `procesando`
mientras quede alguno en curso, después `error` si todos fallaron, `revisar` si alguno quedó
por revisar, y `completada` si todos salieron bien. Un documento fallado de cuatro no hace
fracasar el expediente.

### El entregable: la planilla

Lo que el cliente espera al final es un **Excel con una fila por expediente**, no el JSON del
motor. Se descarga desde el panel por rango de fechas, y sólo incluye expedientes cerrados:
meter los que están en proceso con las celdas vacías haría creer que el análisis no encontró
nada.

Las columnas **no son genéricas** — el cliente de créditos automotrices espera
`NumeroOperacion`, `Patente`, una columna por tipo de documento y `Observaciones`; otro
esperará otra cosa. Por eso viven en la tabla `plantillas_excel`, una por servicio, y agregar
un cliente no es un despliegue. Cada columna declara de dónde sale su valor:

| `origen` | De dónde | Ejemplo de `campo` |
|---|---|---|
| `solicitud` | Una columna de `solicitudes` | `numero_cliente`, `estado`, `costo` |
| `consolidado` | El `respuesta_ia` del expediente, con rutas por punto | `patente`, `deudor.rut` |
| `documento` | El documento cuyo nombre contenga `patron` | `estado`, `presencia`, `resultado` |

Detalles que importan al leer [excel.py](backend/app/excel.py): el matcheo de documento ignora
tildes y mayúsculas (`Pagaré (1).PDF` cuenta como `PAGARE`); un documento ausente deja la celda
**vacía**, no un "No", para no confundirlo con un resultado del análisis; una lista se une con
"; " en una celda; y un servicio sin plantilla cae a `COLUMNAS_GENERICAS`.

### Probar sin el motor

`MOTOR_SIMULADO=true` en el `.env` del backend: no llama al gateway ni escribe en su base. Se
puede probar todo el portal —subir, validar, medir, cobrar, listar— y los expedientes quedan
en `procesando` para siempre, porque nadie manda el callback. Mismo espíritu que `AuthMock`:
por defecto está apagado, así que si nadie lo enciende el portal intenta trabajar de verdad y
falla ruidosamente.

## Autenticación

El navegador **nunca** recibe un token de Google: solo una cookie de sesión `httpOnly` que
JavaScript no puede leer. Para saber quién eres, el front se lo pregunta al servidor.

El front tiene dos implementaciones tras la interfaz [core/auth.ts](src/app/core/auth.ts),
inyectadas por el token `AUTH`:

| Implementación | Cuándo |
|---|---|
| [auth.http.ts](src/app/core/auth.http.ts) | Real, contra el backend. Es la de ambos entornos |
| [auth.mock.ts](src/app/core/auth.mock.ts) | Simulada, para trabajar sin levantar el backend |

Cuál se usa lo decide el archivo de entorno. `environment.ts` (producción) es el valor **por
defecto** a propósito: si el `fileReplacements` fallara, la app intenta autenticar de verdad
y falla ruidosamente, en vez de dejar entrar a cualquiera en silencio. El build de producción
ni siquiera compila la simulada.

Para desarrollar sin backend: cambia `AuthHttp` por `AuthMock` en
[environment.development.ts](src/environments/environment.development.ts) y reinicia `npm start`.

Piezas relacionadas:

- [core/api.interceptor.ts](src/app/core/api.interceptor.ts) — agrega `withCredentials` a las
  llamadas al backend (sin él el navegador no manda cookies cross-origin) y ante un 401 lleva a
  `/ingresar` con `volver`. Excluye `/api/auth/me`, que responde 401 de forma rutinaria a quien
  no ha entrado
- `provideAppInitializer` en [app.config.ts](src/app/app.config.ts) — pregunta por la sesión
  **antes** de mostrar nada, así el guard decide sin esperas y el header no parpadea
- [core/sesion.guard.ts](src/app/core/sesion.guard.ts) — puede ser síncrono gracias a lo
  anterior. Es comodidad de navegación, no control de seguridad: la autorización real se valida
  en el servidor en cada petición

### Decisiones del backend

Están explicadas en [backend/README.md](backend/README.md); en resumen:

- **Sesiones en Postgres, no JWT** — un JWT sigue siendo válido hasta que expira aunque
  desactives al usuario; con sesiones en base cortas el acceso al instante
- **Solo se guarda el hash del token** — si roban la base, esos hashes no sirven para entrar
- **La identidad se enlaza por el `sub` de Google, no por el correo** — un correo puede cambiar
  de dueño dentro de una empresa; el `sub` es permanente
- **PKCE activado** — sin él, quien intercepte el `code` puede canjearlo por un token
- **Los montos de los packs viven en el servidor** — el cliente elige *qué* pack, nunca *cuánto*
  vale, o cualquiera se acreditaría un millón editando la petición

## Stack

**Front**: Angular 19 standalone (sin NgModules) · TypeScript strict · SCSS · Karma + Jasmine.
Sin librería de UI ni de estado: todo es HTML/SCSS propio. Locale `es-CL` registrado en
[app.config.ts](src/app/app.config.ts), así que `date` y `currency` salen en formato chileno.

**Backend**: FastAPI · psycopg 3 **sin pool** · Authlib (OAuth) · **Azure Database for
PostgreSQL** (`simai-db`). `truststore`
se inyecta
**antes** de cualquier import que arme un contexto TLS: hace falta cuando un antivirus con
inspección web, un proxy corporativo o una VPN firma con su propio certificado raíz — está en el
almacén del sistema pero nunca en `certifi`, y sin esto las llamadas a Google fallan con
`CERTIFICATE_VERIFY_FAILED`.

No hay pool de conexiones ni `lifespan`: los dos levantan hilos de fondo, y bajo Passenger esos
hilos dejan el proceso colgado (ver **Despliegue**). Se abre una conexión por petición.

Con Neon eso no se notaba, porque su *pooler* amortiguaba. **Azure no trae nada equivalente
encendido**, así que hoy cada petición paga el saludo TCP+TLS completo. Habilitar el PgBouncer
integrado (parámetro `pgbouncer.enabled`, puerto 6432) es la mejora pendiente más concreta.

## Comandos

```bash
# Front
npm start        # ng serve  → http://localhost:4200 (hot reload)
npm run build    # build de producción → dist/portal-solicitudes
npm test         # tests unitarios en Chrome (Karma)

npx ng test --watch=false --browsers=ChromeHeadless   # una pasada, sin ventana
```

```bash
# Backend (primera vez)
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # y completa los valores
python migrar.py                # crea el modelo de datos

uvicorn app.main:app --reload --port 8000
```

**Modelo de datos: migraciones, no un schema suelto.** Vive en `backend/migraciones/`, y cada
base lleva la cuenta de lo que aplicó en su propia tabla `migraciones`. Cambiar de base —local,
Azure, otra— es apuntar `DATABASE_URL` al destino y correr `migrar.py`. `migrar.py --estado`
muestra qué falta sin escribir nada.

Para cambiar el modelo, un archivo nuevo con el número siguiente. **No editar uno ya
aplicado**: las bases que lo corrieron no lo repiten y quedarían distintas entre sí.

Las credenciales de Google se crean en <https://console.cloud.google.com/apis/credentials>
(*ID de cliente de OAuth 2.0 → Aplicación web*), con
`http://localhost:8000/api/auth/retorno` como URI de redirección autorizado — exacto, o Google
rechaza el intercambio. La ruta se llama `/retorno` y no `/callback/google` a propósito: Chrome
marcaba la anterior como "Sitio peligroso". Si se renombra, tienen que coincidir los tres
lugares: la ruta, `GOOGLE_REDIRECT_URI` y Google Cloud Console.

Para verificar si el dev server ya está arriba sin abrir el navegador:

```bash
netstat -ano | grep :4200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:4200/
```

Nota: `ng serve` escucha solo en IPv6 (`::1`). `localhost` funciona; `127.0.0.1` no.
Usa `ng serve --host 0.0.0.0` si necesitas IPv4 o acceso desde la red.

## Despliegue

**En producción.** El sitio estático en `simai.cl` y el backend en `api.simai.cl`, ambos en
hosting compartido con cPanel (V2network) bajo el *Python Selector* (Passenger), contra
**Azure Database for PostgreSQL**. `environment.ts` —el de producción— apunta a
`https://api.simai.cl`.

| Pieza | Carpeta en el hosting |
|---|---|
| Backend (*Application root*) | `/home/ingetecn/simai-api` |
| Front (raíz web de simai.cl) | `/home/ingetecn/simai.cl` |

**Las credenciales viven en las variables de entorno del Python App, no en un `.env`.** Las del
panel ganan sobre el archivo, así que en el servidor no hay secretos en disco. Lo que cambia
respecto del entorno local: `COOKIE_SECURE=true`, `FRONTEND_URL=https://simai.cl` y
`GOOGLE_REDIRECT_URI=https://api.simai.cl/api/auth/retorno` —que además hay que registrar en
Google Cloud Console—. Tras tocar cualquier variable, **Restart**: Passenger cachea el proceso.

**La IP de salida del hosting es `208.91.188.116`**, y es la que Azure tiene que autorizar en su
firewall. No la des por sentada mirando cPanel: la que el panel muestra es la de *entrada*, y no
tiene por qué coincidir. La salida al puerto 5432 está confirmada abierta desde V2network.

**Front.** `npm run build` deja el sitio en `dist/portal-solicitudes/browser`; se sube tal cual,
con [public/.htaccess](public/.htaccess) incluido: fuerza HTTPS —la cookie va con `Secure`, así
que sobre HTTP no hay login—, manda cualquier ruta desconocida a `index.html` (sin eso, entrar
directo a `/precios` da un 404 de Apache), cachea los `.js`/`.css` con hash para siempre y nunca
`index.html`, y agrega las cabeceras de seguridad.

**Backend.** Passenger habla **WSGI** y FastAPI es **ASGI**.
[passenger_wsgi.py](backend/passenger_wsgi.py) los une con
[asgi_wsgi.py](backend/asgi_wsgi.py), un adaptador propio: `a2wsgi` deja la petición colgada para
siempre bajo este Passenger. Los pasos de cPanel —application root, startup file, pip install,
variables de entorno, restart— están en el docstring de `passenger_wsgi.py`.

**Este Passenger no tolera hilos de fondo**, y eso explica tres decisiones que de otro modo
parecen arbitrarias: nada de `a2wsgi`, nada de `psycopg_pool` (ver [db.py](backend/app/db.py)) y
`main.py` sin `lifespan`. Con cualquiera de los tres el proceso arranca colgado: no responde y no
deja rastro en el log. Si la app deja de arrancar en silencio, ese es el primer sospechoso.

Dos scripts se ejecutan desde *Setup Python App → Ejecutar script python* y dejan su resultado en
un `.txt` al lado, porque la salida del panel a veces no se muestra:

- [diagnostico.py](backend/diagnostico.py) — usa la configuración real y prueba la conexión de
  punta a punta, incluida la autenticación
- [prueba_azure.py](backend/prueba_azure.py) — **no** lee la configuración: informa la IP de
  salida del hosting y si el puerto está abierto, sin tocar lo que sostiene el sitio. Se puede
  correr con producción arriba

Los dos responden la misma pregunta: si el problema es del código o de la red.

En un servidor propio nada de esto hace falta: `uvicorn app.main:app` es ASGI nativo, y volver al
pool de conexiones es cambiar sólo `db.py`.

## Rutas

| Ruta | Página | Notas |
|---|---|---|
| `/` | Landing | Anclas: `#servicios`, `#como-funciona`, `#pago-por-uso`, `#seguridad`, `#contacto` |
| `/precios` | Tarifas, calculadora, packs de saldo, contratación | Contratar acredita saldo vía `CuentaService` |
| `/ingresar` | Acceso | Acepta `?volver=` y `?error=sesion-expirada` |
| `/enviar` | Subida de archivos y carpetas | Protegida por `sesionGuard` |
| `/panel` | Expedientes del usuario, con sus documentos | Protegida por `sesionGuard` |
| `/admin` | Administración comercial: cuentas, servicios, usuarios, plantillas | `adminGuard`; sólo `ADMIN_EMAILS` |
| `**` | → `/` | Reemplazar por un 404 propio cuando exista |

En `/enviar` sólo se ofrecen los servicios con `disponible: true` (ver `SERVICIOS_DISPONIBLES`
en [core/catalogo.ts](src/app/core/catalogo.ts)): un servicio cuyo formato el motor no procesa
todavía se muestra en la landing y en precios, pero no acepta cargas.

En `/panel`, los documentos de un expediente se piden **al abrir el desplegable**, no con el
listado: la mayoría de las filas nunca se abre.

## Endpoints del backend

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/auth/login/google` | Redirige a Google |
| GET | `/api/auth/retorno` | Google vuelve aquí: valida, crea la sesión, deja la cookie y vuelve al portal |
| GET | `/api/auth/me` | Devuelve el usuario, o 401 si no hay sesión |
| POST | `/api/auth/logout` | Revoca la sesión y borra la cookie |
| POST | `/api/cuenta/contratar/{pack_id}` | Acredita el saldo del pack (`prueba`, `impulso`, `volumen`) |
| POST | `/api/solicitudes` | Recibe un expediente y lo despacha al motor |
| GET | `/api/solicitudes` | Los expedientes del usuario, 25 por página |
| GET | `/api/solicitudes/{codigo}` | Uno, con el detalle de sus documentos |
| GET | `/api/solicitudes/excel` | La planilla de resultados de un rango de fechas |
| POST | `/api/callbacks/expediente` | Recibe el resultado consolidado desde N8N |
| GET | `/api/salud` | Health check |
| — | `/api/admin/*` | Cuentas, procesos, usuarios, plantillas y catálogo (sólo `ADMIN_EMAILS`) |

Los GET devuelven camelCase, que es lo que consume el TypeScript. Pedir una solicitud ajena
responde 404, no 403: no se confirma que el código exista.

`GET /api/admin/catalogo` es el catálogo del servidor **para armar el formulario** de la
administración sin escribir ids a mano; no es el `GET /api/catalogo` público que resolvería la
duplicación de precios entre front y backend, que sigue pendiente.

El callback lo llama N8N, no el navegador: no pasa por CORS ni por la cookie, se autentica con
`CALLBACK_TOKEN` comparado con `compare_digest`, y es idempotente porque N8N reintenta. Sin
token configurado responde 503 — vacío significa deshabilitado, no abierto. El contrato está en
[backend/README.md](backend/README.md).

Tablas en `backend/migraciones/`: `cuentas` (saldo y `contratado_en`), `usuarios` (con
`cuenta_id`), `identidades` (PK compuesta `proveedor` + `sujeto`), `sesiones` (`token_hash` en
`bytea`), `cuenta_procesos`, `solicitudes`, `documentos`, `movimientos_saldo` y
`plantillas_excel`. `contratado_en` en `NULL` significa que la cuenta nunca cargó saldo: ese es
el criterio para mostrar la contratación en vez del panel vacío.

`usuarios.saldo` y `usuarios.contratado_en` siguen en la tabla pero **ya no se leen** — la
fuente es la cuenta. Quedaron para poder comparar si el traspaso de la migración 005 no cuadró;
borrarlas es una migración posterior.

`solicitudes.referencia_motor` es lo que viaja como `id_solicitud_externa` y es **única por
envío**: `297541-B178531E`, el número del cliente más el sufijo del código. Tiene que ser única
porque N8N cuenta las solicitudes del motor con ese valor contra `cantidad_archivos`; si dos
envíos la compartieran, el conteo sumaría los dos y el expediente no se consolidaría nunca. Y un
mismo número se reenvía en la práctica, cuando el cliente corrige un documento.

## Estructura

```
src/app/
  app.component.*        Shell: skip-link, <app-site-header>, <main><router-outlet>, <app-site-footer>
  app.config.ts          Router + locale es-CL + HttpClient con interceptor + AUTH + carga de sesión
  app.routes.ts          Rutas lazy; /enviar y /panel pasan por sesionGuard
  core/
    modelos.ts           Servicio, Solicitud, Usuario + mapas de estado a etiqueta/badge
    catalogo.ts          CATALOGO: única fuente de servicios y precios del sitio
    auth.ts              Interfaz Auth + token de inyección AUTH
    auth.http.ts         Sesión real contra el backend
    auth.mock.ts         Sesión SIMULADA (fuera del bundle de producción)
    api.interceptor.ts   withCredentials + reacción al 401
    sesion.guard.ts      CanActivateFn para /enviar y /panel
    admin.guard.ts       CanActivateFn para /admin; comodidad, la autorización es del backend
    admin.service.ts     ÚNICO punto de contacto con /api/admin
    cuenta.service.ts    Contratar pack; recarga la sesión para refrescar el saldo
    solicitudes-api.service.ts  ÚNICO punto de contacto con la API de solicitudes
    solicitudes.service.ts      Expedientes del panel + polling mientras haya algo en curso
  layout/
    site-header/         Nav + acciones según sesión; menú móvil con signal y cierre con Escape
    site-footer/
  pages/
    landing/  precios/  ingresar/  enviar/  panel/  admin/
  ui/
    logo/                <app-logo [conTexto]>: marca, SVG inline
    icon/                <app-icon [name]>: SVG 24×24 de trazo, tipado por IconName
src/environments/        environment.ts (producción, por defecto) y .development.ts
src/styles.scss          Tokens de diseño + primitivas globales
public/.htaccess         Apache: HTTPS, fallback a index.html, caché y cabeceras de seguridad
backend/
  migraciones/           El modelo de datos, numerado
  migrar.py              Lleva cualquier base al día
  passenger_wsgi.py      Arranque bajo Passenger (cPanel). Con uvicorn no se usa
  asgi_wsgi.py           Adaptador ASGI→WSGI propio, sin hilos de fondo
  diagnostico.py         ¿El hosting alcanza la base? Escribe diagnostico.txt
  prueba_azure.py        Igual, pero sin leer la config: corre con producción arriba
  schema.sql             Obsoleto: el modelo se mudó a migraciones/. No se ejecuta
  app/
    main.py              App, CORS con credenciales, SessionMiddleware, truststore
    auth_router.py       Flujo OAuth con Google
    cuenta_router.py     Contratación de packs (montos del lado servidor)
    solicitudes_router.py  Recibe expedientes y los lista
    callbacks_router.py  Entrada del resultado desde N8N
    cuentas.py           Qué servicios y qué proceso del motor tiene cada cuenta
    admin_router.py      Alta de clientes: cuentas, procesos, usuarios, plantillas
    gateway_client.py    ÚNICA pieza que conoce la API del motor
    motor_db.py          ÚNICA escritura en la base del motor
    medicion.py          Unidades a cobrar (pypdf, mutagen)
    catalogo.py          Precios y formatos — fuente de verdad del cobro
    resumen.py           Del JSON del motor a una frase para el panel
    excel.py             La planilla que descarga el cliente, según su plantilla
    dependencias.py      sesion_actual, compartida por los routers
    sesiones.py          Crear, leer y revocar sesiones
    usuarios.py          Reglas de enlace de identidad por `sub`
    db.py  config.py
```

Las piezas que hablan con el exterior están aisladas a propósito: si el contrato del gateway
cambia, se arregla en `gateway_client.py`; si cambia el esquema del motor, en `motor_db.py`. El
resto del portal no sabe que el motor existe.

## Convenciones

**Idioma.** Código, comentarios, nombres de dominio y UI en español. Los comentarios
explican el *porqué*, no el *qué*, y son escasos.

**Componentes.** Standalone con `imports: []` en el decorador. Estado y datos de plantilla
van como `protected readonly`. Inputs con `input()` / `input.required<T>()`, no `@Input()`.
Estado mutable con `signal()`, derivado con `computed()`. Plantillas usan el control flow
nuevo (`@for` con `track`, `@if`, `@switch`), nunca `*ngFor` / `*ngIf`.

**Formularios.** Reactive forms (`fb.nonNullable.group`). Los errores se muestran recién
después del primer envío, con un signal `enviado`, y se enlazan al campo por
`aria-describedby`.

**Llamadas HTTP.** Cada área tiene un único servicio que habla con el backend
(`SolicitudesApi`, `CuentaService`, `AuthHttp`). Los componentes no conocen URLs ni
`HttpClient`: si la API cambia de ruta o de nombres de campo, se toca solo ese servicio.

**Precios.** En el front todo sale de `CATALOGO`. No escribas un precio literal en una
plantilla ni en otro componente: la landing, la tabla de tarifas, la calculadora y el panel
leen de ahí. Pero **el cobro se calcula en el servidor**, con
[backend/app/catalogo.py](backend/app/catalogo.py): lo que manda el navegador no es confiable.
Las dos copias tienen que decir lo mismo, y hoy se mantienen a mano — es el lugar más probable
de una discrepancia entre el precio que el cliente vio y el que se le cobró. Lo correcto es que
el front lea de `GET /api/catalogo`; queda pendiente.

Los montos de los packs de saldo también viven en el servidor, en `cuenta_router.py`: el
cliente elige *qué* pack, nunca *cuánto* vale.

**Mensaje del hero.** Decisión del dueño del proyecto: el hero habla de la marca y del
problema del cliente, **no** del catálogo de servicios ni del modelo de cobro. Eso aparece
más abajo, en `#servicios` y `#pago-por-uso`. Hay un test que lo protege
([landing.component.spec.ts](src/app/pages/landing/landing.component.spec.ts)): falla si el
hero vuelve a mencionar transcripción, documentos, automatización, API, saldo o un precio.

**Datos de contenido.** Cada bloque se declara como `readonly T[]` con su `interface` propia
(`Paso`, `Ventaja`, `Garantia`, `Pack`, `Pregunta`) y se recorre con `@for`. Al agregar una
sección, sigue ese patrón en vez de escribir el markup a mano.

**Estilos.** Todos los colores, espaciados, radios y sombras salen de las variables CSS de
[src/styles.scss](src/styles.scss) — nunca literales en los componentes. Las primitivas
compartidas (`.container`, `.section`, `.eyebrow`, `.section-title`, `.section-lead`, `.card`,
`.btn` y modificadores, `.badge`, `.field`, `.sr-only`, `.skip-link`) también viven ahí; el
SCSS de cada componente cubre solo lo suyo, con BEM (`.hero__title`, `.pack__monto`).

**Bloques oscuros.** Sobre grafito el violeta base no alcanza contraste. Un bloque oscuro
redefine `--c-brand: var(--c-brand-on-dark)` en su propia regla y todo lo que hay dentro
—incluido el logo— se adapta solo. Lo hacen `.hero` y `.site-footer__brand`.

**Accesibilidad.** Es un requisito, no un extra: skip-link, `:focus-visible` visible, iconos
decorativos con `aria-hidden`, gráficos con `role="img"` + `aria-label` descriptivo, estados
de filtro con `aria-pressed`, packs con `role="radio"`, y respeto a `prefers-reduced-motion`.

## Budgets

El build de producción limita 500 kB (warning) / 1 MB (error) para el bundle inicial y
10 kB / 20 kB por estilo de componente.

## Pendientes conocidos

- **Nunca se ha corrido contra el motor real**: falta crear los procesos en IA-ADMIN,
  cargar `cuenta_procesos` con el proceso real de cada cliente, y clonar
  el flujo N8N apuntando su entrega al callback del portal
- **Archivos grandes.** El documento viaja en base64 dentro del body, así que el tope es 25 MB
  y el catálogo promete hasta 500. Pasar a Blob Storage con `url_archivo` —que el gateway ya
  soporta— es cambiar `_entrada()` en `gateway_client.py`, y hay que hacerlo antes de prometer
  esos tamaños
- **[resumen.py](backend/app/resumen.py) adivina.** Deriva la frase del panel buscando campos
  por los nombres más probables, porque los `schema_salida` de los procesos SimAI no existen
  todavía. Al fijarlos, es el único módulo a tocar
- **Dos copias del catálogo** (front y backend) que hay que mantener sincronizadas a mano
- **No hay invitaciones**: cualquiera con cuenta de Google puede registrarse. Queda sin acceso a
  nada —cuenta propia y vacía— pero queda registrado, y hay que habilitarlo desde `/admin`
- Sin pantalla `/solicitud/:codigo` ni descarga del resultado
- Sin pasarela de pago: `contratar` acredita saldo sin cobrar
- El **resultado consolidado por expediente** —cruzar contrato con pagaré para detectar
  diferencias, que es lo que promete el catálogo— lo arma N8N, no el portal. Hoy cada documento
  se procesa por separado
- El nombre del proyecto Angular sigue siendo `portal-solicitudes` (en `package.json`,
  `angular.json` y la carpeta de salida), y el `README.md` de la raíz sigue siendo el que generó
  el Angular CLI. Renombrar y reescribirlos es un cambio aparte
- Los precios del catálogo son de referencia: ajustarlos antes de publicar
- Falta página 404 propia; hoy cualquier ruta desconocida redirige al home
- Enlaces de privacidad y términos apuntan a `#`
- **Sin PgBouncer.** Azure no lo trae encendido y `db.py` no tiene pool, así que cada petición
  paga el saludo TCP+TLS. Se habilita con el parámetro `pgbouncer.enabled` y el puerto 6432
- **Firewall de Azure por revisar.** El hosting conecta sin que su IP esté autorizada
  explícitamente, lo que sugiere una regla demasiado amplia. Hay que dejar sólo
  `208.91.188.116` y la IP de desarrollo
- De la lista de [backend/README.md](backend/README.md) siguen abiertos: límite de intentos por
  IP en el login, y una tarea periódica que borre sesiones vencidas. El resto —HTTPS,
  `COOKIE_SECURE=true`, `SECRET_KEY` fuera del repo, front y API en el mismo dominio— ya está

-- Expedientes, sus documentos y el movimiento del saldo.

-- Un expediente enviado por el cliente: lo que en su escritorio es una
-- carpeta. El nombre de esa carpeta es su número de solicitud —el que usa en
-- sus propios sistemas— y queda en `numero_cliente`.
--
-- Es la unidad que el cliente reconoce y la unidad de cobro: se mide y se
-- reserva el expediente completo, no documento por documento.
--
-- Un archivo suelto, sin carpeta, es un expediente de un documento.
--
-- `estado` son los cuatro valores que entiende el portal, no los del motor.
-- El de la solicitud se deriva de sus documentos: procesando mientras quede
-- alguno en curso; después error si todos fallaron, revisar si alguno quedó
-- por revisar, y completada si todos salieron bien.
create table if not exists solicitudes (
  id              uuid primary key default gen_random_uuid(),
  codigo          text unique not null,
  usuario_id      uuid not null references usuarios(id) on delete cascade,
  servicio        text not null,
  -- Número de solicitud del cliente, tomado del nombre de la carpeta. Null
  -- cuando subió un archivo suelto.
  numero_cliente  text,
  -- Lo que viajó al motor como id_solicitud_externa: el número del cliente si
  -- lo hay, o el código de esta solicitud si no. Es la llave con que vuelve el
  -- resultado desde N8N, así que siempre tiene valor y es única.
  referencia_motor text unique not null,
  -- Suma de las unidades de sus documentos, y el costo en CLP. Mientras está
  -- en proceso el costo es la reserva; al cerrarse se ajusta a lo real.
  unidades        integer not null default 0,
  costo           bigint  not null default 0,
  estado          text    not null default 'procesando',
  -- Resultado consolidado del expediente, tal como lo entrega N8N, y su
  -- versión legible para el panel. Los resultados por documento van en
  -- `documentos`; esto es la mirada del conjunto.
  respuesta_ia    jsonb,
  resumen         text,
  error           text,
  creada_en       timestamptz not null default now(),
  cerrada_en      timestamptz,
  constraint solicitudes_estado_valido
    check (estado in ('procesando', 'completada', 'revisar', 'error'))
);

create index if not exists solicitudes_usuario_idx on solicitudes (usuario_id, creada_en desc);
create index if not exists solicitudes_estado_idx  on solicitudes (estado);
create index if not exists solicitudes_numero_idx  on solicitudes (usuario_id, numero_cliente);


-- Cada archivo del expediente. Es lo que se envía al motor: un documento, una
-- llamada al gateway, un callback de vuelta.
create table if not exists documentos (
  id             uuid primary key default gen_random_uuid(),
  solicitud_id   uuid not null references solicitudes(id) on delete cascade,
  -- Código propio del documento. Viaja al motor como id_transaccion_cliente y
  -- vuelve en el callback: es la vía para saber qué documento se cerró.
  codigo         text unique not null,
  archivo        text not null,
  unidades       integer not null default 0,
  costo          bigint  not null default 0,
  estado         text    not null default 'procesando',
  -- Lo asigna el gateway al aceptar la solicitud. Sirve para cruzar este
  -- documento con los logs del motor.
  correlation_id uuid,
  -- Resultado tal como lo devuelve el motor, y su versión legible.
  respuesta_ia   jsonb,
  resumen        text,
  confianza      numeric(5, 2),
  error          text,
  creado_en      timestamptz not null default now(),
  cerrado_en     timestamptz,
  constraint documentos_estado_valido
    check (estado in ('procesando', 'completada', 'revisar', 'error'))
);

create index if not exists documentos_solicitud_idx on documentos (solicitud_id);
create unique index if not exists documentos_correlation_idx
  on documentos (correlation_id) where correlation_id is not null;


-- Cada movimiento del saldo, para que la cifra de `usuarios.saldo` siempre se
-- pueda explicar. `monto` es positivo cuando entra plata (carga de un pack,
-- devolución de una reserva) y negativo cuando sale (reserva de un trabajo).
--
-- La suma de los movimientos de un usuario debe cuadrar con su saldo.
create table if not exists movimientos_saldo (
  id            uuid primary key default gen_random_uuid(),
  usuario_id    uuid not null references usuarios(id) on delete cascade,
  solicitud_id  uuid references solicitudes(id) on delete set null,
  tipo          text not null,
  monto         bigint not null,
  detalle       text,
  creado_en     timestamptz not null default now(),
  constraint movimientos_tipo_valido
    check (tipo in ('carga', 'reserva', 'ajuste', 'devolucion'))
);

-- Un expediente reserva una vez y ajusta una vez. El índice hace que un
-- callback repetido —N8N reintenta con backoff— no pueda cobrar dos veces por
-- el mismo concepto.
create unique index if not exists movimientos_unicos_por_solicitud
  on movimientos_saldo (solicitud_id, tipo)
  where solicitud_id is not null and tipo in ('reserva', 'ajuste');

create index if not exists movimientos_usuario_idx  on movimientos_saldo (usuario_id, creado_en desc);
create index if not exists movimientos_solicitud_idx on movimientos_saldo (solicitud_id);

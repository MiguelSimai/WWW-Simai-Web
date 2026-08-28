-- Autenticación: quién entra al portal y cómo se sostiene su sesión.

create extension if not exists citext;
create extension if not exists "pgcrypto";   -- para gen_random_uuid()

-- Persona que entra al portal.
create table if not exists usuarios (
  id                uuid primary key default gen_random_uuid(),
  email             citext unique not null,
  nombre            text not null,
  creado_en         timestamptz not null default now(),
  ultimo_acceso_en  timestamptz
);

-- Cuenta externa con la que se autentica (Google hoy, Microsoft mañana).
-- Se enlaza por el `sub` del proveedor, NUNCA por el correo: el correo puede
-- cambiar de dueño dentro de una empresa, el `sub` no.
create table if not exists identidades (
  usuario_id  uuid not null references usuarios(id) on delete cascade,
  proveedor   text not null,
  sujeto      text not null,
  creado_en   timestamptz not null default now(),
  primary key (proveedor, sujeto)
);

create index if not exists identidades_usuario_idx on identidades (usuario_id);

-- Sesión activa. Guardamos sólo el hash del token, igual que una contraseña:
-- si te roban la base, no sirven para entrar.
create table if not exists sesiones (
  id          uuid primary key default gen_random_uuid(),
  usuario_id  uuid not null references usuarios(id) on delete cascade,
  token_hash  bytea unique not null,
  creado_en   timestamptz not null default now(),
  expira_en   timestamptz not null,
  revocada_en timestamptz,
  ip          inet,
  user_agent  text
);

create index if not exists sesiones_usuario_idx on sesiones (usuario_id);
create index if not exists sesiones_expira_idx on sesiones (expira_en);

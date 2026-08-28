-- La empresa como titular de lo contratado.
--
-- Hasta acá el saldo vivía en `usuarios`, así que dos personas de la misma
-- empresa habrían tenido saldos separados. Comercialmente contrata la empresa,
-- no la persona: el saldo, los procesos habilitados y la plantilla del Excel
-- pasan a la cuenta, y los usuarios pertenecen a una.

create table if not exists cuentas (
  id            uuid primary key default gen_random_uuid(),
  nombre        text not null,
  saldo         bigint not null default 0,
  contratado_en timestamptz,
  creada_en     timestamptz not null default now()
);

alter table usuarios add column if not exists cuenta_id uuid references cuentas(id);


-- Traspaso de los usuarios que ya existen: cada uno se queda con su propia
-- cuenta y su saldo intacto. Si después dos deben compartir cuenta, se
-- reasigna a mano; adivinar por dominio de correo sería peor que no hacerlo.
--
-- La cuenta reusa el id del usuario: hace el traspaso determinista e
-- idempotente, sin depender de emparejar por nombre —que fallaría con dos
-- personas homónimas o sin nombre—. Sólo aplica a este traspaso 1:1; las
-- cuentas nuevas llevan su propio id.
insert into cuentas (id, nombre, saldo, contratado_en)
select u.id, coalesce(nullif(u.nombre, ''), u.email::text), u.saldo, u.contratado_en
  from usuarios u
 where u.cuenta_id is null
   and not exists (select 1 from cuentas c where c.id = u.id);

update usuarios set cuenta_id = id where cuenta_id is null;

-- `usuarios.saldo` y `usuarios.contratado_en` quedan en la tabla pero ya no se
-- leen: la fuente es la cuenta. No se eliminan todavía para poder comparar si
-- algo no cuadró en el traspaso; borrarlas es una migración posterior.


-- Qué proceso del motor le corresponde a cada cuenta para cada servicio.
--
-- Es la pieza que faltaba: "Análisis de documentos" no es un solo proceso. El
-- de créditos automotrices de un cliente tiene su prompt y su schema_salida, y
-- el de facturas de otro cliente es otro proceso distinto en el motor.
--
-- Una fila acá significa además que la cuenta **tiene contratado** ese
-- servicio: sin fila, el portal no lo ofrece y lo rechaza.
create table if not exists cuenta_procesos (
  id             uuid primary key default gen_random_uuid(),
  cuenta_id      uuid not null references cuentas(id) on delete cascade,
  servicio       text not null,
  -- Lo que el gateway compara contra su tabla iagw_proceso. Los tres tienen
  -- que coincidir con la fila del motor o responde 404.
  tipo_servicio  text not null,
  proceso_codigo text not null,
  id_proceso     integer not null,
  -- Con qué plantilla se arma el Excel de este servicio. Null usa la genérica.
  plantilla_id   uuid references plantillas_excel(id),
  activo         boolean not null default true,
  creado_en      timestamptz not null default now()
);

create unique index if not exists cuenta_procesos_unico
  on cuenta_procesos (cuenta_id, servicio) where activo;

create index if not exists cuenta_procesos_cuenta_idx on cuenta_procesos (cuenta_id);


-- Las solicitudes pasan a ser de la cuenta. Se conserva `usuario_id` para
-- saber quién las subió, que es distinto de a quién se le cobran.
alter table solicitudes add column if not exists cuenta_id uuid references cuentas(id);

update solicitudes s
   set cuenta_id = u.cuenta_id
  from usuarios u
 where s.usuario_id = u.id
   and s.cuenta_id is null;

create index if not exists solicitudes_cuenta_idx on solicitudes (cuenta_id, creada_en desc);


-- Los movimientos también: el saldo que explican es el de la cuenta.
alter table movimientos_saldo add column if not exists cuenta_id uuid references cuentas(id);

update movimientos_saldo m
   set cuenta_id = u.cuenta_id
  from usuarios u
 where m.usuario_id = u.id
   and m.cuenta_id is null;

create index if not exists movimientos_cuenta_idx on movimientos_saldo (cuenta_id, creado_en desc);


-- La plantilla deja de ser una por servicio: ahora se elige por cuenta desde
-- cuenta_procesos, así que dos clientes pueden tener planillas distintas para
-- el mismo servicio.
drop index if exists plantillas_excel_servicio_activa;

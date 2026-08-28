-- Estado comercial del usuario.
--
-- `contratado_en` en NULL significa que nunca ha cargado saldo: ese es el
-- criterio para mostrarle la contratación en vez del panel vacío.

alter table usuarios add column if not exists saldo bigint not null default 0;
alter table usuarios add column if not exists contratado_en timestamptz;

-- RUT de la empresa, para facturar.
--
-- Va en `cuentas` y no en `usuarios` porque quien contrata es la empresa: la
-- factura se emite a la cuenta, no a la persona que subió los archivos.
--
-- Nullable a propósito. Las cuentas que ya existen no lo tienen, y exigirlo
-- rompería el alta automática de quien entra por primera vez —que recibe su
-- propia cuenta antes de que nadie le pida datos tributarios—. Se completa
-- desde /admin cuando el cliente se formaliza.
--
-- Sin CHECK de formato: el dígito verificador se valida en `app/rut.py`, donde
-- se puede dar un mensaje útil en vez de un error de constraint. La columna
-- guarda el valor ya normalizado, sin puntos y con guion: 76543210-3.
alter table cuentas add column if not exists rut text;

-- Único, pero sólo entre los que tienen valor: dos cuentas no pueden compartir
-- RUT —serían la misma empresa, y hay que fusionarlas—, pero muchas pueden
-- estar sin él.
create unique index if not exists ux_cuentas_rut on cuentas (rut) where rut is not null;

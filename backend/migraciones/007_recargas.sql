-- Recargas declaradas por el cliente, a la espera de verificación.
--
-- Hasta ahora `contratar` acreditaba el saldo en el momento: servía para
-- probar el portal, no para venderle a nadie. Con esto el cliente transfiere,
-- declara lo que transfirió, y el saldo se acredita recién cuando alguien lo
-- verifica contra la cartola del banco.
--
-- Es el mismo lugar que ocuparía el webhook de una pasarela de pago: la
-- confirmación llega de afuera, y sólo entonces se mueve el saldo.
create table if not exists recargas (
  id            uuid primary key default gen_random_uuid(),
  cuenta_id     uuid not null references cuentas(id) on delete cascade,
  -- Quién la declaró. Se conserva aunque después lo muevan de cuenta.
  usuario_id    uuid not null references usuarios(id) on delete cascade,

  -- El pack elegido, si eligió uno. Null cuando declara un monto libre.
  -- Se guarda el id y no el monto: los montos y el bono viven en el servidor.
  pack_id       text,

  -- Lo que el cliente DICE que transfirió. No es lo que se acredita: eso sale
  -- de la cartola. Sirve para encontrar la transferencia y para detectar
  -- diferencias.
  monto_declarado bigint not null,
  -- N° de transferencia o folio. Es el dato que permite calzarla en el banco.
  referencia    text not null,

  estado        text not null default 'pendiente',
  -- Lo que finalmente se movió, cuando se aprueba. Puede no coincidir con lo
  -- declarado, y esa diferencia es justamente lo que hay que poder ver.
  monto_acreditado bigint,
  -- Por qué se rechazó, o cualquier nota de quien la resolvió.
  nota          text,
  resuelta_en   timestamptz,
  resuelta_por  text,

  creada_en     timestamptz not null default now(),

  constraint recargas_estado_valido
    check (estado in ('pendiente', 'acreditada', 'rechazada')),
  -- Una recarga resuelta tiene que decir cuándo y quién; una pendiente, no.
  constraint recargas_resueltas_completas
    check ((estado = 'pendiente') = (resuelta_en is null))
);

-- La consulta del panel de administración es "qué hay pendiente": índice
-- parcial, porque las resueltas no se listan ahí y con el tiempo son la
-- mayoría.
create index if not exists ix_recargas_pendientes
  on recargas (creada_en) where estado = 'pendiente';

-- El cliente ve las suyas, las más recientes primero.
create index if not exists ix_recargas_cuenta on recargas (cuenta_id, creada_en desc);

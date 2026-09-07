-- Deja constancia de qué páginas se quitaron de un documento antes de medirlo
-- y despacharlo al motor.
--
-- Los contratos impresos a doble cara llegan con el reverso en blanco
-- intercalado. Esas hojas se cobran dos veces —Document Intelligence por
-- página enviada, y el portal por página contada— sin aportar nada, así que se
-- podan antes de medir.
--
-- Al motor le llega el documento recortado, y este campo es lo que permite
-- reconstruir la relación con el original: si una observación menciona la
-- página 9 del recortado, acá está la lista para saber cuál era en el que
-- entregó el cliente.
--
-- Lista vacía significa que no se quitó nada, que es el caso normal.

alter table documentos
  add column if not exists paginas_omitidas integer[] not null default '{}';

comment on column documentos.paginas_omitidas is
  'Páginas en blanco quitadas antes de medir y despachar. Numeración 1-based del documento original.';

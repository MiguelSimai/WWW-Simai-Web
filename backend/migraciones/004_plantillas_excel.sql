-- Plantillas del Excel que descarga el cliente.
--
-- El entregable es una planilla con **una fila por expediente**, y sus columnas
-- son propias de cada proceso: el cliente de créditos automotrices espera
-- NumeroOperacion, Patente, una columna por tipo de documento y Observaciones;
-- otro cliente esperará otra cosa.
--
-- Por eso las columnas viven en base y no en el código: agregar un cliente o
-- cambiar su planilla no debería ser un despliegue.
create table if not exists plantillas_excel (
  id        uuid primary key default gen_random_uuid(),
  servicio  text not null,
  nombre    text not null,
  -- Lista ordenada de columnas. Cada una:
  --   titulo  el encabezado, tal como lo quiere el cliente
  --   origen  'solicitud' | 'consolidado' | 'documento'
  --   campo   qué sacar (según el origen)
  --   patron  sólo para origen 'documento': con qué texto reconocer el archivo
  --
  --   origen 'solicitud'    → campo es una columna de solicitudes
  --                           (numero_cliente, codigo, estado, unidades, costo,
  --                            resumen, creada_en)
  --   origen 'consolidado'  → campo es una clave del respuesta_ia del expediente
  --   origen 'documento'    → se busca el documento cuyo nombre contenga patron;
  --                           campo puede ser 'presencia' (Sí/No), 'estado',
  --                           'resultado', o una clave de su respuesta_ia
  columnas  jsonb not null,
  activa    boolean not null default true,
  creada_en timestamptz not null default now()
);

create unique index if not exists plantillas_excel_servicio_activa
  on plantillas_excel (servicio) where activa;


-- Plantilla del caso real: expedientes de crédito automotriz.
--
-- Los nombres de campo de origen 'consolidado' (patente, observaciones) tienen
-- que coincidir con lo que devuelva el proceso en su schema_salida. Mientras
-- ese schema no esté fijado, las celdas saldrán vacías: revisar acá cuando se
-- defina.
insert into plantillas_excel (servicio, nombre, columnas)
select 'documentos', 'Operaciones — crédito automotriz', $json$[
  {"titulo": "NumeroOperacion", "origen": "solicitud",   "campo": "numero_cliente"},
  {"titulo": "Patente",         "origen": "consolidado", "campo": "patente"},
  {"titulo": "Carta",           "origen": "documento",   "campo": "estado", "patron": "CARTA"},
  {"titulo": "CAV",             "origen": "documento",   "campo": "estado", "patron": "CAV"},
  {"titulo": "Contrato",        "origen": "documento",   "campo": "estado", "patron": "CONTRATO"},
  {"titulo": "Pagare",          "origen": "documento",   "campo": "estado", "patron": "PAGARE"},
  {"titulo": "Observaciones",   "origen": "consolidado", "campo": "observaciones"}
]$json$::jsonb
where not exists (
  select 1 from plantillas_excel where servicio = 'documentos' and activa
);

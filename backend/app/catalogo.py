"""
Catálogo de servicios del lado del servidor.

**Esta es la fuente de verdad del cobro.** El catálogo del front
(`src/app/core/catalogo.ts`) es para mostrar; el dinero se calcula acá, porque
lo que el navegador manda no es confiable.

Los dos tienen que decir lo mismo. Hoy se mantienen a mano, lo que es una
duplicación real y el lugar más probable de una discrepancia entre el precio
que el cliente vio y el que se le cobró. Lo correcto es que el front lea de
`GET /api/catalogo` y esta sea la única copia; queda pendiente.

Formatos: solo los que el motor procesa hoy de punta a punta. Doc_Check
reconoce por magic bytes PDF, imágenes y audio, y nada más. El catálogo del
front ofrece además video, Office y ZIP, que hay que deshabilitar hasta que el
motor los cubra: aceptar un archivo no es procesarlo.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Servicio:
    id: str
    nombre: str
    # Cómo se cuenta lo que se cobra: "minutos", "paginas" o "ejecuciones".
    unidad_medida: str
    # Precio por unidad en CLP, sin IVA.
    precio: int
    extensiones: frozenset[str]
    max_mb: int
    # Un servicio sin formatos que el motor procese queda fuera hasta que los
    # tenga. Es preferible decirlo a aceptar el archivo y fallar después.
    disponible: bool = True
    motivo_no_disponible: str = ""


# Tope por documento mientras el archivo viaje en base64 dentro del body. Al
# pasar a Blob Storage sube a lo que promete el catálogo del front.
_MAX_MB = 25

_SERVICIOS: tuple[Servicio, ...] = (
    Servicio(
        id="transcripcion",
        nombre="Transcripción de audio y video",
        unidad_medida="minutos",
        precio=12,
        # Sin video: Doc_Check no reconoce MP4/MOV/MKV, y Speech necesita que
        # se le extraiga el audio antes. Sin .m4a: es un contenedor MP4.
        extensiones=frozenset({".mp3", ".wav", ".ogg", ".flac", ".aac"}),
        max_mb=_MAX_MB,
    ),
    Servicio(
        id="documentos",
        nombre="Análisis de documentos",
        unidad_medida="paginas",
        precio=35,
        extensiones=frozenset({".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".bmp"}),
        max_mb=_MAX_MB,
    ),
    Servicio(
        id="conversaciones",
        nombre="Análisis de conversaciones",
        unidad_medida="minutos",
        precio=25,
        extensiones=frozenset({".mp3", ".wav", ".ogg", ".flac", ".aac"}),
        max_mb=_MAX_MB,
    ),
    Servicio(
        id="automatizacion",
        nombre="Automatización de procesos",
        unidad_medida="ejecuciones",
        precio=18,
        # CSV, XLSX y JSON no pasan Doc_Check, así que el servicio no tiene
        # ningún formato viable todavía.
        extensiones=frozenset(),
        max_mb=_MAX_MB,
        disponible=False,
        motivo_no_disponible="Disponible por API. La carga de archivos desde el portal llega pronto.",
    ),
)

CATALOGO: dict[str, Servicio] = {s.id: s for s in _SERVICIOS}


def servicio_por_id(id_servicio: str) -> Servicio | None:
    return CATALOGO.get(id_servicio)

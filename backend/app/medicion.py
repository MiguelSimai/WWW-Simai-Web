"""
Cuánto se cobra por un archivo.

Las unidades se miden acá, en el servidor, y no se toman del navegador ni del
motor de procesamiento:

  - Del navegador, porque el cliente puede mentir. La pantalla de envío estima
    la duración para mostrarla, pero esa cifra es informativa.
  - Del motor, porque quien factura es el portal. Que el cobro dependa de lo
    que informe otro servicio lo vuelve frágil por ninguna ganancia: medir un
    encabezado de audio o contar páginas de un PDF es barato.
"""

import io
import math

from .catalogo import Servicio

# Extensiones cuya duración sabe leer mutagen entre las que aceptamos hoy.
_AUDIO = {".mp3", ".wav", ".ogg", ".flac", ".aac"}


class ArchivoNoMedible(Exception):
    """El archivo llegó corrupto o en un formato que no se puede medir."""


def medir(servicio: Servicio, nombre: str, contenido: bytes) -> int:
    """
    Unidades a cobrar por este archivo, según la unidad del servicio.

    Siempre devuelve al menos 1: un archivo válido de tres segundos es un
    minuto cobrado, no cero.
    """
    extension = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""

    if servicio.unidad_medida == "minutos":
        return _minutos(extension, contenido)
    if servicio.unidad_medida == "paginas":
        return _paginas(extension, contenido)
    # "ejecuciones": un archivo enviado es una ejecución.
    return 1


def _minutos(extension: str, contenido: bytes) -> int:
    if extension not in _AUDIO:
        raise ArchivoNoMedible(f"No se puede medir la duración de un {extension}.")

    from mutagen import File as MutagenFile

    try:
        audio = MutagenFile(io.BytesIO(contenido))
    except Exception as exc:
        raise ArchivoNoMedible("El archivo de audio no se pudo leer.") from exc

    if audio is None or audio.info is None or not getattr(audio.info, "length", 0):
        raise ArchivoNoMedible("El archivo de audio no declara su duración.")

    return max(1, math.ceil(audio.info.length / 60))


def _paginas(extension: str, contenido: bytes) -> int:
    # Una imagen es una página: no hay nada que contar.
    if extension in {".jpg", ".jpeg", ".png", ".tiff", ".bmp"}:
        return 1

    if extension != ".pdf":
        raise ArchivoNoMedible(f"No se pueden contar las páginas de un {extension}.")

    from pypdf import PdfReader

    try:
        lector = PdfReader(io.BytesIO(contenido))
        paginas = len(lector.pages)
    except Exception as exc:
        raise ArchivoNoMedible("El PDF no se pudo abrir.") from exc

    if not paginas:
        raise ArchivoNoMedible("El PDF no tiene páginas.")

    return paginas


def costo(servicio: Servicio, unidades: int) -> int:
    """Costo en CLP, sin IVA. El precio unitario sale del catálogo."""
    return servicio.precio * unidades

"""
Cuánto se cobra por un archivo, y qué páginas de él vale la pena procesar.

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


def podar_paginas_vacias(nombre: str, contenido: bytes) -> tuple[bytes, list[int]]:
    """
    Devuelve el PDF sin sus páginas en blanco, y cuáles se quitaron.

    Los contratos impresos a doble cara llegan con el reverso vacío
    intercalado. Document Intelligence cobra por página enviada —vacía o no— y
    el portal cobra por página contada, así que esas hojas se pagan dos veces
    sin aportar nada: en un contrato de 13 páginas, 6 son reversos.

    Una página se descarta solo si NO tiene texto y NO tiene imágenes. La
    segunda condición es la que protege: una página sin texto pero con imagen
    puede ser una firma escaneada o un anexo, y esa se queda.

    Antes de mirar página por página se comprueba que el documento tenga capa
    de texto en alguna parte. Un PDF escaneado no la tiene en ninguna, y ahí el
    criterio del texto borraría el documento entero.

    Ante cualquier duda no se poda: se devuelve el archivo intacto. Cobrar de
    más una hoja es un problema menor que perder una página con contenido.

    Retorna:
        (contenido, paginas_quitadas) — los números son 1-based y referidos al
        documento ORIGINAL, que es como los cuenta quien lo abra.
    """
    extension = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension != ".pdf":
        return contenido, []

    from pypdf import PdfReader, PdfWriter

    try:
        lector = PdfReader(io.BytesIO(contenido))
        paginas = lector.pages
    except Exception:
        return contenido, []

    if len(paginas) < 2:
        return contenido, []

    try:
        tiene_texto = [bool((pag.extract_text() or "").strip()) for pag in paginas]
    except Exception:
        return contenido, []

    # PDF escaneado: ninguna página declara texto. El criterio no aplica.
    if not any(tiene_texto):
        return contenido, []

    vacias: list[int] = []
    for indice, pagina in enumerate(paginas):
        if tiene_texto[indice] or _tiene_imagenes(pagina):
            continue
        vacias.append(indice)

    if not vacias or len(vacias) == len(paginas):
        return contenido, []

    escritor = PdfWriter()
    for indice, pagina in enumerate(paginas):
        if indice not in vacias:
            escritor.add_page(pagina)

    salida = io.BytesIO()
    try:
        escritor.write(salida)
    except Exception:
        return contenido, []

    return salida.getvalue(), [i + 1 for i in vacias]


def _tiene_imagenes(pagina) -> bool:
    """
    True si la página incorpora algún XObject de tipo imagen.

    Se lee el diccionario de recursos en vez de `pagina.images`, que
    materializa cada imagen en memoria: acá solo interesa si existe alguna.
    Ante un PDF con estructura inesperada se responde True, que es el lado
    seguro — la página se conserva.
    """
    try:
        recursos = pagina.get("/Resources")
        if recursos is None:
            return False
        xobjects = recursos.get_object().get("/XObject")
        if xobjects is None:
            return False
        return any(
            obj.get_object().get("/Subtype") == "/Image"
            for obj in xobjects.get_object().values()
        )
    except Exception:
        return True


def costo(servicio: Servicio, unidades: int) -> int:
    """Costo en CLP, sin IVA. El precio unitario sale del catálogo."""
    return servicio.precio * unidades

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


# Una página se considera en blanco bajo este porcentaje de píxeles oscuros.
# Medido sobre contratos escaneados reales: las hojas vacías dan entre 0,01 % y
# 0,26 % —polvo del escáner y sombras del borde—, y la página con menos texto
# da 5,6 %. El umbral queda cuatro veces sobre el peor blanco y cinco veces bajo
# el contenido más liviano.
_TINTA_MAXIMA_BLANCO = 1.0

# Solo se decodifican las páginas cuya imagen pesa menos que esto. Una hoja
# vacía comprime a menos de 1 KB; la más liviana con texto pesa 19 KB. Evita
# decodificar páginas grandes para nada.
_BYTES_CANDIDATA_BLANCO = 6 * 1024


def podar_paginas_vacias(nombre: str, contenido: bytes) -> tuple[bytes, list[int]]:
    """
    Devuelve el PDF sin sus páginas en blanco, y cuáles se quitaron.

    Los contratos impresos a doble cara llegan con el reverso vacío
    intercalado. Document Intelligence cobra por página enviada —vacía o no— y
    el portal cobra por página contada, así que esas hojas se pagan dos veces
    sin aportar nada: en un contrato de 13 páginas, 6 son reversos.

    Hay dos clases de PDF y cada una necesita su criterio:

      - Nativo, con capa de texto: la página está vacía si no tiene texto NI
        imágenes. La segunda condición protege una firma escaneada o un anexo.
      - Escaneado, sin capa de texto en ninguna página: no hay texto que mirar,
        así que se mide cuánta tinta tiene la imagen de la página.

    Ante cualquier duda no se poda. Cobrar de más una hoja es un problema menor
    que perder una página con contenido.

    Retorna:
        (contenido, paginas_quitadas) — números 1-based referidos al documento
        ORIGINAL, que es como los cuenta quien lo abra.
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

    escaneado = not any(tiene_texto)

    vacias: list[int] = []
    for indice, pagina in enumerate(paginas):
        if escaneado:
            if _pagina_escaneada_en_blanco(pagina):
                vacias.append(indice)
        elif not tiene_texto[indice] and not _tiene_imagenes(pagina):
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


def _pagina_escaneada_en_blanco(pagina) -> bool:
    """
    True si la imagen de la página es papel en blanco.

    Primero se mira el tamaño comprimido, que no obliga a decodificar nada: una
    hoja vacía ocupa una fracción de lo que ocupa una con texto. Solo las
    candidatas se decodifican para contar sus píxeles oscuros.

    Cualquier error responde False y la página se conserva.
    """
    try:
        if _bytes_de_imagenes(pagina) > _BYTES_CANDIDATA_BLANCO:
            return False

        from PIL import Image

        for imagen in pagina.images:
            grises = Image.open(io.BytesIO(imagen.data)).convert("L")
            # Reducir antes de contar: la proporción de tinta se conserva y el
            # conteo baja de millones de píxeles a decenas de miles.
            grises.thumbnail((400, 400))
            histograma = grises.histogram()
            oscuros = sum(histograma[:200])
            total = grises.size[0] * grises.size[1]
            if not total:
                return False
            return (100.0 * oscuros / total) < _TINTA_MAXIMA_BLANCO
    except Exception:
        return False

    return False


def _bytes_de_imagenes(pagina) -> int:
    """Tamaño comprimido de las imágenes de la página, sin decodificarlas."""
    total = 0
    try:
        recursos = pagina.get("/Resources")
        if recursos is None:
            return 0
        xobjects = recursos.get_object().get("/XObject")
        if xobjects is None:
            return 0
        for obj in xobjects.get_object().values():
            o = obj.get_object()
            if o.get("/Subtype") == "/Image":
                total += len(o.get_data())
    except Exception:
        # Sin medida confiable, se declara grande: no es candidata a blanco.
        return _BYTES_CANDIDATA_BLANCO + 1
    return total


def costo(servicio: Servicio, unidades: int) -> int:
    """Costo en CLP, sin IVA. El precio unitario sale del catálogo."""
    return servicio.precio * unidades

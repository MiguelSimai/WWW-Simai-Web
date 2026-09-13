"""
Qué es un archivo de verdad, mirando sus primeros bytes.

La extensión del nombre la escribe quien sube el archivo, así que no prueba
nada: renombrar cualquier cosa a `.pdf` la hacía pasar. El contenido sí se
delata — casi todo formato empieza con una marca fija.

Esta tabla es **la misma que la del gateway** (`app/services/doc_check.py` en
ia-api-gateway), y eso es deliberado:

  - Si el portal fuera más estricto, rechazaría archivos que la capa siguiente
    sí acepta, y el cliente no entendería por qué.
  - Si fuera más laxo, el archivo pasaría, se cobraría el saldo y lo rechazaría
    el gateway media arquitectura después.

Lo que sí cambia respecto del gateway es qué se hace con una discrepancia: allá
queda como advertencia, acá se rechaza. Es la diferencia entre anotar el
problema y no dejarlo entrar, y la puerta es este archivo.

**El portal solo opina de los formatos que conoce.** Si llega una extensión que
no está en la tabla de abajo, pasa sin revisar. Eso es a propósito y no un
descuido: el Doc_Check del gateway se configura **por proceso**, contra la base
(`iagw_configuracion_proceso`), así que habilitarle a un cliente un proceso que
acepte un formato nuevo no requiere tocar este archivo. Si acá se rechazara lo
desconocido, cada proceso nuevo empezaría rechazándole los archivos al cliente
hasta que alguien se acordara de venir a agregar una firma — y la falla se
vería en producción, no antes.

La autoridad sobre qué formatos acepta cada proceso es el gateway. Esto es solo
un filtro temprano para lo evidente: un .pdf que por dentro es otra cosa se
rechaza en la puerta, sin cobrarle el saldo al cliente ni cruzar media
arquitectura para llegar a la misma conclusión.
"""

# Primeros bytes de cada formato que el portal acepta. El orden importa solo
# para formatos que comparten prefijo; hoy ninguno lo hace.
_FIRMAS: tuple[tuple[bytes, str], ...] = (
    (b"%PDF", "application/pdf"),
    (b"\x89PNG\r\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),          # TIFF little-endian
    (b"MM\x00*", "image/tiff"),          # TIFF big-endian
    (b"BM", "image/bmp"),
    (b"ID3", "audio/mpeg"),              # MP3 con cabecera ID3
    (b"\xff\xfb", "audio/mpeg"),         # MP3 sin ID3 (frame sync)
    (b"\xff\xf3", "audio/mpeg"),         # MP3 MPEG-2
    (b"\xff\xf2", "audio/mpeg"),         # MP3 MPEG-2.5
    (b"RIFF", "audio/wav"),              # WAV (contenedor RIFF)
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"\xff\xf1", "audio/aac"),          # AAC ADTS
    (b"\xff\xf9", "audio/aac"),          # AAC ADTS
)

# Qué extensiones puede llevar cada tipo. El gateway tiene este mapa sin las
# entradas de audio, lo que le hace marcar todo audio como discrepante; acá
# están, porque acá la discrepancia rechaza y eso dejaría fuera toda
# transcripción.
_EXTENSIONES: dict[str, frozenset[str]] = {
    "application/pdf": frozenset({".pdf"}),
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/tiff": frozenset({".tiff", ".tif"}),
    "image/bmp": frozenset({".bmp"}),
    "audio/mpeg": frozenset({".mp3"}),
    "audio/wav": frozenset({".wav"}),
    "audio/ogg": frozenset({".ogg"}),
    "audio/flac": frozenset({".flac"}),
    "audio/aac": frozenset({".aac"}),
}


def tipo_real(contenido: bytes) -> str | None:
    """
    El MIME que dicen los bytes, o None si no se reconoce ninguno.
    """
    for firma, tipo in _FIRMAS:
        if contenido.startswith(firma):
            return tipo

    # El header %PDF no siempre está en el byte 0: la norma (ISO 32000) lo
    # admite dentro del primer KB, y hay generadores que dejan un BOM o
    # espacios antes. Se mira aparte para no relajar las demás firmas.
    if b"%PDF" in contenido[:1024]:
        return "application/pdf"

    return None


# Todas las extensiones de las que este módulo sabe algo. Se arma sola desde el
# mapa de arriba: agregar un formato es tocar un solo sitio.
_VIGILADAS: frozenset[str] = frozenset().union(*_EXTENSIONES.values())


def vigilada(extension: str) -> bool:
    """
    Si de esta extensión sabemos qué aspecto tiene por dentro.

    En False el archivo pasa sin revisar, y lo valida el gateway con la
    configuración del proceso. Ver la nota del encabezado.
    """
    return extension in _VIGILADAS


def corresponde(extension: str, tipo: str | None) -> bool:
    """Si un archivo de ese tipo puede llamarse con esa extensión."""
    if tipo is None:
        return False
    return extension in _EXTENSIONES.get(tipo, frozenset())

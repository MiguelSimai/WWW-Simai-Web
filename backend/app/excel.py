"""
Genera la planilla que descarga el cliente.

Una fila por expediente, y las columnas las define la plantilla del servicio
(tabla `plantillas_excel`): el cliente de créditos automotrices espera
NumeroOperacion, Patente, una columna por tipo de documento y Observaciones,
y otro cliente esperará otra cosa.

Si un servicio no tiene plantilla, se cae a un juego de columnas genérico: es
mejor entregar algo correcto que un error.

Cada columna puede declarar `formato` para normalizar lo que muestra. Hace
falta porque el modelo transcribe lo que ve, y lo que ve varía: el mismo RUT
llega como "14156964-3" en un documento y "14.156.964-3" en otro. Quien lee la
planilla espera una sola forma.

Y puede declarar `fuentes`: una lista de orígenes en orden de precedencia, de
la que se toma el primero con valor. El número de operación está en la carta,
en el contrato y en el pagaré; si la carta falla, la columna quedaría vacía
teniendo el dato a mano. Que los documentos discrepen no se resuelve acá: de
eso avisan las reglas de cruce, que dejan el expediente como rechazado y
detallan la diferencia en las observaciones.
"""

import io
import logging
import re
import unicodedata
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# Cuando el servicio no tiene plantilla configurada.
COLUMNAS_GENERICAS: list[dict] = [
    {"titulo": "Solicitud", "origen": "solicitud", "campo": "numero_cliente"},
    {"titulo": "Código", "origen": "solicitud", "campo": "codigo"},
    {"titulo": "Archivos", "origen": "solicitud", "campo": "documentos"},
    {"titulo": "Volumen", "origen": "solicitud", "campo": "unidades"},
    {"titulo": "Costo", "origen": "solicitud", "campo": "costo"},
    {"titulo": "Estado", "origen": "solicitud", "campo": "estado"},
    {"titulo": "Ingresada", "origen": "solicitud", "campo": "creada_en"},
    {"titulo": "Observaciones", "origen": "solicitud", "campo": "resumen"},
]

# Cómo se lee cada estado en la planilla. El cliente no tiene por qué conocer
# el vocabulario interno.
_ESTADO_LEGIBLE = {
    "completada": "OK",
    "revisar": "Revisar",
    "error": "Error",
    "procesando": "En proceso",
}

_ANCHO_MAXIMO = 70
_ANCHO_MINIMO = 12


def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _coincide(nombre_archivo: str, patron: str) -> bool:
    """
    Si el nombre del archivo corresponde al tipo que busca la columna.

    Se compara sin tildes y en mayúsculas porque los nombres vienen tal como
    los dejó quien armó la carpeta: "PAGARE.pdf", "Pagaré.PDF", "pagare (1).pdf"
    son el mismo documento.
    """
    return _sin_tildes(patron).upper() in _sin_tildes(nombre_archivo).upper()


def _valor(columna: dict, solicitud: dict, documentos: list[dict]) -> Any:
    """
    El valor de una columna para un expediente.

    Con `fuentes`, se prueban en orden y gana la primera que traiga algo. La
    precedencia la fija la plantilla y es deliberada: para el número de
    operación manda la carta, que es el documento de cabecera.
    """
    fuentes = columna.get("fuentes")
    if fuentes:
        for fuente in fuentes:
            # Cada fuente hereda lo que la columna ya declaró —el formato, por
            # ejemplo— y solo cambia de dónde sale el dato.
            valor = _valor({**columna, **fuente, "fuentes": None}, solicitud, documentos)
            if valor is not None and valor != "":
                return valor
        return None

    origen = columna.get("origen", "solicitud")
    campo = columna.get("campo", "")

    if origen == "solicitud":
        valor = solicitud.get(campo)
        if campo == "estado":
            return _ESTADO_LEGIBLE.get(str(valor), valor)
        return valor

    if origen == "consolidado":
        datos = solicitud.get("respuesta_ia")
        return _del_json(datos, campo)

    if origen == "regla":
        # Una columna por regla. Devuelve el objeto entero —no un campo— porque
        # el formateador necesita el nombre, el resultado, lo que comparó y el
        # detalle para armar la celda.
        #
        # Se identifica por `codigo`. El `indice` posicional sigue aceptándose
        # para las plantillas viejas, pero no debería usarse en las nuevas: las
        # validaciones vienen en el orden de `iagw_reglas_config.orden`, así que
        # intercalar una regla corre todas las columnas y "Regla 1" pasa a
        # mostrar otra cosa, sin error y sin que nadie se entere.
        consolidado = solicitud.get("respuesta_ia")
        if not isinstance(consolidado, dict):
            return None

        reglas = consolidado.get("validaciones")
        if not isinstance(reglas, list):
            return None

        codigo = columna.get("codigo")
        if codigo:
            return next((r for r in reglas if r.get("regla") == codigo), None)

        indice = columna.get("indice", 0)
        return reglas[indice] if indice < len(reglas) else None

    if origen == "documento":
        patron = columna.get("patron") or ""
        hallado = next((d for d in documentos if _coincide(d["archivo"], patron)), None)

        if campo == "presencia":
            return "Sí" if hallado else "No"
        if hallado is None:
            # Documento ausente: celda vacía. Un "No" acá se confundiría con un
            # resultado del análisis.
            return None
        if campo == "estado":
            return _ESTADO_LEGIBLE.get(str(hallado["estado"]), hallado["estado"])
        if campo in ("resultado", "resumen"):
            return hallado.get("resumen") or hallado.get("error")
        return _del_json(hallado.get("respuesta_ia"), campo)

    return None


def _del_json(datos: Any, campo: str) -> Any:
    """
    Saca `campo` del JSON del motor. Acepta rutas con punto ("deudor.rut").

    Las listas se devuelven intactas. Aplanarlas es cosa de la celda o del
    formateador: `motivos_rechazo` se numera, y un texto con punto y coma
    adentro no debe partirse en dos observaciones.
    """
    if not isinstance(datos, dict) or not campo:
        return None

    actual: Any = datos
    for parte in campo.split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(parte)
        if actual is None:
            return None

    if isinstance(actual, (dict,)):
        return None
    return actual


def _formato_rut(valor: Any) -> Any:
    """
    Un RUT sin puntos y con guion: 14156964-3.

    Si no parece un RUT se devuelve intacto. Vale más una celda con el texto
    original que una vacía porque el formateador no lo reconoció.
    """
    texto = str(valor).replace(".", "").replace(" ", "").upper()
    m = re.match(r"^(\d{1,8})-?([\dK])$", texto)
    return f"{m.group(1)}-{m.group(2)}" if m else valor


def _formato_fecha(valor: Any) -> Any:
    """
    Una fecha real, para que Excel la ordene y filtre como tal.

    El modelo las entrega en ISO porque así se le pidió; acá se convierten a
    `date` y la presentación dd-mm-aaaa la aplica `generar()` con el formato de
    celda. Guardar el texto ya formateado sería más simple y peor: quedarían
    como cadenas y "01-02" ordenaría antes que "31-01".
    """
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.fromisoformat(str(valor).strip()[:10]).date()
    except (ValueError, TypeError):
        return valor


# Marca interna para el blanco que todavía no tiene a quién pegarse.
_PENDIENTE = "\x00"


def _negrita(texto: str) -> TextBlock:
    return TextBlock(InlineFont(b=True), texto)


def _enriquecido(partes: list) -> CellRichText:
    """
    Arma el texto enriquecido sin dejar runs que sean puro espacio en blanco.

    openpyxl marca `xml:space="preserve"` solo cuando el run trae algo además
    del blanco. Un run que es únicamente "\n" sale sin esa marca, Excel le quita
    el contenido al leerlo y rechaza el archivo entero: "Hemos encontrado un
    problema con contenido". Por eso el separador se pega al run siguiente —o al
    anterior, si va al final— en vez de viajar solo.
    """
    pendiente = ""
    resultado: list = []

    for parte in partes:
        if isinstance(parte, TextBlock):
            texto = (parte.text or "")
            if pendiente:
                parte = TextBlock(parte.font, pendiente + texto)
                pendiente = ""
            resultado.append(parte)
            continue

        texto = str(parte)
        if not texto:
            continue
        if not texto.strip():
            pendiente += texto
            continue

        texto = pendiente + texto
        pendiente = ""
        # Dos runs planos seguidos son un solo run: menos XML y menos aristas.
        if resultado and isinstance(resultado[-1], str):
            resultado[-1] += texto
        else:
            resultado.append(texto)

    if pendiente and resultado:
        ultima = resultado[-1]
        resultado[-1] = (
            TextBlock(ultima.font, (ultima.text or "") + pendiente)
            if isinstance(ultima, TextBlock)
            else ultima + pendiente
        )

    return CellRichText(resultado)


def _formato_observaciones(valor: Any) -> Any:
    """
    Los motivos de rechazo, numerados y con el titular en negrita.

    Un motivo por regla incumplida, así que la numeración cuadra con la columna
    "Reglas falladas". Cuando una regla encontró varios problemas —es el caso de
    las validaciones internas, que recorren los cuatro documentos— cada hallazgo
    baja a su propia línea bajo el número.

    Sin motivos se dice explícitamente que todo pasó: una celda vacía no
    distingue "sin observaciones" de "no se evaluó".
    """
    motivos = valor if isinstance(valor, list) else (
        [x.strip() for x in str(valor).split(";") if x.strip()] if valor else []
    )

    if not motivos:
        return _enriquecido([_negrita("Todas las validaciones fueron aprobadas")])

    partes: list = []
    for n, motivo in enumerate(motivos, start=1):
        if partes:
            partes.append("\n")

        titular, _, resto = str(motivo).partition(":")
        partes.append(_negrita(f"{n}- {titular.strip()}:"))

        # Los hallazgos de una misma regla vienen separados por " | ".
        for hallazgo in [h.strip() for h in resto.split("|") if h.strip()]:
            partes.append(f"\n   {hallazgo}")

    return _enriquecido(partes)


def _formato_regla(valor: Any) -> Any:
    """
    Una regla explicada: qué evaluó, sobre qué campos y con qué resultado.

    El encabezado va en negrita para poder barrer la fila de un vistazo y ver
    cuál falló, sin leer el detalle de las siete.
    """
    if not isinstance(valor, dict):
        return None

    resultado = valor.get("resultado", "?")
    titular = f"{valor.get('regla', 'regla')} — {resultado}"

    partes: list = [_negrita(titular)]

    mensaje = valor.get("mensaje")
    if mensaje and resultado != "cumple":
        partes.append(f"\n{mensaje}")

    campos = valor.get("campos")
    if campos:
        listado = ", ".join(campos) if isinstance(campos, list) else str(campos)
        partes.append(f"\nCompara: {listado}")

    detalle = valor.get("detalle")
    if detalle:
        partes.append(f"\n{detalle}")

    return _enriquecido(partes)


_FORMATOS = {
    "rut": _formato_rut,
    "fecha": _formato_fecha,
    "observaciones": _formato_observaciones,
    "regla": _formato_regla,
}

# Cómo se ve cada formato en la planilla. Lo que no está acá va sin formato.
_FORMATO_CELDA = {
    "fecha": "DD-MM-YYYY",
    "monto": "#,##0",
}


def _aplicar_formato(valor: Any, formato: str | None) -> Any:
    # `observaciones` es la excepción: con valor nulo tiene algo que decir
    # —"todas aprobadas"—, mientras que el resto sin dato deja la celda vacía.
    if not formato:
        return valor
    if valor is None and formato != "observaciones":
        return valor
    convertir = _FORMATOS.get(formato)
    return convertir(valor) if convertir else valor


def _celda(valor: Any) -> Any:
    """Lo que openpyxl puede escribir tal cual."""
    if isinstance(valor, CellRichText):
        return valor
    if isinstance(valor, list):
        # Última parada para una lista sin formateador propio.
        return "; ".join(str(x) for x in valor)
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    if isinstance(valor, (int, float, date, str)) or valor is None:
        return valor
    return str(valor)


def generar(
    filas: list[dict],
    columnas: list[dict],
    titulo_hoja: str = "Operaciones",
) -> bytes:
    """
    Arma el XLSX y lo devuelve en bytes.

    `filas` son dicts de solicitud, cada uno con su lista `documentos_detalle`.
    """
    libro = Workbook()
    hoja = libro.active
    hoja.title = titulo_hoja[:31]  # Excel no admite títulos más largos

    encabezado_fondo = PatternFill("solid", fgColor="F1EAFE")
    encabezado_fuente = Font(bold=True)

    hoja.append([c.get("titulo", "") for c in columnas])
    for celda in hoja[1]:
        celda.fill = encabezado_fondo
        celda.font = encabezado_fuente
        celda.alignment = Alignment(vertical="center")

    for solicitud in filas:
        documentos = solicitud.get("documentos_detalle") or []
        hoja.append([
            _celda(_aplicar_formato(_valor(c, solicitud, documentos), c.get("formato")))
            for c in columnas
        ])

    # Presentación de fechas y montos. Va en el formato de celda y no en el
    # valor: la celda sigue conteniendo un número o una fecha, así que Excel la
    # ordena y filtra bien, y solo cambia cómo se muestra.
    for i, columna in enumerate(columnas, start=1):
        formato_celda = _FORMATO_CELDA.get(columna.get("formato") or "")
        if not formato_celda:
            continue
        for fila in hoja.iter_rows(min_row=2, min_col=i, max_col=i):
            fila[0].number_format = formato_celda

    # Ancho por contenido, acotado: las observaciones son párrafos y sin tope
    # dejarían una columna de miles de píxeles.
    for i, columna in enumerate(columnas, start=1):
        largos = [len(str(columna.get("titulo", "")))]
        for fila in hoja.iter_rows(min_row=2, min_col=i, max_col=i):
            valor = fila[0].value
            largos.append(len(str(valor)) if valor is not None else 0)

        ancho = min(_ANCHO_MAXIMO, max(_ANCHO_MINIMO, max(largos) + 2))
        hoja.column_dimensions[get_column_letter(i)].width = ancho

        # Texto ajustado cuando la columna es ancha —un párrafo de
        # observaciones— o cuando alguna celda trae saltos de línea. Sin esto
        # Excel los ignora y pega todo seguido: "…— cumpleLos 4 documentos…".
        multilinea = any(
            "\n" in str(fila[0].value)
            for fila in hoja.iter_rows(min_row=2, min_col=i, max_col=i)
            if fila[0].value is not None
        )
        if ancho >= _ANCHO_MAXIMO or multilinea:
            for fila in hoja.iter_rows(min_row=2, min_col=i, max_col=i):
                fila[0].alignment = Alignment(wrap_text=True, vertical="top")

    # Fija el encabezado al desplazarse: con 100 filas es la diferencia entre
    # leer la planilla y adivinar las columnas.
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()

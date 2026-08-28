"""
Del JSON del motor a una frase que el cliente entienda.

El panel muestra una línea por expediente —"Transcripción lista · 4 hablantes",
"3 diferencias entre anexo y contrato"—, no un JSON. Acá se deriva esa línea.

**Esto es provisorio a propósito.** La forma del `respuesta_ia` la define el
`schema_salida` de cada proceso en `iagw_config_proc`, y esos procesos todavía
no existen. Mientras no estén fijados, se buscan los campos por los nombres
más probables y se cae a algo genérico pero cierto.

Cuando los `schema_salida` estén definidos, este módulo es el único lugar a
tocar: una función por servicio, que sabe exactamente qué campos leer.
"""

from typing import Any

# Campos donde suele venir un texto ya listo para mostrar. Si el proceso
# devuelve uno de estos, se usa tal cual y no se inventa nada.
_CAMPOS_RESUMEN = ("resumen", "resumen_ejecutivo", "descripcion", "conclusion", "detalle")

# Campos donde suele venir una lista de hallazgos: diferencias, faltantes,
# observaciones. Su cantidad es lo más informativo que se puede decir.
_CAMPOS_HALLAZGOS = (
    "diferencias",
    "observaciones",
    "faltantes",
    "hallazgos",
    "inconsistencias",
    "alertas",
)


def derivar(servicio: str, datos: Any, documentos_ok: int, documentos_total: int) -> str:
    """
    Frase corta para el panel.

    Nunca falla ni devuelve vacío: si del JSON no se puede sacar nada útil, se
    describe lo que sí se sabe con certeza —cuántos documentos salieron bien—,
    que es mejor que una línea en blanco.
    """
    texto = _del_json(datos)
    if texto:
        return texto[:200]

    return _por_cantidad(servicio, documentos_ok, documentos_total)


def _del_json(datos: Any) -> str | None:
    """Intenta sacar una frase del resultado del motor."""
    if not isinstance(datos, dict):
        # Una lista suele ser un conjunto de ítems detectados: prestaciones,
        # hablantes, documentos clasificados.
        if isinstance(datos, list) and datos:
            return f"{len(datos)} ítems detectados"
        return None

    for campo in _CAMPOS_RESUMEN:
        valor = datos.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()

    for campo in _CAMPOS_HALLAZGOS:
        valor = datos.get(campo)
        if isinstance(valor, list):
            if not valor:
                return "Sin observaciones"
            etiqueta = campo if len(valor) != 1 else campo.rstrip("es").rstrip("s")
            return f"{len(valor)} {etiqueta}"

    # Un clasificador suele devolver el tipo de documento y nada más.
    tipo = datos.get("tipo_documento")
    if isinstance(tipo, str) and tipo.strip():
        return f"Clasificado como {tipo.replace('_', ' ')}"

    return None


def _por_cantidad(servicio: str, ok: int, total: int) -> str:
    """Lo que se puede afirmar sin mirar el resultado."""
    if total == 1:
        base = {
            "transcripcion": "Transcripción lista",
            "documentos": "Documento analizado",
            "conversaciones": "Conversación analizada",
            "automatizacion": "Ejecución completada",
        }.get(servicio, "Resultado listo")
        return base if ok else "No se pudo procesar"

    if ok == total:
        return f"{total} documentos procesados"
    if ok:
        return f"{ok} de {total} documentos procesados"
    return f"Ninguno de los {total} documentos se pudo procesar"

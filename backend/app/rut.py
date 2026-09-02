"""
Normalización y validación de RUT chileno.

Se valida el dígito verificador porque un RUT mal tecleado no se descubre hasta
que el SII rechaza la factura, y ahí ya es tarde: hay que anularla y reemitir.
El cálculo es determinista, así que atajarlo acá cuesta nada.

Se guarda normalizado —sin puntos, con guion, K mayúscula— para que dos
cuentas con el mismo RUT escrito distinto choquen contra el índice único en vez
de convivir como si fueran empresas diferentes.
"""

import re


class RutInvalido(ValueError):
    """El RUT no tiene forma de RUT, o su dígito verificador no cuadra."""


def _digito(cuerpo: int) -> str:
    """
    Dígito verificador por módulo 11, con la serie de factores 2..7.

    Es el algoritmo del SII: se recorren los dígitos de derecha a izquierda
    multiplicando por 2,3,4,5,6,7 y volviendo a 2.
    """
    suma = 0
    factor = 2
    while cuerpo > 0:
        suma += (cuerpo % 10) * factor
        cuerpo //= 10
        factor = 2 if factor == 7 else factor + 1

    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def normalizar(valor: str) -> str:
    """
    Devuelve el RUT como `76543210-3`, o lanza `RutInvalido`.

    Acepta lo que la gente escribe de verdad: con puntos, sin guion, con la K
    en minúscula.
    """
    limpio = re.sub(r"[.\s-]", "", (valor or "")).upper()

    if not re.fullmatch(r"\d{7,8}[0-9K]", limpio):
        raise RutInvalido(
            "El RUT debe tener entre 7 y 8 dígitos más el verificador, por ejemplo 76543210-3."
        )

    cuerpo, verificador = limpio[:-1], limpio[-1]

    if _digito(int(cuerpo)) != verificador:
        raise RutInvalido(
            f"El dígito verificador no corresponde: para {cuerpo} debería ser "
            f"{_digito(int(cuerpo))}."
        )

    return f"{cuerpo}-{verificador}"

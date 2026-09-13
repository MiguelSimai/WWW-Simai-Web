"""
Freno de peticiones por IP.

Qué frena y qué no, para no confiarse:

  - Frena a alguien golpeando desde una IP: un script que prueba rutas, que
    dispara logins en cadena o que intenta saturar el servidor. Para eso está.
  - NO frena un ataque repartido entre muchas IP. Eso no se resuelve acá sino
    delante del servidor, y para el tamaño de este portal no corresponde.

La cuenta vive en memoria y es **por proceso**. Passenger levanta varios, cada
uno con la suya, así que el límite real es el configurado por la cantidad de
procesos. Se podría llevar en la base y sería exacto, pero cada consulta contra
Neon cuesta ~250 ms y pagarlos en cada petición para contar sería peor que el
problema. Para cortar un abuso evidente, esta aproximación alcanza.

El contador se pierde al reiniciar la aplicación, que es aceptable: reiniciar
no es algo que un atacante pueda provocar.
"""

import threading
import time
from collections import deque

# Cada cuánto se barren las claves que ya no tienen marcas vigentes. Sin esto
# el diccionario crece con cada IP que haya pasado alguna vez, y un proceso de
# larga vida termina acumulando memoria por nada.
_LIMPIEZA_CADA_SEG = 300.0

# Tope de claves vigiladas a la vez. Es un seguro contra alguien que rote IP a
# propósito para inflar el diccionario: al pasarse, se descarta todo y se
# empieza de nuevo. Perder la cuenta un momento es preferible a quedarse sin
# memoria.
_MAXIMO_CLAVES = 20_000


class Ventana:
    """
    Cuenta cuántas peticiones hizo cada clave en los últimos N segundos.

    Es una ventana deslizante y no un contador que se reinicia cada minuto: con
    el segundo, alguien puede meter el doble del límite a caballo entre dos
    ventanas —todo al final de una y todo al principio de la siguiente— y no se
    entera nadie.

    Se guarda una marca de tiempo por petición admitida. Suena caro y no lo es:
    lo que ocupa es el límite configurado por clave, y las marcas viejas se
    descartan a medida que se consultan.
    """

    def __init__(self, maximo: int, segundos: float) -> None:
        self.maximo = maximo
        self.segundos = segundos
        self._marcas: dict[str, deque] = {}
        # Varias peticiones pueden entrar a la vez en el mismo proceso, y un
        # dict no tolera que se lo modifique desde dos lados.
        self._candado = threading.Lock()
        self._proxima_limpieza = time.monotonic() + _LIMPIEZA_CADA_SEG

    def registrar(self, clave: str) -> float:
        """
        Anota una petición. Devuelve 0 si puede pasar, o cuántos segundos
        faltan para que vuelva a haber lugar.

        Cuando devuelve espera NO anota la petición: si la anotara, quien
        siguiera insistiendo estiraría su propio castigo para siempre.
        """
        if self.maximo <= 0:  # apagada
            return 0.0

        ahora = time.monotonic()

        with self._candado:
            self._limpiar(ahora)

            marcas = self._marcas.setdefault(clave, deque())
            corte = ahora - self.segundos
            while marcas and marcas[0] <= corte:
                marcas.popleft()

            if len(marcas) >= self.maximo:
                return max(1.0, round(marcas[0] + self.segundos - ahora, 1))

            marcas.append(ahora)
            return 0.0

    def _limpiar(self, ahora: float) -> None:
        """Se llama con el candado tomado."""
        if len(self._marcas) > _MAXIMO_CLAVES:
            self._marcas.clear()
            self._proxima_limpieza = ahora + _LIMPIEZA_CADA_SEG
            return

        if ahora < self._proxima_limpieza:
            return

        corte = ahora - self.segundos
        self._marcas = {
            clave: marcas
            for clave, marcas in self._marcas.items()
            if marcas and marcas[-1] > corte
        }
        self._proxima_limpieza = ahora + _LIMPIEZA_CADA_SEG

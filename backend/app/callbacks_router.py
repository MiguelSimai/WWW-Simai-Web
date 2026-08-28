"""
Entrada del resultado desde N8N.

N8N espera a que el motor termine todos los documentos de un expediente, los
consolida y hace un POST acá. El portal cierra el expediente, ajusta el cobro
y deja el resultado listo para el panel.

──────────────────────────────────────────────────────────────────────────────
CONTRATO

  POST /api/callbacks/expediente
  X-Callback-Token: <CALLBACK_TOKEN>

  {
    "numero_solicitud": "297541",        // qué expediente. OBLIGATORIO
    "estado": "procesado",               // procesado | error | rechazado
    "respuesta_ia": { ... },             // consolidado del expediente
    "error_ia": "...",                  // si el expediente falló completo
    "documentos": [                      // opcional, pero recomendado
      {
        "id_transaccion_cliente": "DOC-1A2B3C4D",
        "estado": "procesado",
        "respuesta_ia": { ... },
        "confianza": 0.94,
        "error_ia": null
      }
    ]
  }

Los nombres son los que ya usa el stack: son los del payload que capa 3 manda
a N8N y los que arma su `Code Consolidar`. Además se aceptan alias por si el
flujo los nombra distinto (ver `_primero`), así que lo más probable es que
calce sin tocar nada.

Sin `documentos`, el expediente se cierra igual: todos sus documentos toman el
estado global. Con `documentos`, cada uno se cierra con lo suyo y el cobro se
ajusta a los que de verdad se procesaron.
──────────────────────────────────────────────────────────────────────────────
"""

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from psycopg.types.json import Jsonb

from . import resumen
from .config import config
from .db import pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/callbacks", tags=["callbacks"])

# Bajo este valor, un resultado se marca para revisión en vez de darse por
# bueno. El motor entrega la confianza en 0..1 desde capa 3 y en 0..100 desde
# la capa sync; `_normalizar_confianza` unifica a 0..100.
UMBRAL_REVISION = 75.0

# De qué campos leer cada cosa, en orden de preferencia. El primero es el
# nombre canónico; el resto son alias para no depender de cómo quede el flujo.
_ALIAS_REFERENCIA = ("numero_solicitud", "id_externo", "id_solicitud_externa", "referencia")
_ALIAS_DOCUMENTO = ("id_transaccion_cliente", "codigo_documento", "id_documento")
_ALIAS_RESULTADO = ("respuesta_ia", "datos", "resultado", "datos_ia")
_ALIAS_ERROR = ("error_ia", "error", "mensaje_error", "detalle_error")

# Estados con que el motor dice que algo terminó mal.
_ESTADOS_FALLIDOS = {"error", "rechazado", "fallido"}


def _primero(datos: dict, nombres: tuple[str, ...]) -> Any:
    for nombre in nombres:
        valor = datos.get(nombre)
        if valor not in (None, ""):
            return valor
    return None


def _normalizar_confianza(valor: Any) -> float | None:
    """
    Confianza a escala 0..100.

    Capa 3 la entrega en 0..1 y la capa sync en 0..100. Un 0.94 y un 94 son lo
    mismo, así que se escala lo que venga en fracción.
    """
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return round(numero * 100, 2) if numero <= 1 else round(numero, 2)


def _estado_documento(estado_motor: str | None, confianza: float | None) -> str:
    """Traduce el estado del motor al del portal, para un documento."""
    if estado_motor and estado_motor.lower() in _ESTADOS_FALLIDOS:
        return "error"
    if confianza is not None and confianza < UMBRAL_REVISION:
        return "revisar"
    return "completada"


def _estado_expediente(estados: list[str]) -> str:
    """
    Estado del expediente a partir de sus documentos.

    Un documento fallado de cuatro no hace fracasar el expediente: queda para
    revisión, con el detalle de cuál falló.
    """
    if not estados:
        return "error"
    if all(e == "error" for e in estados):
        return "error"
    if any(e in ("error", "revisar") for e in estados):
        return "revisar"
    return "completada"


@router.post("/expediente")
def recibir_expediente(
    cuerpo: dict,
    x_callback_token: str = Header(default=""),
):
    """
    Cierra un expediente con el resultado que entrega N8N.

    Es idempotente: N8N reintenta con backoff, y un expediente ya cerrado
    devuelve 200 sin volver a cobrar ni a modificar nada.
    """
    # Sin token configurado el callback está deshabilitado, no abierto: un
    # secreto vacío haría pasar a cualquiera que no mande el header.
    if not config.callback_token:
        logger.error("Llegó un callback pero CALLBACK_TOKEN no está configurado.")
        raise HTTPException(status_code=503, detail="Callback no configurado")

    # `compare_digest` en vez de `!=`: comparar secretos carácter por carácter
    # filtra información por el tiempo que tarda en fallar.
    if not secrets.compare_digest(x_callback_token, config.callback_token):
        raise HTTPException(status_code=401, detail="Token de callback inválido")

    referencia = _primero(cuerpo, _ALIAS_REFERENCIA)
    if not referencia:
        raise HTTPException(
            status_code=422,
            detail="Falta el número de solicitud del expediente.",
        )
    referencia = str(referencia)

    estado_global = str(cuerpo.get("estado") or "").lower()
    resultado_global = _primero(cuerpo, _ALIAS_RESULTADO)
    error_global = _primero(cuerpo, _ALIAS_ERROR)
    documentos_payload = cuerpo.get("documentos") or []

    with pool.connection() as conn:
        solicitud = conn.execute(
            """
            select id, codigo, usuario_id, servicio, costo, estado
              from solicitudes
             where referencia_motor = %s
               for update
            """,
            (referencia,),
        ).fetchone()

        if solicitud is None:
            # No es un error del portal: puede ser un expediente de otro
            # sistema que usa el mismo flujo N8N. Se responde 404 para que
            # quede en el log de N8N y no se reintente indefinidamente.
            logger.warning("Callback de un expediente desconocido: %s", referencia)
            raise HTTPException(status_code=404, detail="Expediente no encontrado")

        if solicitud["estado"] != "procesando":
            logger.info(
                "Callback repetido de %s, ya cerrado como '%s'",
                solicitud["codigo"],
                solicitud["estado"],
            )
            return {"estado": solicitud["estado"], "repetido": True}

        documentos = conn.execute(
            "select id, codigo, costo, estado from documentos where solicitud_id = %s",
            (solicitud["id"],),
        ).fetchall()

        por_codigo = {d["codigo"]: d for d in documentos}
        cerrados: dict[str, str] = {}

        # ── Cerrar los documentos que vienen detallados ──────────────────────
        for item in documentos_payload:
            if not isinstance(item, dict):
                continue

            codigo_doc = _primero(item, _ALIAS_DOCUMENTO)
            if not codigo_doc or codigo_doc not in por_codigo:
                logger.warning(
                    "El callback de %s trae un documento que no es suyo: %s",
                    solicitud["codigo"],
                    codigo_doc,
                )
                continue

            confianza = _normalizar_confianza(item.get("confianza"))
            estado_doc = _estado_documento(str(item.get("estado") or ""), confianza)
            resultado_doc = _primero(item, _ALIAS_RESULTADO)
            error_doc = _primero(item, _ALIAS_ERROR)

            conn.execute(
                """
                update documentos
                   set estado = %s, respuesta_ia = %s, resumen = %s,
                       confianza = %s, error = %s, cerrado_en = now()
                 where id = %s
                """,
                (
                    estado_doc,
                    Jsonb(resultado_doc) if resultado_doc is not None else None,
                    resumen.derivar(solicitud["servicio"], resultado_doc, 1, 1)
                    if resultado_doc is not None
                    else None,
                    confianza,
                    str(error_doc)[:500] if error_doc else None,
                    por_codigo[codigo_doc]["id"],
                ),
            )
            cerrados[codigo_doc] = estado_doc

        # ── Los que no vinieron detallados toman el estado global ────────────
        # Los que ya se habían cerrado con error al despachar se dejan como
        # están: el motor nunca los vio.
        estado_por_defecto = "error" if estado_global in _ESTADOS_FALLIDOS else "completada"

        for doc in documentos:
            if doc["codigo"] in cerrados:
                continue
            if doc["estado"] != "procesando":
                cerrados[doc["codigo"]] = doc["estado"]
                continue

            conn.execute(
                """
                update documentos
                   set estado = %s, error = %s, cerrado_en = now()
                 where id = %s
                """,
                (
                    estado_por_defecto,
                    str(error_global)[:500] if error_global else None,
                    doc["id"],
                ),
            )
            cerrados[doc["codigo"]] = estado_por_defecto

        # ── Ajustar el cobro a lo que de verdad se procesó ───────────────────
        # Lo reservado cubría el expediente completo. Lo que falló se devuelve:
        # no se cobra lo que no se entregó.
        devolver = sum(
            d["costo"] for d in documentos if cerrados.get(d["codigo"]) == "error"
        )
        costo_final = solicitud["costo"] - devolver

        estado_final = _estado_expediente(list(cerrados.values()))
        ok = sum(1 for e in cerrados.values() if e != "error")

        texto = resumen.derivar(
            solicitud["servicio"], resultado_global, ok, len(documentos) or 1
        )

        conn.execute(
            """
            update solicitudes
               set estado = %s, costo = %s, respuesta_ia = %s,
                   resumen = %s, error = %s, cerrada_en = now()
             where id = %s
            """,
            (
                estado_final,
                costo_final,
                Jsonb(resultado_global) if resultado_global is not None else None,
                texto,
                str(error_global)[:500] if error_global else None,
                solicitud["id"],
            ),
        )

        if devolver:
            conn.execute(
                "update usuarios set saldo = saldo + %s where id = %s",
                (devolver, solicitud["usuario_id"]),
            )
            conn.execute(
                """
                insert into movimientos_saldo
                       (usuario_id, solicitud_id, tipo, monto, detalle)
                     values (%s, %s, 'ajuste', %s, %s)
                """,
                (
                    solicitud["usuario_id"],
                    solicitud["id"],
                    devolver,
                    f"Documentos no procesados de {solicitud['codigo']}",
                ),
            )

    logger.info(
        "Expediente %s cerrado como '%s': %s de %s documentos, $%s cobrados",
        solicitud["codigo"],
        estado_final,
        ok,
        len(documentos),
        costo_final,
    )

    return {"codigo": solicitud["codigo"], "estado": estado_final}

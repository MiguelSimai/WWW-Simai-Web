from fastapi import APIRouter, Depends, HTTPException

from .db import pool
from .dependencias import sesion_actual

router = APIRouter(prefix="/api/cuenta", tags=["cuenta"])

# Los montos viven en el servidor. Si el front mandara el monto, cualquiera
# podría cargarse un millón de saldo editando la petición: el cliente elige
# QUÉ pack, nunca CUÁNTO vale.
PACKS: dict[str, dict] = {
    "prueba": {"monto": 30_000, "bonus": 0},
    "impulso": {"monto": 100_000, "bonus": 8_000},
    "volumen": {"monto": 300_000, "bonus": 45_000},
}


@router.post("/contratar/{pack_id}")
def contratar(pack_id: str, usuario: dict = Depends(sesion_actual)):
    """
    Acredita el saldo de un pack.

    SIN PASARELA DE PAGO: hoy acredita directo. Cuando exista el cobro, este
    endpoint debe crear la intención de pago y el saldo acreditarse recién en
    el webhook de confirmación, nunca aquí.
    """
    pack = PACKS.get(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Pack desconocido")

    total = pack["monto"] + pack["bonus"]

    if not usuario.get("cuenta_id"):
        raise HTTPException(status_code=403, detail="Tu usuario no tiene una cuenta asociada.")

    with pool.connection() as conn:
        # El saldo es de la cuenta: contrata la empresa, no la persona.
        fila = conn.execute(
            """
            update cuentas
               set saldo = saldo + %s,
                   contratado_en = coalesce(contratado_en, now())
             where id = %s
             returning saldo, contratado_en
            """,
            (total, usuario["cuenta_id"]),
        ).fetchone()

        # Queda el movimiento para que el saldo siempre se pueda explicar: la
        # suma de los movimientos tiene que cuadrar con `cuentas.saldo`. Se
        # guarda además quién lo cargó.
        conn.execute(
            """
            insert into movimientos_saldo (cuenta_id, usuario_id, tipo, monto, detalle)
                 values (%s, %s, 'carga', %s, %s)
            """,
            (usuario["cuenta_id"], usuario["id"], total, f"Pack {pack_id}"),
        )

    return {"saldo": fila["saldo"], "contratado": fila["contratado_en"] is not None}

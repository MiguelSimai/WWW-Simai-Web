import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .config import config
from .db import pool
from .dependencias import sesion_actual

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cuenta", tags=["cuenta"])

# Los montos viven en el servidor. Si el front mandara el monto, cualquiera
# podría cargarse un millón de saldo editando la petición: el cliente elige
# QUÉ pack, nunca CUÁNTO vale.
PACKS: dict[str, dict] = {
    "prueba": {"monto": 30_000, "bonus": 0},
    "impulso": {"monto": 100_000, "bonus": 8_000},
    "volumen": {"monto": 300_000, "bonus": 45_000},
}

# Cuántas recargas sin resolver se le aceptan a una cuenta.
#
# No es un límite de negocio: es para que un error de la pantalla —o alguien
# apretando el botón diez veces— no deje una fila de declaraciones que hay que
# revisar una por una contra la cartola.
MAX_PENDIENTES = 3


class RecargaDeclarada(BaseModel):
    """Lo que el cliente dice haber transferido."""

    # Opcional: se puede declarar un monto libre sin elegir pack.
    pack_id: str | None = None
    monto_declarado: int = Field(gt=0)
    # El N° de transferencia. Es lo que permite encontrarla en la cartola, así
    # que sin esto la declaración no sirve para nada.
    referencia: str = Field(min_length=1, max_length=200)


@router.get("/transferencia")
def datos_transferencia(usuario: dict = Depends(sesion_actual)):
    """
    A dónde transferir. Requiere sesión: no es información pública.

    Si no está configurada se dice explícitamente, para que la pantalla ofrezca
    contactar en vez de mostrar una cuenta a medias — alguien podría transferir
    a ninguna parte.
    """
    if not config.transferencia_configurada:
        return {"configurada": False}

    return {
        "configurada": True,
        "banco": config.transferencia_banco,
        "tipo": config.transferencia_tipo,
        "numero": config.transferencia_numero,
        "rut": config.transferencia_rut,
        "titular": config.transferencia_titular,
        "email": config.transferencia_email,
    }


@router.post("/recargas", status_code=201)
def declarar_recarga(datos: RecargaDeclarada, usuario: dict = Depends(sesion_actual)):
    """
    Registra que el cliente transfirió, para que alguien lo verifique.

    **No mueve el saldo.** Eso ocurre cuando se aprueba desde la
    administración, contra la cartola del banco. Este endpoint ocupa el lugar
    que tendría el webhook de una pasarela de pago: la confirmación llega de
    afuera, y sólo entonces hay plata.

    Lo que el cliente declara no es lo que se acredita: sirve para encontrar la
    transferencia y para que la diferencia, si la hay, quede a la vista.
    """
    if not config.transferencia_configurada:
        raise HTTPException(
            status_code=503,
            detail="La recarga por transferencia no está disponible. Escríbenos.",
        )

    if not usuario.get("cuenta_id"):
        raise HTTPException(status_code=403, detail="Tu usuario no tiene una cuenta asociada.")

    if datos.pack_id is not None and datos.pack_id not in PACKS:
        raise HTTPException(status_code=404, detail="Pack desconocido")

    referencia = datos.referencia.strip()
    if not referencia:
        raise HTTPException(status_code=422, detail="La referencia es obligatoria")

    with pool.connection() as conn:
        pendientes = conn.execute(
            "select count(*) as n from recargas where cuenta_id = %s and estado = 'pendiente'",
            (usuario["cuenta_id"],),
        ).fetchone()["n"]

        if pendientes >= MAX_PENDIENTES:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Ya tienes {pendientes} recargas por verificar. "
                    "Espera a que las revisemos antes de declarar otra."
                ),
            )

        fila = conn.execute(
            """
            insert into recargas (cuenta_id, usuario_id, pack_id, monto_declarado, referencia)
                 values (%s, %s, %s, %s, %s)
              returning id, monto_declarado, referencia, estado, creada_en
            """,
            (
                usuario["cuenta_id"],
                usuario["id"],
                datos.pack_id,
                datos.monto_declarado,
                referencia,
            ),
        ).fetchone()

    logger.info(
        "%s declaró una transferencia de %s (ref: %s)",
        usuario["email"], datos.monto_declarado, referencia,
    )
    return dict(fila)


@router.get("/recargas")
def mis_recargas(usuario: dict = Depends(sesion_actual)):
    """
    Las recargas de la cuenta, para que el cliente vea en qué van.

    Son de la cuenta y no de la persona: quien transfirió puede no ser quien
    consulta, y el saldo lo comparten igual.
    """
    if not usuario.get("cuenta_id"):
        return {"recargas": []}

    with pool.connection() as conn:
        filas = conn.execute(
            """
            select id, pack_id, monto_declarado, referencia, estado,
                   monto_acreditado, nota, creada_en, resuelta_en
              from recargas
             where cuenta_id = %s
             order by creada_en desc
             limit 10
            """,
            (usuario["cuenta_id"],),
        ).fetchall()

    return {"recargas": [dict(f) for f in filas]}

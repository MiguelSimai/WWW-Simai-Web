from typing import Any


def enlazar_o_crear(
    conn: Any,
    *,
    proveedor: str,
    sujeto: str,
    email: str,
    nombre: str,
    email_verificado: bool,
) -> dict:
    """
    Devuelve el usuario correspondiente a una identidad externa, creándolo si
    es la primera vez que entra.

    Reglas de enlace, en orden:

    1. Si ya conocemos (proveedor, sujeto), ese es el usuario. Punto.
    2. Si no, y el proveedor confirma que el correo está verificado, lo
       enlazamos al usuario que tenga ese correo.
    3. Si no existe nadie con ese correo, creamos el usuario.

    El paso 2 exige `email_verificado` a propósito: enlazar cuentas por un
    correo no verificado permite que alguien reclame la cuenta de otro
    registrando ese correo en un proveedor que no lo valida.
    """
    fila = conn.execute(
        """
        select u.id, u.email, u.nombre
          from identidades i
          join usuarios u on u.id = i.usuario_id
         where i.proveedor = %s and i.sujeto = %s
        """,
        (proveedor, sujeto),
    ).fetchone()

    if fila is None:
        if not email_verificado:
            raise ValueError("El proveedor no confirmó el correo; no se enlaza la cuenta.")

        fila = conn.execute(
            """
            insert into usuarios (email, nombre)
                 values (%s, %s)
            on conflict (email) do update set nombre = excluded.nombre
              returning id, email, nombre
            """,
            (email, nombre),
        ).fetchone()

        conn.execute(
            "insert into identidades (usuario_id, proveedor, sujeto) values (%s, %s, %s)",
            (fila["id"], proveedor, sujeto),
        )

    # Todo usuario tiene que pertenecer a una cuenta: es donde vive el saldo y
    # los procesos contratados. Al entrar por primera vez se le crea una propia,
    # y si después debe compartir la de su empresa se reasigna a mano — deducir
    # la empresa por el dominio del correo mezclaría saldos de gente que no
    # tiene relación (gmail.com, por ejemplo).
    conn.execute(
        """
        with nueva as (
          insert into cuentas (nombre)
          select %(nombre)s
           where not exists (
             select 1 from usuarios where id = %(id)s and cuenta_id is not null
           )
          returning id
        )
        update usuarios
           set cuenta_id = (select id from nueva)
         where id = %(id)s and cuenta_id is null
        """,
        {"id": fila["id"], "nombre": nombre or email},
    )

    conn.execute("update usuarios set ultimo_acceso_en = now() where id = %s", (fila["id"],))
    return fila

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    secret_key: str
    session_hours: int = 8

    # En producción tiene que ser True: sin esto la cookie viaja en claro.
    cookie_secure: bool = True

    frontend_url: str = "http://localhost:4200"

    # --- Datos de transferencia ---
    #
    # Lo que se le muestra al cliente para que pague. Van en configuración y no
    # en la base: cambian casi nunca, y la cuenta bancaria a la que llega la
    # plata no es un dato que deba poder editarse desde el producto.
    #
    # Sin `transferencia_banco` y `transferencia_numero` el portal no ofrece la
    # recarga: es preferible no mostrar la pantalla que mostrarla incompleta y
    # que alguien transfiera a ninguna parte.
    transferencia_banco: str = ""
    transferencia_tipo: str = "Cuenta Corriente"
    transferencia_numero: str = ""
    transferencia_rut: str = ""
    transferencia_titular: str = ""
    # Dónde avisar que transfirió, además de quedar registrado en el portal.
    transferencia_email: str = ""

    @property
    def transferencia_configurada(self) -> bool:
        return bool(self.transferencia_banco and self.transferencia_numero)

    # --- Microsoft Entra ID (opcional) ---
    #
    # Vacío significa que el proveedor no se ofrece. Es a propósito: el portal
    # tiene que arrancar igual mientras la app no esté dada de alta en Entra, y
    # el front pregunta por /api/auth/proveedores para no mostrar un botón que
    # el servidor no puede atender.
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = ""

    @property
    def microsoft_habilitado(self) -> bool:
        return bool(
            self.microsoft_client_id
            and self.microsoft_client_secret
            and self.microsoft_redirect_uri
        )

    # Correos que pueden entrar a la administración: dar de alta cuentas,
    # habilitarles servicios y mover usuarios entre cuentas.
    #
    # Va en configuración y no en la base a propósito: quién administra el
    # producto no es un dato que deba poder cambiarse desde el producto mismo.
    # Separados por coma.
    admin_emails: str = ""

    @property
    def administradores(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    # --- Motor de procesamiento (gateway IA) ---

    # Simula el motor: no llama al gateway ni escribe en su base. Sirve para
    # probar el portal entero —validar, medir, cobrar, listar— sin levantar la
    # arquitectura de procesamiento. Los expedientes quedan en 'procesando'
    # para siempre, porque nadie va a mandar el callback.
    #
    # Mismo espíritu que AuthMock en el front: por defecto está apagado, así
    # que si nadie lo enciende el portal intenta trabajar de verdad y falla
    # ruidosamente, en vez de fingir en silencio.
    motor_simulado: bool = False

    gateway_url: str = "http://localhost:8010"

    # Base del motor. El portal solo escribe ahí el registro del expediente
    # que N8N necesita para saber cuándo está completo (ver motor_db.py).
    # Obligatoria salvo en modo simulado.
    motor_database_url: str = ""

    # Empresa y canal con que el portal se identifica ante el gateway. Tienen
    # que existir en la base del motor (`iagw_empresa`, `iagw_canal`): se crean
    # desde IA-ADMIN, que es la consola del motor.
    gateway_empresa_id: int = 1
    gateway_canal: str = "portal-simai"

    # URL pública de ESTE backend, la que el motor usa para el callback. En
    # local no sirve `localhost` si el motor corre en otra máquina o contenedor.
    public_url: str = "http://localhost:8000"

    # Secreto compartido con el motor para el endpoint de callback. Ese
    # endpoint no lleva cookie de sesión —lo llama un servidor, no un
    # navegador—, así que este token es lo único que lo protege.
    #
    # Vacío no es "sin protección": es callback deshabilitado. Sin token
    # configurado el endpoint rechaza todo, en vez de quedar abierto.
    callback_token: str = ""

    # Segundos que el portal espera al gateway al encolar. No procesa nada en
    # esa llamada: solo valida y encola, así que no hace falta más.
    gateway_timeout: int = 30

    @model_validator(mode="after")
    def revisar_motor(self) -> "Config":
        """
        Fuera del modo simulado, el motor tiene que estar configurado.

        Es preferible no arrancar a arrancar y descubrirlo cuando un cliente
        sube su primer expediente.
        """
        if not self.motor_simulado and not self.motor_database_url:
            raise ValueError(
                "Falta MOTOR_DATABASE_URL. Ponla, o usa MOTOR_SIMULADO=true "
                "para probar el portal sin el motor de procesamiento."
            )
        return self


config = Config()  # type: ignore[call-arg]

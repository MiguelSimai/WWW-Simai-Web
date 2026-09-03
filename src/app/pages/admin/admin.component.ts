import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AdminService, CuentaAdmin } from '../../core/admin.service';
import { CATALOGO } from '../../core/catalogo';
import { ServicioId } from '../../core/modelos';

@Component({
  selector: 'app-admin',
  imports: [CurrencyPipe, DatePipe, ReactiveFormsModule],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly fb = inject(FormBuilder);

  protected readonly cuentas = this.admin.cuentas;
  protected readonly usuarios = this.admin.usuarios;
  protected readonly plantillas = this.admin.plantillas;
  protected readonly recargas = this.admin.recargas;

  /** La bandeja de trabajo: lo que hay que buscar en la cartola. */
  protected readonly pendientes = computed(() =>
    this.recargas().filter((r) => r.estado === 'pendiente'),
  );

  /** Las resueltas, para poder mirar atrás sin ir a la base. */
  protected readonly resueltas = computed(() =>
    this.recargas().filter((r) => r.estado !== 'pendiente'),
  );

  protected readonly errorRecarga = signal<string | null>(null);

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);

  /** Todos los servicios, incluidos los que el motor no procesa todavía. */
  protected readonly servicios = CATALOGO;

  /** A qué cuenta se le está habilitando un servicio. */
  protected readonly editando = signal<string | null>(null);

  /* ===== Búsqueda y ruido =================================================
     Cada persona que entra por primera vez crea un usuario **y** una cuenta
     propia y vacía. O sea que las dos listas crecen con los registros, no con
     los clientes: sin filtrar, un puñado de curiosos entierra a los clientes
     reales. */

  protected readonly busquedaCuentas = signal('');
  protected readonly busquedaUsuarios = signal('');

  /** Las cuentas vacías se ocultan por defecto: son registros, no clientes. */
  protected readonly mostrarVacias = signal(false);

  /**
   * Una cuenta sin nada: ni saldo, ni usuarios, ni expedientes, ni servicios.
   * Con cualquiera de las cuatro cosas ya es algo que alguien decidió.
   */
  private sinActividad(c: CuentaAdmin): boolean {
    return (
      c.saldo === 0 && c.usuarios === 0 && c.solicitudes === 0 && c.procesos.length === 0
    );
  }

  protected readonly cuentasVisibles = computed(() => {
    const texto = this.busquedaCuentas().trim().toLowerCase();

    return this.cuentas().filter((c) => {
      // La búsqueda pasa por encima del filtro de vacías: si escribiste un
      // nombre, quieres esa cuenta exista o no tenga actividad.
      if (texto) {
        return (
          c.nombre.toLowerCase().includes(texto) || (c.rut ?? '').includes(texto)
        );
      }
      return this.mostrarVacias() || !this.sinActividad(c);
    });
  });

  protected readonly cuentasOcultas = computed(() =>
    this.busquedaCuentas().trim() || this.mostrarVacias()
      ? 0
      : this.cuentas().filter((c) => this.sinActividad(c)).length,
  );

  protected readonly usuariosVisibles = computed(() => {
    const texto = this.busquedaUsuarios().trim().toLowerCase();
    if (!texto) {
      return this.usuarios();
    }
    return this.usuarios().filter(
      (u) =>
        u.email.toLowerCase().includes(texto) ||
        (u.nombre ?? '').toLowerCase().includes(texto) ||
        (u.cuenta ?? '').toLowerCase().includes(texto),
    );
  });

  protected escribir(destino: { set(v: string): void }, evento: Event): void {
    destino.set((evento.target as HTMLInputElement).value);
  }

  protected readonly formCuenta = this.fb.nonNullable.group({
    nombre: ['', Validators.required],
    // El RUT no se exige al crear: la cuenta suele abrirse antes de tener los
    // datos tributarios. Se completa después desde la ficha.
    rut: [''],
  });

  /** Qué cuenta tiene abierto el formulario de RUT. */
  protected readonly editandoRut = signal<string | null>(null);

  protected readonly formRut = this.fb.nonNullable.group({
    rut: ['', Validators.required],
  });

  /** Qué cuenta tiene abierto el formulario de saldo. */
  protected readonly acreditando = signal<string | null>(null);

  // El error va junto al campo y no en el aviso de arriba: son formularios que
  // se abren dentro de la ficha, y a esa altura de la página el mensaje de la
  // cabecera queda fuera de la vista.
  protected readonly errorSaldo = signal<string | null>(null);
  protected readonly errorRut = signal<string | null>(null);

  protected readonly formSaldo = this.fb.nonNullable.group({
    monto: [0, [Validators.required]],
    referencia: ['', Validators.required],
  });

  protected readonly formProceso = this.fb.nonNullable.group({
    servicio: ['documentos' as ServicioId, Validators.required],
    tipo_servicio: ['documentos', Validators.required],
    proceso_codigo: ['', Validators.required],
    id_proceso: [0, [Validators.required, Validators.min(1)]],
    plantilla_id: [''],
  });

  async ngOnInit(): Promise<void> {
    await this.recargar();
  }

  private async recargar(): Promise<void> {
    this.cargando.set(true);
    try {
      await this.admin.cargar();
      this.error.set(null);
    } catch {
      this.error.set('No pudimos cargar la administración.');
    } finally {
      this.cargando.set(false);
    }
  }

  protected async crearCuenta(): Promise<void> {
    if (this.formCuenta.invalid) {
      return;
    }
    try {
      const { nombre, rut } = this.formCuenta.getRawValue();
      await this.admin.crearCuenta(nombre.trim(), rut.trim() || null);
      // Nace sin actividad, así que sin esto quedaría oculta justo después de
      // crearla.
      this.mostrarVacias.set(true);
      this.formCuenta.reset({ nombre: '', rut: '' });
      this.error.set(null);
    } catch {
      // El 422 del RUT inválido cae acá igual que cualquier otro fallo; el
      // mensaje lo menciona porque es la causa más probable.
      this.error.set('No pudimos crear la cuenta. Si escribiste un RUT, revísalo.');
    }
  }

  protected abrirProceso(cuenta: CuentaAdmin): void {
    this.editando.set(cuenta.id);
    this.formProceso.reset({
      servicio: 'documentos',
      tipo_servicio: 'documentos',
      proceso_codigo: '',
      id_proceso: 0,
      plantilla_id: '',
    });
  }

  protected cerrarProceso(): void {
    this.editando.set(null);
  }

  /**
   * El tipo de servicio del motor suele llamarse igual que el servicio del
   * portal, así que se propone ese valor al elegir. Sigue siendo editable
   * porque en el motor puede estar nombrado distinto.
   */
  protected alElegirServicio(valor: string): void {
    this.formProceso.patchValue({ tipo_servicio: valor });
  }

  protected async habilitar(cuentaId: string): Promise<void> {
    if (this.formProceso.invalid) {
      return;
    }
    const datos = this.formProceso.getRawValue();
    try {
      await this.admin.habilitarProceso(cuentaId, {
        ...datos,
        id_proceso: Number(datos.id_proceso),
        plantilla_id: datos.plantilla_id || null,
      });
      this.editando.set(null);
      this.error.set(null);
    } catch {
      this.error.set('No pudimos habilitar el servicio. Revisa los datos del proceso.');
    }
  }

  /**
   * El motivo que devuelve el servidor, que es el útil: cuál debería ser el
   * dígito verificador, o cuánto saldo tiene la cuenta. Un mensaje propio sólo
   * repetiría "no se pudo".
   */
  private detalle(error: unknown, porDefecto: string): string {
    const detail = (error as { error?: { detail?: unknown } })?.error?.detail;
    return typeof detail === 'string' && detail ? detail : porDefecto;
  }

  protected abrirSaldo(cuenta: CuentaAdmin): void {
    this.acreditando.set(cuenta.id);
    this.errorSaldo.set(null);
    this.formSaldo.reset({ monto: 0, referencia: '' });
  }

  protected cerrarSaldo(): void {
    this.acreditando.set(null);
    this.errorSaldo.set(null);
  }

  protected async acreditar(cuentaId: string): Promise<void> {
    const { monto, referencia } = this.formSaldo.getRawValue();

    if (Number(monto) === 0) {
      this.errorSaldo.set('El monto no puede ser cero.');
      return;
    }

    if (!referencia.trim()) {
      this.errorSaldo.set('La referencia es obligatoria: es lo que permite reconciliar el pago.');
      return;
    }

    try {
      await this.admin.cargarSaldo(cuentaId, Number(monto), referencia.trim());
      this.acreditando.set(null);
      this.errorSaldo.set(null);
    } catch (error) {
      this.errorSaldo.set(this.detalle(error, 'No pudimos acreditar el saldo.'));
    }
  }

  protected abrirRut(cuenta: CuentaAdmin): void {
    this.editandoRut.set(cuenta.id);
    this.errorRut.set(null);
    this.formRut.reset({ rut: cuenta.rut ?? '' });
  }

  protected cerrarRut(): void {
    this.editandoRut.set(null);
    this.errorRut.set(null);
  }

  protected async guardarRut(cuentaId: string): Promise<void> {
    const rut = this.formRut.getRawValue().rut.trim();

    if (!rut) {
      this.errorRut.set('Escribe el RUT de la empresa.');
      return;
    }

    try {
      await this.admin.fijarRut(cuentaId, rut);
      this.editandoRut.set(null);
      this.errorRut.set(null);
    } catch (error) {
      this.errorRut.set(this.detalle(error, 'No pudimos guardar el RUT.'));
    }
  }

  protected async acreditarRecarga(id: string, monto: string, nota: string): Promise<void> {
    const valor = Number(monto);

    if (!Number.isFinite(valor) || valor <= 0) {
      this.errorRecarga.set('El monto a acreditar tiene que ser mayor que cero.');
      return;
    }

    try {
      await this.admin.acreditarRecarga(id, valor, nota.trim() || null);
      this.errorRecarga.set(null);
    } catch (error) {
      this.errorRecarga.set(this.detalle(error, 'No pudimos acreditar la recarga.'));
    }
  }

  protected async rechazarRecarga(id: string, nota: string): Promise<void> {
    if (!nota.trim()) {
      // Obligatoria porque el cliente la va a ver: "rechazada" sin motivo
      // termina en una llamada telefónica.
      this.errorRecarga.set('Escribe el motivo del rechazo: el cliente lo va a ver.');
      return;
    }

    try {
      await this.admin.rechazarRecarga(id, nota.trim());
      this.errorRecarga.set(null);
    } catch (error) {
      this.errorRecarga.set(this.detalle(error, 'No pudimos rechazar la recarga.'));
    }
  }

  /** Mensaje de la última acción, para confirmar que algo pasó. */
  protected readonly aviso = signal<string | null>(null);

  protected async cerrarSesiones(usuarioId: string, email: string): Promise<void> {
    try {
      const cerradas = await this.admin.cerrarSesiones(usuarioId);
      this.aviso.set(
        cerradas
          ? `Se cerraron ${cerradas} sesión(es) de ${email}. Tendrá que volver a entrar.`
          : `${email} no tenía sesiones abiertas.`,
      );
      this.error.set(null);
    } catch (error) {
      this.error.set(this.detalle(error, 'No pudimos cerrar sus sesiones.'));
    }
  }

  protected async quitar(cuentaId: string, servicio: string): Promise<void> {
    try {
      await this.admin.quitarProceso(cuentaId, servicio);
    } catch {
      this.error.set('No pudimos quitar el servicio.');
    }
  }

  /**
   * Cuentas que se pueden fusionar dentro de una: las demás que tengan algo
   * que traspasar. Ofrecer una cuenta vacía sería ruido.
   */
  protected fusionables(destino: CuentaAdmin): readonly CuentaAdmin[] {
    return this.cuentas().filter(
      (c) => c.id !== destino.id && (c.saldo > 0 || c.solicitudes > 0 || c.usuarios > 0),
    );
  }

  protected async fusionar(destinoId: string, origenId: string): Promise<void> {
    if (!origenId) {
      return;
    }
    try {
      await this.admin.fusionar(destinoId, origenId);
      this.error.set(null);
    } catch {
      this.error.set('No pudimos fusionar las cuentas.');
    }
  }

  protected async mover(usuarioId: string, cuentaId: string): Promise<void> {
    if (!cuentaId) {
      return;
    }
    try {
      await this.admin.moverUsuario(usuarioId, cuentaId);
      this.error.set(null);
    } catch {
      this.error.set('No pudimos mover el usuario.');
    }
  }

  protected nombreServicio(id: string): string {
    return this.servicios.find((s) => s.id === id)?.nombre ?? id;
  }
}

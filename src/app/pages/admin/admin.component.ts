import { CurrencyPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AdminService, CuentaAdmin } from '../../core/admin.service';
import { CATALOGO } from '../../core/catalogo';
import { ServicioId } from '../../core/modelos';

@Component({
  selector: 'app-admin',
  imports: [CurrencyPipe, ReactiveFormsModule],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly fb = inject(FormBuilder);

  protected readonly cuentas = this.admin.cuentas;
  protected readonly usuarios = this.admin.usuarios;
  protected readonly plantillas = this.admin.plantillas;

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);

  /** Todos los servicios, incluidos los que el motor no procesa todavía. */
  protected readonly servicios = CATALOGO;

  /** A qué cuenta se le está habilitando un servicio. */
  protected readonly editando = signal<string | null>(null);

  /** Los usuarios que están solos en su cuenta: candidatos a agrupar. */
  protected readonly sueltos = computed(() =>
    this.usuarios().filter((u) => {
      const cuenta = this.cuentas().find((c) => c.id === u.cuenta_id);
      return !cuenta || cuenta.usuarios === 1;
    }),
  );

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

  protected abrirSaldo(cuenta: CuentaAdmin): void {
    this.acreditando.set(cuenta.id);
    this.formSaldo.reset({ monto: 0, referencia: '' });
  }

  protected cerrarSaldo(): void {
    this.acreditando.set(null);
  }

  protected async acreditar(cuentaId: string): Promise<void> {
    const { monto, referencia } = this.formSaldo.getRawValue();

    if (this.formSaldo.invalid || Number(monto) === 0 || !referencia.trim()) {
      return;
    }

    try {
      await this.admin.cargarSaldo(cuentaId, Number(monto), referencia.trim());
      this.acreditando.set(null);
      this.error.set(null);
    } catch {
      // El backend rechaza el saldo negativo y la referencia vacía; el mensaje
      // se queda genérico porque el 404 de esta sección no distingue causas.
      this.error.set('No pudimos acreditar el saldo. Revisa el monto.');
    }
  }

  protected abrirRut(cuenta: CuentaAdmin): void {
    this.editandoRut.set(cuenta.id);
    this.formRut.reset({ rut: cuenta.rut ?? '' });
  }

  protected cerrarRut(): void {
    this.editandoRut.set(null);
  }

  protected async guardarRut(cuentaId: string): Promise<void> {
    const rut = this.formRut.getRawValue().rut.trim();
    if (!rut) {
      return;
    }
    try {
      await this.admin.fijarRut(cuentaId, rut);
      this.editandoRut.set(null);
      this.error.set(null);
    } catch {
      this.error.set('RUT inválido, o ya está en otra cuenta.');
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

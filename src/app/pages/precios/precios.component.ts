import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { CurrencyPipe, LowerCasePipe } from '@angular/common';
import { Router } from '@angular/router';
import { AUTH } from '../../core/auth';
import { CuentaService } from '../../core/cuenta.service';
import { CATALOGO, servicioPorId } from '../../core/catalogo';
import { ServicioId } from '../../core/modelos';
import { IconComponent } from '../../ui/icon/icon.component';

interface Pack {
  readonly id: string;
  readonly nombre: string;
  readonly monto: number;
  /** Saldo extra de regalo, en CLP. */
  readonly bonus: number;
  readonly para: string;
  readonly destacado: boolean;
}

interface Pregunta {
  readonly pregunta: string;
  readonly respuesta: string;
}

@Component({
  selector: 'app-precios',
  imports: [CurrencyPipe, LowerCasePipe, ReactiveFormsModule, IconComponent],
  templateUrl: './precios.component.html',
  styleUrl: './precios.component.scss',
})
export class PreciosComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AUTH);
  private readonly cuenta = inject(CuentaService);
  private readonly router = inject(Router);

  protected readonly autenticado = this.auth.autenticado;
  protected readonly usuario = this.auth.usuario;
  protected readonly procesando = signal(false);
  protected readonly errorContratar = signal<string | null>(null);

  /** Datos bancarios que se le muestran al cliente. Los entrega el servidor. */
  protected readonly transferencia = this.cuenta.transferencia;

  /** Queda en true tras declarar, para mostrar el acuse en vez del formulario. */
  protected readonly declarada = signal(false);

  async ngOnInit(): Promise<void> {
    // Requiere sesión, así que sólo tiene sentido pedirlo si ya entró.
    if (this.autenticado()) {
      await this.cuenta.cargarTransferencia();
    }
  }

  protected readonly servicios = CATALOGO;

  /* ===== Calculadora ===== */

  protected readonly servicioSel = signal<ServicioId>('transcripcion');
  protected readonly cantidad = signal(120);

  protected readonly servicioActivo = computed(() => servicioPorId(this.servicioSel()));
  protected readonly estimado = computed(() => this.servicioActivo().precio * this.cantidad());

  protected cambiarServicio(event: Event): void {
    this.servicioSel.set((event.target as HTMLSelectElement).value as ServicioId);
  }

  protected cambiarCantidad(event: Event): void {
    const valor = Number((event.target as HTMLInputElement).value);
    this.cantidad.set(Number.isFinite(valor) && valor > 0 ? Math.floor(valor) : 0);
  }

  /* ===== Packs de saldo ===== */

  protected readonly packs: readonly Pack[] = [
    {
      id: 'prueba',
      nombre: 'Prueba',
      monto: 30_000,
      bonus: 0,
      para: 'Para medir resultados con material propio antes de comprometer volumen.',
      destacado: false,
    },
    {
      id: 'impulso',
      nombre: 'Impulso',
      monto: 100_000,
      bonus: 8_000,
      para: 'Para un equipo que ya incorporó el servicio a su rutina semanal.',
      destacado: true,
    },
    {
      id: 'volumen',
      nombre: 'Volumen',
      monto: 300_000,
      bonus: 45_000,
      para: 'Para procesamiento continuo o integrado por API a tus sistemas.',
      destacado: false,
    },
  ];

  protected readonly packSel = signal('impulso');

  protected seleccionarPack(id: string): void {
    this.packSel.set(id);
  }

  protected readonly packActivo = computed(
    () => this.packs.find((p) => p.id === this.packSel()) ?? this.packs[0],
  );

  /* ===== Contratación ===== */

  protected readonly formulario = this.fb.nonNullable.group({
    nombre: ['', [Validators.required, Validators.minLength(3)]],
    email: ['', [Validators.required, Validators.email]],
    empresa: [''],
    // Sólo se exige a quien ya entró y está declarando: es el dato que permite
    // encontrar la transferencia en la cartola.
    referencia: [''],
  });

  protected readonly enviado = signal(false);

  protected get f() {
    return this.formulario.controls;
  }

  /**
   * Quien no ha entrado pasa por el login y vuelve aquí. Quien ya entró declara
   * la transferencia que hizo — **esto no acredita saldo**: lo mueve alguien al
   * verificarla contra la cartola.
   */
  protected async contratar(): Promise<void> {
    this.errorContratar.set(null);

    if (!this.autenticado()) {
      this.enviado.set(true);
      // La referencia no aplica a quien todavía no entró.
      if (this.f.nombre.invalid || this.f.email.invalid) {
        return;
      }
      // Con un solo proveedor se va derecho al login y se ahorra una pantalla.
      // Con varios, la elección vive en /ingresar y no se duplica acá.
      const disponibles = this.auth.proveedores();
      if (disponibles.length === 1) {
        this.auth.irALogin('/precios', disponibles[0]);
      } else {
        this.router.navigate(['/ingresar'], { queryParams: { volver: '/precios' } });
      }
      return;
    }

    this.enviado.set(true);
    const referencia = this.f.referencia.value.trim();

    if (!referencia) {
      this.errorContratar.set(
        'Escribe el N° de la transferencia: es lo que nos permite encontrarla.',
      );
      return;
    }

    this.procesando.set(true);
    try {
      await this.cuenta.declarar(
        this.packSel(),
        this.packActivo().monto,
        referencia,
      );
      this.declarada.set(true);
    } catch (error) {
      const detail = (error as { error?: { detail?: unknown } })?.error?.detail;
      this.errorContratar.set(
        typeof detail === 'string' && detail
          ? detail
          : 'No pudimos registrar tu transferencia. Inténtalo de nuevo.',
      );
    } finally {
      this.procesando.set(false);
    }
  }

  protected readonly preguntas: readonly Pregunta[] = [
    {
      pregunta: '¿El saldo tiene vencimiento?',
      respuesta:
        'No. El saldo cargado queda disponible hasta que lo uses. Si un mes no procesas nada, no se descuenta ni se pierde.',
    },
    {
      pregunta: '¿Qué pasa si un trabajo falla?',
      respuesta:
        'No se cobra. Si un archivo llega corrupto o el proceso falla por nuestro lado, la solicitud queda marcada con error y el saldo se devuelve completo.',
    },
    {
      pregunta: '¿Los precios incluyen IVA?',
      respuesta:
        'Las tarifas se muestran sin IVA. La boleta o factura se emite al cargar saldo, no en cada solicitud.',
    },
    {
      pregunta: '¿Puedo integrarlo a mis sistemas?',
      respuesta:
        'Sí. Todos los servicios están disponibles por API con la misma tarifa del portal. La clave se genera desde tu panel.',
    },
  ];
}

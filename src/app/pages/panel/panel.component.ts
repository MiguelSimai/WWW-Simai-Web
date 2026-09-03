import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AUTH } from '../../core/auth';
import { servicioPorId } from '../../core/catalogo';
import {
  BADGE_ESTADO,
  Documento,
  ETIQUETA_ESTADO,
  EstadoSolicitud,
  Solicitud,
} from '../../core/modelos';
import { CuentaService } from '../../core/cuenta.service';
import { FILTRO_VACIO, SolicitudesService } from '../../core/solicitudes.service';
import { IconComponent, IconName } from '../../ui/icon/icon.component';

type Filtro = EstadoSolicitud | 'todas';

interface OpcionFiltro {
  readonly valor: Filtro;
  readonly label: string;
}

interface Indicador {
  readonly icono: IconName;
  readonly label: string;
  readonly valor: string;
  readonly nota: string;
}

@Component({
  selector: 'app-panel',
  imports: [CurrencyPipe, DatePipe, RouterLink, IconComponent],
  templateUrl: './panel.component.html',
  styleUrl: './panel.component.scss',
})
export class PanelComponent implements OnInit, OnDestroy {
  private readonly auth = inject(AUTH);
  private readonly solicitudesSvc = inject(SolicitudesService);
  private readonly cuenta = inject(CuentaService);

  protected readonly usuario = this.auth.usuario;

  /**
   * Las recargas de la cuenta.
   *
   * Sin esto el cliente declara una transferencia y no vuelve a saber nada:
   * el saldo cambia solo, sin explicación, y no tiene dónde ver si su pago se
   * verificó o se rechazó.
   */
  protected readonly recargas = this.cuenta.recargas;

  /** Cuántas recargas se ven sin desplegar. Las viejas rara vez importan. */
  private static readonly RECARGAS_VISIBLES = 3;

  protected readonly verTodasRecargas = signal(false);

  protected readonly recargasVisibles = computed(() =>
    this.verTodasRecargas()
      ? this.recargas()
      : this.recargas().slice(0, PanelComponent.RECARGAS_VISIBLES),
  );

  protected readonly recargasOcultas = computed(() =>
    Math.max(0, this.recargas().length - PanelComponent.RECARGAS_VISIBLES),
  );
  protected readonly cargando = this.solicitudesSvc.cargando;
  protected readonly errorCarga = this.solicitudesSvc.error;

  ngOnInit(): void {
    // Queda pendiente mientras haya algo en proceso: el resultado llega por
    // callback desde el motor, no cuando el cliente abre la página.
    void this.solicitudesSvc.vigilar();
    // Sin await: la lista de expedientes es lo que se vino a ver, y esto es
    // información secundaria que puede aparecer un instante después.
    void this.cuenta.cargarRecargas();
  }

  /** Etiqueta y color del estado de una recarga. */
  protected readonly ESTADO_RECARGA: Readonly<Record<string, string>> = {
    pendiente: 'En verificación',
    acreditada: 'Acreditada',
    rechazada: 'Rechazada',
  };

  protected readonly BADGE_RECARGA: Readonly<Record<string, string>> = {
    pendiente: 'badge--proceso',
    acreditada: 'badge--ok',
    rechazada: 'badge--error',
  };

  ngOnDestroy(): void {
    this.solicitudesSvc.detener();
  }

  /**
   * Quien entró pero nunca cargó saldo no tiene nada que mirar aquí: en vez
   * de un panel vacío, se le ofrece contratar.
   */
  protected readonly contratado = computed(() => this.usuario()?.contratado === true);

  /** El filtro lo guarda el servicio: es lo que viaja en cada consulta. */
  protected readonly filtro = computed(() => this.solicitudesSvc.filtro().estado);
  protected readonly pagina = this.solicitudesSvc.pagina;
  protected readonly hayMas = this.solicitudesSvc.hayMas;
  protected readonly conteos = this.solicitudesSvc.conteos;

  /** Lo que el usuario escribe, antes de mandarlo. */
  protected readonly busqueda = signal('');
  protected readonly filtroDesde = signal('');
  protected readonly filtroHasta = signal('');

  protected readonly hayFiltroActivo = computed(() => {
    const f = this.solicitudesSvc.filtro();
    return f.estado !== 'todas' || !!f.desde || !!f.hasta || !!f.buscar;
  });

  protected readonly opciones: readonly OpcionFiltro[] = [
    { valor: 'todas', label: 'Todas' },
    { valor: 'procesando', label: 'Procesando' },
    { valor: 'revisar', label: 'Requieren revisión' },
    { valor: 'completada', label: 'Completadas' },
    { valor: 'error', label: 'Con error' },
  ];

  // El servidor ya devuelve la página filtrada: acá no se filtra nada. Antes
  // se filtraba sobre lo cargado, y eso escondía todo lo que estuviera más
  // allá de la primera página.
  protected readonly visibles = this.solicitudesSvc.solicitudes;

  protected readonly indicadores = computed<readonly Indicador[]>(() => [
    {
      icono: 'pago',
      label: 'Saldo disponible',
      valor: this.formatearPesos(this.usuario()?.saldo ?? 0),
      nota: 'No vence',
    },
    {
      icono: 'grafico',
      label: 'Gasto del período',
      valor: this.formatearPesos(this.solicitudesSvc.gastoTotal()),
      nota: `${this.solicitudesSvc.total()} solicitudes`,
    },
    {
      icono: 'reloj',
      label: 'En proceso',
      valor: String(this.solicitudesSvc.enProceso()),
      nota: 'Se avisa al terminar',
    },
    {
      icono: 'evidencia',
      label: 'Requieren revisión',
      valor: String(this.solicitudesSvc.porRevisar()),
      nota: 'Esperan tu decisión',
    },
  ]);

  protected async cambiarFiltro(valor: Filtro): Promise<void> {
    await this.solicitudesSvc.filtrar({ estado: valor });
  }

  protected async aplicarBusqueda(evento?: Event): Promise<void> {
    // `submit` nativo y no `ngSubmit`: el panel no importa FormsModule, y sin
    // esto el formulario recargaría la página entera.
    evento?.preventDefault();

    await this.solicitudesSvc.filtrar({
      buscar: this.busqueda(),
      desde: this.filtroDesde(),
      hasta: this.filtroHasta(),
    });
  }

  protected async limpiarFiltros(): Promise<void> {
    this.busqueda.set('');
    this.filtroDesde.set('');
    this.filtroHasta.set('');
    await this.solicitudesSvc.filtrar(FILTRO_VACIO);
  }

  protected async cambiarPagina(delta: number): Promise<void> {
    await this.solicitudesSvc.irAPagina(this.pagina() + delta);
  }

  protected escribir(signal: { set(v: string): void }, evento: Event): void {
    signal.set((evento.target as HTMLInputElement).value);
  }

  /* ===== Descarga de la planilla ===== */

  // Por defecto, el mes corrido hasta hoy: es lo que el cliente pide más
  // seguido, y así no tiene que escribir fechas para el caso normal.
  protected readonly desde = signal(this.haceDias(30));
  protected readonly hasta = signal(this.haceDias(0));
  protected readonly descargando = signal(false);
  protected readonly errorDescarga = signal<string | null>(null);

  private haceDias(dias: number): string {
    const fecha = new Date();
    fecha.setDate(fecha.getDate() - dias);
    return fecha.toISOString().slice(0, 10);
  }

  protected cambiarDesde(valor: string): void {
    this.desde.set(valor);
  }

  protected cambiarHasta(valor: string): void {
    this.hasta.set(valor);
  }

  protected async descargar(): Promise<void> {
    if (this.descargando()) {
      return;
    }

    this.descargando.set(true);
    this.errorDescarga.set(null);
    try {
      await this.solicitudesSvc.descargarExcel(this.desde(), this.hasta());
    } catch (respuesta: unknown) {
      // El 404 del backend significa "no hay nada terminado en ese rango", que
      // no es un error del cliente: se le dice tal cual.
      const estado = (respuesta as { status?: number })?.status;
      this.errorDescarga.set(
        estado === 404
          ? 'No hay expedientes terminados en esas fechas.'
          : 'No pudimos generar la planilla. Inténtalo de nuevo.',
      );
    } finally {
      this.descargando.set(false);
    }
  }

  /* ===== Documentos de una solicitud ===== */

  // Se cargan al abrir el desplegable, no con el listado: la mayoría de las
  // filas nunca se abre, y traer todos los documentos de la página engordaría
  // cada consulta para nada.
  private readonly documentosPorCodigo = signal<Record<string, readonly Documento[]>>({});
  private readonly cargandoCodigo = signal<string | null>(null);

  protected documentosDe(codigo: string): readonly Documento[] | null {
    return this.documentosPorCodigo()[codigo] ?? null;
  }

  protected estaCargando(codigo: string): boolean {
    return this.cargandoCodigo() === codigo;
  }

  protected async alternarDetalle(solicitud: Solicitud, abierto: boolean): Promise<void> {
    if (!abierto || this.documentosDe(solicitud.codigo) || this.estaCargando(solicitud.codigo)) {
      return;
    }

    this.cargandoCodigo.set(solicitud.codigo);
    try {
      const detalle = await this.solicitudesSvc.detalle(solicitud.codigo);
      this.documentosPorCodigo.update((actual) => ({
        ...actual,
        [solicitud.codigo]: detalle.documentosDetalle,
      }));
    } catch {
      // Sin documentos que mostrar, el desplegable lo dice y se puede
      // reintentar cerrando y abriendo.
    } finally {
      this.cargandoCodigo.set(null);
    }
  }

  /** Lo cuenta el servidor sobre todo el rango, no sobre la página cargada. */
  protected contarPorFiltro(valor: Filtro): number {
    return this.conteos()[valor] ?? 0;
  }

  protected nombreServicio(solicitud: Solicitud): string {
    return servicioPorId(solicitud.servicio).nombre;
  }

  protected iconoServicio(solicitud: Solicitud): IconName {
    return servicioPorId(solicitud.servicio).icono;
  }

  protected unidadServicio(solicitud: Solicitud): string {
    return servicioPorId(solicitud.servicio).unidad;
  }

  protected etiqueta(estado: EstadoSolicitud): string {
    return ETIQUETA_ESTADO[estado];
  }

  protected badge(estado: EstadoSolicitud): string {
    return BADGE_ESTADO[estado];
  }

  /** Los indicadores son texto plano, así que el formato se arma aquí. */
  private formatearPesos(monto: number): string {
    return monto.toLocaleString('es-CL', {
      style: 'currency',
      currency: 'CLP',
      maximumFractionDigits: 0,
    });
  }
}

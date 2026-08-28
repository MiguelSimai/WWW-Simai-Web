import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { EstadoSolicitud, Solicitud, SolicitudDetalle } from './modelos';

/** Cada cuánto se vuelve a preguntar mientras algo está en proceso. */
const ESPERA_MS = 10_000;

interface RespuestaLista {
  readonly solicitudes: readonly Solicitud[];
  readonly total: number;
  readonly pagina: number;
  readonly hay_mas: boolean;
}

/**
 * Solicitudes del usuario.
 *
 * El resultado no llega cuando el cliente pide la página: el motor procesa
 * aparte y avisa por callback. Así que mientras haya algo en proceso, este
 * servicio vuelve a preguntar cada diez segundos y se detiene cuando no queda
 * nada — sin WebSockets ni SSE, que para este volumen sobran.
 */
@Injectable({ providedIn: 'root' })
export class SolicitudesService {
  private readonly http = inject(HttpClient);

  private readonly _solicitudes = signal<readonly Solicitud[]>([]);
  private readonly _cargando = signal(false);
  private readonly _error = signal<string | null>(null);

  readonly solicitudes = this._solicitudes.asReadonly();
  readonly cargando = this._cargando.asReadonly();
  readonly error = this._error.asReadonly();

  readonly total = computed(() => this._solicitudes().length);

  readonly enProceso = computed(
    () => this._solicitudes().filter((s) => s.estado === 'procesando').length,
  );

  readonly porRevisar = computed(
    () => this._solicitudes().filter((s) => s.estado === 'revisar').length,
  );

  /** Gasto acumulado del período visible, en CLP. */
  readonly gastoTotal = computed(() =>
    this._solicitudes().reduce((suma, s) => suma + s.costo, 0),
  );

  private temporizador: ReturnType<typeof setTimeout> | null = null;

  filtrarPorEstado(estado: EstadoSolicitud | 'todas'): readonly Solicitud[] {
    const todas = this._solicitudes();
    return estado === 'todas' ? todas : todas.filter((s) => s.estado === estado);
  }

  async cargar(): Promise<void> {
    this._cargando.set(true);
    try {
      const respuesta = await firstValueFrom(
        this.http.get<RespuestaLista>(`${environment.apiUrl}/api/solicitudes`),
      );
      this._solicitudes.set(respuesta.solicitudes);
      this._error.set(null);
    } catch {
      // Un fallo puntual no borra lo que ya se mostraba: es peor vaciar la
      // pantalla que dejar los datos de hace diez segundos.
      this._error.set('No pudimos actualizar tus solicitudes.');
    } finally {
      this._cargando.set(false);
    }
  }

  detalle(codigo: string): Promise<SolicitudDetalle> {
    return firstValueFrom(
      this.http.get<SolicitudDetalle>(`${environment.apiUrl}/api/solicitudes/${codigo}`),
    );
  }

  /**
   * Baja la planilla de un rango de fechas.
   *
   * Llega como binario y se guarda con el nombre que puso el servidor: el
   * navegador no puede renombrar lo que no ve, así que se lee del
   * Content-Disposition.
   */
  async descargarExcel(desde: string, hasta: string): Promise<void> {
    const url = `${environment.apiUrl}/api/solicitudes/excel?desde=${desde}&hasta=${hasta}`;
    const respuesta = await firstValueFrom(
      this.http.get(url, { observe: 'response', responseType: 'blob' }),
    );

    const cuerpo = respuesta.body;
    if (!cuerpo) {
      throw new Error('La descarga llegó vacía.');
    }

    const disposicion = respuesta.headers.get('Content-Disposition') ?? '';
    const nombre = /filename="?([^";]+)"?/.exec(disposicion)?.[1] ?? 'solicitudes.xlsx';

    const enlace = document.createElement('a');
    enlace.href = URL.createObjectURL(cuerpo);
    enlace.download = nombre;
    enlace.click();
    URL.revokeObjectURL(enlace.href);
  }

  /**
   * Carga y queda pendiente mientras haya algo en proceso.
   *
   * Lo llama el panel al entrar. Idempotente: llamarlo dos veces no deja dos
   * temporizadores corriendo.
   */
  async vigilar(): Promise<void> {
    this.detener();
    await this.cargar();
    this.programarSiguiente();
  }

  detener(): void {
    if (this.temporizador !== null) {
      clearTimeout(this.temporizador);
      this.temporizador = null;
    }
  }

  private programarSiguiente(): void {
    if (!this.enProceso()) {
      return;
    }

    this.temporizador = setTimeout(async () => {
      await this.cargar();
      this.programarSiguiente();
    }, ESPERA_MS);
  }
}

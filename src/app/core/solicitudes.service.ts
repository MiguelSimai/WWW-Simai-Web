import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { EstadoSolicitud, Solicitud, SolicitudDetalle } from './modelos';

/** Cada cuánto se vuelve a preguntar mientras algo está en proceso. */
const ESPERA_MS = 10_000;

interface RespuestaLista {
  readonly solicitudes: readonly Solicitud[];
  readonly total: number;
  readonly conteos: Conteos;
  readonly pagina: number;
  readonly por_pagina: number;
  readonly hay_mas: boolean;
}

/** Cuántas solicitudes hay de cada estado dentro del filtro actual. */
export type Conteos = Readonly<Record<EstadoSolicitud | 'todas', number>>;

/** Lo que el usuario eligió en la pantalla. Todo viaja al servidor. */
export interface FiltroSolicitudes {
  readonly estado: EstadoSolicitud | 'todas';
  readonly desde: string;
  readonly hasta: string;
  readonly buscar: string;
}

const SIN_CONTEOS: Conteos = {
  todas: 0,
  procesando: 0,
  revisar: 0,
  completada: 0,
  error: 0,
};

export const FILTRO_VACIO: FiltroSolicitudes = {
  estado: 'todas',
  desde: '',
  hasta: '',
  buscar: '',
};

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
  private readonly _conteos = signal<Conteos>(SIN_CONTEOS);
  private readonly _pagina = signal(1);
  private readonly _hayMas = signal(false);
  private readonly _filtro = signal<FiltroSolicitudes>(FILTRO_VACIO);

  readonly solicitudes = this._solicitudes.asReadonly();
  readonly cargando = this._cargando.asReadonly();
  readonly error = this._error.asReadonly();

  /** Cuántas hay de cada estado, contadas por el servidor sobre TODO el rango. */
  readonly conteos = this._conteos.asReadonly();
  readonly pagina = this._pagina.asReadonly();
  readonly hayMas = this._hayMas.asReadonly();
  readonly filtro = this._filtro.asReadonly();

  readonly total = computed(() => this._conteos().todas);
  readonly enProceso = computed(() => this._conteos().procesando);
  readonly porRevisar = computed(() => this._conteos().revisar);

  /** Gasto de lo que se está viendo, no del total: es lo que hay cargado. */
  readonly gastoTotal = computed(() =>
    this._solicitudes().reduce((suma, s) => suma + s.costo, 0),
  );

  private temporizador: ReturnType<typeof setTimeout> | null = null;

  /**
   * Cambia el filtro y vuelve a la primera página.
   *
   * Quedarse en la página 4 tras filtrar mostraría una pantalla vacía sin
   * explicación.
   */
  async filtrar(cambios: Partial<FiltroSolicitudes>): Promise<void> {
    this._filtro.update((actual) => ({ ...actual, ...cambios }));
    this._pagina.set(1);
    await this.vigilar();
  }

  async irAPagina(pagina: number): Promise<void> {
    this._pagina.set(Math.max(1, pagina));
    await this.vigilar();
  }

  async cargar(): Promise<void> {
    this._cargando.set(true);
    try {
      const f = this._filtro();
      let params = new HttpParams().set('pagina', this._pagina());
      if (f.estado !== 'todas') params = params.set('estado', f.estado);
      if (f.desde) params = params.set('desde', f.desde);
      if (f.hasta) params = params.set('hasta', f.hasta);
      if (f.buscar.trim()) params = params.set('buscar', f.buscar.trim());

      const respuesta = await firstValueFrom(
        this.http.get<RespuestaLista>(`${environment.apiUrl}/api/solicitudes`, { params }),
      );
      this._solicitudes.set(respuesta.solicitudes);
      this._conteos.set(respuesta.conteos);
      this._hayMas.set(respuesta.hay_mas);
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

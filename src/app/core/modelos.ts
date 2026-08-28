import { IconName } from '../ui/icon/icon.component';

export type ServicioId = 'transcripcion' | 'documentos' | 'conversaciones' | 'automatizacion';

/** Servicio del catálogo, con su tarifa por uso. */
export interface Servicio {
  readonly id: ServicioId;
  readonly nombre: string;
  readonly icono: IconName;
  readonly resumen: string;
  readonly detalle: string;
  /** Unidad que se cobra, en singular: "minuto de audio", "página". */
  readonly unidad: string;
  /** Precio unitario en CLP, sin IVA. */
  readonly precio: number;
  readonly incluye: readonly string[];
  /** Extensiones que acepta el input de archivos, con punto. */
  readonly acepta: readonly string[];
  /** Tope por archivo, en MB. */
  readonly maxMb: number;
  /**
   * Si se puede enviar desde el portal. Un servicio cuyo formato el motor
   * todavía no procesa se ofrece igual en la landing y en precios, pero no
   * acepta cargas: es preferible decirlo antes que fallar al subir.
   */
  readonly disponible: boolean;
  /** Qué mostrar cuando no está disponible. Vacío si lo está. */
  readonly motivoNoDisponible: string;
}

export type EstadoSolicitud = 'completada' | 'procesando' | 'revisar' | 'error';

/**
 * Un expediente enviado a uno de los servicios: lo que en el escritorio del
 * cliente es una carpeta con documentos dentro. Un archivo suelto es un
 * expediente de uno.
 */
export interface Solicitud {
  readonly codigo: string;
  readonly servicio: ServicioId;
  /** Número de solicitud del cliente, del nombre de la carpeta. */
  readonly numeroCliente: string | null;
  /** Cómo se nombra en el panel: el número del expediente, o el archivo. */
  readonly etiqueta: string;
  /** Cuántos documentos lleva. */
  readonly documentos: number;
  readonly unidades: number;
  /** Costo total en CLP, ya calculado por el backend. */
  readonly costo: number;
  /** Fecha de ingreso en ISO 8601. */
  readonly fecha: string;
  readonly estado: EstadoSolicitud;
  readonly resultado: string;
}

/** Un documento dentro de un expediente, con su resultado propio. */
export interface Documento {
  readonly codigo: string;
  readonly archivo: string;
  readonly unidades: number;
  readonly costo: number;
  readonly estado: EstadoSolicitud;
  readonly resultado: string | null;
  /** Confianza del motor, 0 a 100. Null mientras no haya resultado. */
  readonly confianza: number | null;
  readonly error: string | null;
  readonly respuestaIa: unknown;
}

/** Una solicitud con el detalle de sus documentos. */
export interface SolicitudDetalle extends Solicitud {
  readonly documentosDetalle: readonly Documento[];
  readonly respuestaIa: unknown;
  readonly cerradaEn: string | null;
}

export interface Usuario {
  readonly id: string;
  readonly email: string;
  readonly nombre: string;
  /** Nombre de la cuenta a la que pertenece. */
  readonly empresa?: string;
  /**
   * Saldo disponible en CLP. Es de la cuenta, no de la persona: todos los
   * usuarios de una empresa comparten el mismo.
   */
  readonly saldo?: number;
  /** Si alguna vez cargó saldo. Decide si ve el panel o la contratación. */
  readonly contratado?: boolean;
  /**
   * Servicios que la cuenta tiene contratados. Sólo esos se ofrecen en
   * /enviar; el backend rechaza el resto de todas formas.
   */
  readonly servicios?: readonly ServicioId[];
  /**
   * Si puede entrar a la administración. Sólo sirve para mostrar el acceso: el
   * backend valida el correo en cada llamada y responde 404 al resto.
   */
  readonly esAdmin?: boolean;
}

/** Etiqueta legible para cada estado, usada en badges y tablas. */
export const ETIQUETA_ESTADO: Readonly<Record<EstadoSolicitud, string>> = {
  completada: 'Completada',
  procesando: 'Procesando',
  revisar: 'Requiere revisión',
  error: 'Con error',
};

/** Modificador BEM de `.badge` que corresponde a cada estado. */
export const BADGE_ESTADO: Readonly<Record<EstadoSolicitud, string>> = {
  completada: 'badge--ok',
  procesando: 'badge--proceso',
  revisar: 'badge--warn',
  error: 'badge--error',
};

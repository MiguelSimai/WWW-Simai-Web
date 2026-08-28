import { Servicio, ServicioId } from './modelos';

/**
 * Catálogo de servicios y tarifas. Es la única fuente de precios del sitio:
 * la landing, la página de precios y el panel leen de aquí.
 *
 * Precios en CLP por unidad, sin IVA. Son valores de referencia: ajústalos
 * antes de publicar.
 *
 * OJO: `backend/app/catalogo.py` tiene que decir lo mismo. Esta copia es para
 * mostrar; el cobro se calcula en el servidor, porque lo que manda el
 * navegador no es confiable. Que las dos se separen significa cobrarle al
 * cliente un precio distinto del que vio, así que al tocar precios,
 * extensiones o topes hay que cambiar ambas.
 *
 * `acepta` y `maxMb` describen lo que el motor procesa hoy de punta a punta:
 * audio, PDF e imágenes. Video, Office y ZIP quedan fuera hasta que el motor
 * los cubra — aceptar un archivo no es procesarlo.
 */

/** Tope por archivo mientras viaje en base64 hacia el motor. */
const MAX_MB = 25;

export const CATALOGO: readonly Servicio[] = [
  {
    id: 'transcripcion',
    nombre: 'Transcripción de audio y video',
    icono: 'transcripcion',
    resumen: 'Reuniones, entrevistas y llamadas convertidas en texto con marcas de tiempo.',
    detalle:
      'Sube el archivo y recibe la transcripción con hablantes separados y marcas de tiempo. Reconoce español de Chile, incluidas grabaciones con ruido de fondo o varios participantes.',
    unidad: 'minuto de audio',
    precio: 12,
    incluye: [
      'Separación de hablantes',
      'Marcas de tiempo por párrafo',
      'Exporta a TXT, DOCX y SRT',
    ],
    // Sin video todavía: hay que extraerle el audio antes de transcribirlo.
    acepta: ['.mp3', '.wav', '.ogg', '.flac', '.aac'],
    maxMb: MAX_MB,
    disponible: true,
    motivoNoDisponible: '',
  },
  {
    id: 'documentos',
    nombre: 'Análisis de documentos',
    icono: 'documento',
    resumen: 'Extrae los datos clave de contratos, facturas e informes, y los compara entre sí.',
    detalle:
      'Lee documentos —incluidos los escaneados—, extrae los campos que definas y los cruza para detectar diferencias y faltantes. Cada dato queda citado con documento y página.',
    unidad: 'página',
    precio: 35,
    incluye: [
      'OCR para documentos escaneados',
      'Campos a medida según tu formato',
      'Cada dato citado con su página',
    ],
    acepta: ['.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.bmp'],
    maxMb: MAX_MB,
    disponible: true,
    motivoNoDisponible: '',
  },
  {
    id: 'conversaciones',
    nombre: 'Análisis de conversaciones',
    icono: 'audio',
    resumen: 'Qué se dijo, en qué tono y si se cumplió el guion, sobre el total de tus llamadas.',
    detalle:
      'Sobre el audio ya transcrito, identifica temas, detecta compromisos, mide el tono de la conversación y verifica el cumplimiento de un guion o checklist definido por ti.',
    unidad: 'minuto analizado',
    precio: 25,
    incluye: [
      'Temas y compromisos detectados',
      'Cumplimiento de guion',
      'Resumen ejecutivo por llamada',
    ],
    acepta: ['.mp3', '.wav', '.ogg', '.flac', '.aac'],
    maxMb: MAX_MB,
    disponible: true,
    motivoNoDisponible: '',
  },
  {
    id: 'automatizacion',
    nombre: 'Automatización de procesos',
    icono: 'automatizacion',
    resumen: 'Encadena pasos con IA y conéctalos a los sistemas que ya usas.',
    detalle:
      'Define un flujo —recibir, clasificar, extraer, validar, notificar— y déjalo corriendo. Se conecta por API o correo con tus sistemas actuales, sin migrar nada.',
    unidad: 'ejecución',
    precio: 18,
    incluye: [
      'Flujos con pasos condicionales',
      'Conectores por API y correo',
      'Reintento automático ante fallas',
    ],
    acepta: [],
    maxMb: MAX_MB,
    disponible: false,
    motivoNoDisponible:
      'Disponible por API. La carga de archivos desde el portal llega pronto.',
  },
];

/** Acceso puntual por id, para pintar el servicio de una solicitud. */
export function servicioPorId(id: ServicioId): Servicio {
  const servicio = CATALOGO.find((s) => s.id === id);
  if (!servicio) {
    throw new Error(`Servicio desconocido: ${id}`);
  }
  return servicio;
}

/** Los que aceptan carga desde el portal, que es lo que ofrece /enviar. */
export const SERVICIOS_DISPONIBLES: readonly Servicio[] = CATALOGO.filter((s) => s.disponible);

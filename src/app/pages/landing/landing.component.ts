import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { IconComponent, IconName } from '../../ui/icon/icon.component';

interface Paso {
  readonly numero: string;
  readonly titulo: string;
  readonly detalle: string;
}

/** Una lista con encabezado, dentro de un servicio o de la propuesta. */
interface Bloque {
  readonly titulo: string;
  readonly items: readonly string[];
}

/**
 * Un servicio tal como se presenta en la web.
 *
 * No son los del catálogo (`core/catalogo.ts`): estos son la forma comercial
 * de contar lo mismo. El catálogo define lo que se cobra —minuto de audio,
 * página, ejecución— y alimenta el portal; esto es cómo se le explica a quien
 * llega al sitio. Si cambia uno, revisar que el otro siga siendo coherente.
 */
interface ServicioWeb {
  readonly id: string;
  readonly icono: IconName;
  readonly titulo: string;
  readonly resumen: string;
  readonly bloques: readonly Bloque[];
}

interface Garantia {
  readonly titulo: string;
  readonly detalle: string;
}

/** Línea de la respuesta de ejemplo que se muestra en el hero. */
interface LineaRespuesta {
  readonly campo: string;
  readonly valor: string;
}

interface DatoContacto {
  readonly icono: IconName;
  readonly label: string;
  readonly valor: string;
  readonly nota: string;
  /** Enlace directo (mailto:), cuando el dato es accionable. */
  readonly href?: string;
}

@Component({
  selector: 'app-landing',
  imports: [ReactiveFormsModule, RouterLink, IconComponent],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
})
export class LandingComponent {
  private readonly fb = inject(FormBuilder);

  /* ===== Hero ===== */

  protected readonly heroParrafos: readonly string[] = [
    'Transformamos documentos, imágenes, audios y datos empresariales en información estratégica que acelera el crecimiento, optimiza operaciones y multiplica las capacidades de las organizaciones.',
    'Ayudamos a las empresas a incorporar Inteligencia Artificial de forma práctica y segura, potenciando el talento humano y habilitando nuevos niveles de productividad, eficiencia e innovación.',
  ];

  protected readonly heroCierre =
    'Convertimos información en decisiones. Decisiones en resultados. Resultados en crecimiento exponencial.';

  /* ===== Quiénes somos ===== */

  protected readonly nosotros: readonly string[] = [
    'Somos una empresa especializada en soluciones de Inteligencia Artificial diseñadas para aumentar exponencialmente las capacidades de las organizaciones.',
    'Nuestro propósito es ayudar a las empresas a aprovechar el valor oculto en sus documentos, imágenes, audios y datos estructurados, transformándolos en conocimiento accionable para mejorar la toma de decisiones, automatizar procesos y generar nuevas oportunidades de crecimiento.',
    'Creemos que la Inteligencia Artificial alcanza su máximo potencial cuando trabaja junto a las personas. Por ello desarrollamos soluciones que potencian el talento humano, permitiendo que los equipos concentren su energía en actividades estratégicas de alto valor.',
  ];

  /* ===== Visión ===== */

  protected readonly vision: readonly string[] = [
    'Visualizamos un futuro donde las organizaciones puedan crecer más rápido y mejor mediante la combinación de inteligencia humana e inteligencia artificial.',
    'Nuestro objetivo es transformar empresas tradicionales en organizaciones aumentadas, capaces de procesar grandes volúmenes de información, tomar decisiones más rápidas y generar ventajas competitivas sostenibles.',
  ];

  protected readonly visionCierre: readonly string[] = [
    'No buscamos mejoras incrementales.',
    'Buscamos habilitar crecimientos exponenciales.',
  ];

  /* ===== Propuesta de valor ===== */

  /**
   * Los tipos de información van agrupados y no en una lista de doce: así se
   * lee de un vistazo qué familia de contenido cubre cada uno.
   */
  protected readonly tiposInformacion: readonly Bloque[] = [
    {
      titulo: 'Documentos y comunicaciones',
      items: [
        'Documentos físicos y digitales',
        'Contratos y formularios',
        'Correos electrónicos',
        'Facturas y órdenes de compra',
      ],
    },
    {
      titulo: 'Imágenes y audio',
      items: [
        'Imágenes y fotografías',
        'Grabaciones de audio',
        'Conversaciones comerciales y de servicio',
      ],
    },
    {
      titulo: 'Datos empresariales',
      items: [
        'Bases de datos empresariales',
        'Información operacional',
        'Datos de clientes',
        'Registros transaccionales',
        'Información de ERP, CRM y otros sistemas corporativos',
      ],
    },
  ];

  /* ===== Servicios ===== */

  protected readonly servicios: readonly ServicioWeb[] = [
    {
      id: 'procesos',
      icono: 'automatizacion',
      titulo: 'Digitalización inteligente de procesos operacionales',
      resumen:
        'Modernizamos procesos corporativos mediante Inteligencia Artificial aplicada a contenidos y datos empresariales.',
      bloques: [
        {
          titulo: 'Capacidades',
          items: [
            'Extracción inteligente de información documental',
            'Procesamiento masivo de contenidos',
            'Clasificación automática de documentos',
            'Automatización de flujos operacionales',
            'Integración con procesos existentes',
            'Generación automática de indicadores',
            'Análisis de información estructurada y no estructurada',
          ],
        },
        {
          titulo: 'Beneficios',
          items: [
            'Mayor productividad operacional',
            'Escalabilidad de procesos',
            'Menores costos operativos',
            'Reducción de errores',
            'Organizaciones preparadas para crecer exponencialmente',
          ],
        },
      ],
    },
    {
      id: 'ventas',
      icono: 'grafico',
      titulo: 'Inteligencia Artificial para ventas y desarrollo comercial',
      resumen:
        'Transformamos datos e interacciones comerciales en oportunidades de crecimiento.',
      bloques: [
        {
          titulo: 'Capacidades',
          items: [
            'Análisis de conversaciones de ventas',
            'Procesamiento de llamadas y reuniones',
            'Análisis de comportamiento de clientes',
            'Identificación de oportunidades comerciales',
            'Calificación inteligente de prospectos',
            'Automatización de procesos de captación',
            'Modelos predictivos basados en datos comerciales',
          ],
        },
        {
          titulo: 'Beneficios',
          items: [
            'Incremento en la generación de oportunidades',
            'Mejora de las tasas de conversión',
            'Mayor productividad comercial',
            'Ciclos de venta más eficientes',
            'Crecimiento acelerado y escalable',
          ],
        },
      ],
    },
    {
      id: 'contenidos',
      icono: 'extraer',
      titulo: 'Análisis inteligente de contenidos',
      resumen: 'Extraemos información valiosa desde cualquier formato de contenido empresarial.',
      bloques: [
        {
          titulo: 'Documentos',
          items: ['Contratos', 'Informes', 'Facturas', 'Formularios', 'Expedientes'],
        },
        {
          titulo: 'Imágenes',
          items: ['Fotografías', 'Evidencias visuales', 'Documentación escaneada'],
        },
        {
          titulo: 'Audios',
          items: ['Llamadas', 'Reuniones', 'Entrevistas', 'Conversaciones de servicio'],
        },
        {
          titulo: 'Resultados',
          items: [
            'Extracción de información',
            'Clasificación automática',
            'Generación de resúmenes',
            'Detección de riesgos',
            'Identificación de oportunidades',
            'Generación de conocimiento empresarial',
          ],
        },
      ],
    },
    {
      id: 'datos',
      icono: 'api',
      titulo: 'Inteligencia sobre datos empresariales',
      resumen: 'Convertimos datos estructurados en ventajas competitivas.',
      bloques: [
        {
          titulo: 'Analizamos información de',
          items: [
            'ERP',
            'CRM',
            'Plataformas financieras',
            'Sistemas de recursos humanos',
            'Sistemas logísticos',
            'Plataformas de atención al cliente',
            'Bases de datos corporativas',
          ],
        },
        {
          titulo: 'Capacidades',
          items: [
            'Identificación de patrones y tendencias',
            'Análisis predictivo',
            'Generación de indicadores estratégicos',
            'Detección temprana de riesgos',
            'Descubrimiento de oportunidades de crecimiento',
            'Apoyo avanzado para la toma de decisiones',
          ],
        },
        {
          titulo: 'Beneficios',
          items: [
            'Decisiones basadas en evidencia',
            'Mayor capacidad predictiva',
            'Optimización continua',
            'Crecimiento impulsado por datos',
          ],
        },
      ],
    },
  ];

  /* ===== Cómo trabajamos ===== */

  protected readonly pasos: readonly Paso[] = [
    {
      numero: '01',
      titulo: 'Ingesta',
      detalle:
        'Recepción de documentos, imágenes, audios y datos estructurados provenientes de cualquier fuente corporativa.',
    },
    {
      numero: '02',
      titulo: 'Análisis inteligente',
      detalle:
        'Aplicación de modelos avanzados de Inteligencia Artificial adaptados al contexto específico de cada organización.',
    },
    {
      numero: '03',
      titulo: 'Generación de conocimiento',
      detalle: 'Extracción de información, patrones, indicadores, alertas y recomendaciones.',
    },
    {
      numero: '04',
      titulo: 'Entrega de resultados',
      detalle:
        'La información se devuelve en el formato que cada cliente requiere, para integrarse con ERP, CRM, plataformas analíticas, sistemas internos y procesos de negocio.',
    },
  ];

  /* ===== Compromiso ===== */

  protected readonly compromiso: readonly string[] = [
    'La verdadera transformación no ocurre cuando una empresa incorpora tecnología. Ocurre cuando la tecnología amplifica el potencial de las personas.',
    'Por eso diseñamos soluciones que permiten que los equipos trabajen con mayor información, mejor contexto y mayor velocidad de ejecución.',
  ];

  protected readonly mision =
    'Ayudar a las empresas a alcanzar niveles exponenciales de crecimiento mediante Inteligencia Artificial que potencia a las personas, optimiza los procesos y transforma la información en una ventaja competitiva sostenible.';

  /* ===== Seguridad ===== */

  protected readonly garantias: readonly Garantia[] = [
    {
      titulo: 'Cifrado en tránsito y en reposo',
      detalle: 'Tus archivos viajan y se almacenan cifrados, en infraestructura alojada en Chile.',
    },
    {
      titulo: 'Tus datos no entrenan modelos',
      detalle: 'Ni los tuyos ni los de nadie. Se procesan, se entregan y se eliminan.',
    },
    {
      titulo: 'Retención que tú defines',
      detalle:
        'Elige cuánto se conserva cada resultado. Cumplido el plazo, se borra de forma verificable.',
    },
    {
      titulo: 'Trazabilidad completa',
      detalle: 'Queda registro de cada solicitud: quién la envió, cuándo y qué se hizo con ella.',
    },
    {
      titulo: 'La decisión sigue siendo tuya',
      detalle: 'La IA propone y respalda con evidencia. Aprobar, corregir o descartar lo haces tú.',
    },
    {
      titulo: 'Aislamiento por cuenta',
      detalle: 'Cada cliente procesa en su propio espacio. Nada se cruza entre organizaciones.',
    },
  ];

  /* ===== Maqueta del hero: de la puesta en marcha al consumo ===== */

  protected readonly puestaEnMarcha: readonly string[] = [
    'Levantamiento del proceso, contigo',
    'Modelos configurados y validados con tus casos reales',
    'Endpoint habilitado en tu ambiente',
  ];

  protected readonly demoEndpoint = 'POST /v1/documentos/analizar';
  protected readonly demoEstado = '200 OK · 1,8 s';

  protected readonly demoRespuesta: readonly LineaRespuesta[] = [
    { campo: 'campos_extraidos', valor: '14' },
    { campo: 'confianza', valor: '0.97' },
    { campo: 'paginas', valor: '3' },
  ];

  /* ===== Contacto ===== */

  protected readonly datosContacto: readonly DatoContacto[] = [
    {
      icono: 'correo',
      label: 'Escríbenos',
      valor: 'contacto@simai.cl',
      nota: 'Respondemos dentro de un día hábil.',
      href: 'mailto:contacto@simai.cl',
    },
    {
      icono: 'lugar',
      label: 'Dónde estamos',
      valor: 'Santiago, Chile',
      nota: 'Trabajamos con clientes de todo el país, de forma remota.',
    },
    {
      icono: 'reloj',
      label: 'Horario',
      valor: 'Lunes a viernes, 9:00 a 18:00',
      nota: 'Si escribes fuera de horario, te respondemos al día siguiente.',
    },
  ];

  protected readonly contacto = this.fb.nonNullable.group({
    nombre: ['', [Validators.required, Validators.minLength(3)]],
    email: ['', [Validators.required, Validators.email]],
    empresa: [''],
    mensaje: ['', [Validators.required, Validators.minLength(10)]],
  });

  protected readonly contactoEnviado = signal(false);
  protected readonly contactoListo = signal(false);

  protected get c() {
    return this.contacto.controls;
  }

  /**
   * SIMULADO: no hay backend que reciba el mensaje. Se valida y se muestra la
   * confirmación para dejar el flujo completo; al conectar el backend, envía
   * `this.contacto.getRawValue()` y recién entonces marca `contactoListo`.
   */
  protected enviarContacto(): void {
    this.contactoEnviado.set(true);
    if (this.contacto.invalid) {
      return;
    }

    this.contactoListo.set(true);
  }

  protected escribirOtro(): void {
    this.contacto.reset();
    this.contactoEnviado.set(false);
    this.contactoListo.set(false);
  }
}

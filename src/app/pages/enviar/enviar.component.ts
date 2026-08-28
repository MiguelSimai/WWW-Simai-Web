import { Component, computed, inject, signal } from '@angular/core';
import { HttpEventType } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { AUTH } from '../../core/auth';
import { SERVICIOS_DISPONIBLES, servicioPorId } from '../../core/catalogo';
import { ServicioId } from '../../core/modelos';
import { SolicitudesApi } from '../../core/solicitudes-api.service';
import { IconComponent } from '../../ui/icon/icon.component';

type EstadoExpediente = 'pendiente' | 'subiendo' | 'listo' | 'error';

/** Un archivo dentro de un expediente. */
interface DocumentoEnCola {
  readonly id: number;
  readonly file: File;
  /** Duración en minutos, sólo para audio y video. */
  readonly minutos: number | null;
  /** Por qué no se puede enviar. Si está, el documento no viaja. */
  readonly error?: string;
}

/**
 * Un expediente listo para enviar: lo que en el escritorio del cliente es una
 * carpeta. `numero` es el nombre de esa carpeta, que el backend usa como
 * número de solicitud. En null cuando son archivos sueltos.
 */
interface ExpedienteEnCola {
  readonly id: number;
  readonly numero: string | null;
  readonly documentos: readonly DocumentoEnCola[];
  readonly estado: EstadoExpediente;
  /** 0–100 mientras sube. */
  readonly progreso: number;
  readonly codigo?: string;
  readonly error?: string;
}

@Component({
  selector: 'app-enviar',
  imports: [IconComponent, RouterLink],
  templateUrl: './enviar.component.html',
  styleUrl: './enviar.component.scss',
})
export class EnviarComponent {
  private readonly api = inject(SolicitudesApi);
  private readonly router = inject(Router);
  private readonly auth = inject(AUTH);

  private siguienteId = 1;

  /**
   * Lo que se puede enviar: el cruce de dos filtros.
   *
   * 1. Que el motor procese sus formatos (`disponible` en el catálogo).
   * 2. Que la cuenta lo tenga contratado (`servicios` de la sesión).
   *
   * El backend rechaza igual lo que no corresponda; esto es para no ofrecerle
   * al cliente algo que no puede usar. Si la sesión no trae la lista —una
   * cuenta sin procesos configurados—, no se ofrece ninguno.
   */
  protected readonly servicios = computed(() => {
    const contratados = this.auth.usuario()?.servicios;
    if (!contratados) {
      return [];
    }
    return SERVICIOS_DISPONIBLES.filter((s) => contratados.includes(s.id));
  });

  protected readonly servicioSel = signal<ServicioId | null>(null);

  /**
   * El servicio con el que se está trabajando.
   *
   * Nunca es null para no llenar la plantilla de comprobaciones: si la cuenta
   * no tiene ninguno contratado se cae al primero del catálogo, pero en ese
   * caso la pantalla muestra el aviso y nada de esto se renderiza.
   */
  protected readonly servicio = computed(() => {
    // El primero contratado es el que se muestra al entrar, sin obligar a
    // elegir cuando hay uno solo.
    const elegido = this.servicioSel() ?? this.servicios()[0]?.id;
    return servicioPorId(elegido ?? SERVICIOS_DISPONIBLES[0].id);
  });

  protected readonly cola = signal<readonly ExpedienteEnCola[]>([]);
  protected readonly arrastrando = signal(false);
  protected readonly enviando = signal(false);

  protected readonly pendientes = computed(() =>
    this.cola().filter((e) => e.estado === 'pendiente'),
  );
  protected readonly enviados = computed(() => this.cola().filter((e) => e.estado === 'listo'));

  /** Documentos que sí van a viajar, de los expedientes pendientes. */
  protected readonly documentosPorEnviar = computed(() =>
    this.pendientes().reduce((n, e) => n + e.documentos.filter((d) => !d.error).length, 0),
  );

  /**
   * Sólo el audio y el video permiten estimar antes de procesar: el navegador
   * puede leer su duración. En documentos, el número de páginas no se conoce
   * hasta abrirlos, así que no inventamos una cifra.
   */
  protected readonly estimable = computed(() => {
    const docs = this.pendientes().flatMap((e) => e.documentos.filter((d) => !d.error));
    return docs.length > 0 && docs.every((d) => d.minutos !== null);
  });

  protected readonly minutosTotales = computed(() =>
    this.pendientes()
      .flatMap((e) => e.documentos)
      .reduce((suma, d) => suma + (d.minutos ?? 0), 0),
  );

  protected readonly costoEstimado = computed(
    () => this.minutosTotales() * this.servicio().precio,
  );

  /* ===== Selección de servicio ===== */

  protected esElegido(id: ServicioId): boolean {
    return this.servicio()?.id === id;
  }

  protected elegirServicio(id: ServicioId): void {
    if (this.enviando()) {
      return;
    }
    this.servicioSel.set(id);
    // Lo aceptado cambia con el servicio: la cola anterior puede no servir.
    this.cola.set([]);
  }

  /* ===== Entrada de archivos ===== */

  protected onArrastrar(evento: DragEvent, dentro: boolean): void {
    evento.preventDefault();
    this.arrastrando.set(dentro);
  }

  protected async onSoltar(evento: DragEvent): Promise<void> {
    evento.preventDefault();
    this.arrastrando.set(false);

    const items = evento.dataTransfer?.items;
    if (items?.length) {
      // Arrastrar una carpeta sólo entrega su contenido por esta vía: en
      // `files` llegaría como una entrada vacía sin sus archivos dentro.
      const archivos = await this.leerArrastre(items);
      if (archivos.length) {
        this.agregar(archivos);
        return;
      }
    }

    this.agregar(Array.from(evento.dataTransfer?.files ?? []));
  }

  protected onSeleccionar(evento: Event): void {
    const input = evento.target as HTMLInputElement;
    this.agregar(Array.from(input.files ?? []));
    // Permite volver a elegir lo mismo si se quitó de la cola.
    input.value = '';
  }

  /**
   * Saca los archivos de lo arrastrado, entrando en las carpetas.
   *
   * Se le pone a cada archivo su ruta relativa en `webkitRelativePath` para
   * que el resto del flujo no distinga entre arrastrar una carpeta y elegirla
   * con el botón: en los dos casos la ruta dice a qué expediente pertenece.
   */
  private async leerArrastre(items: DataTransferItemList): Promise<File[]> {
    const raices = Array.from(items)
      .map((item) => item.webkitGetAsEntry?.())
      .filter((entrada): entrada is FileSystemEntry => !!entrada);

    if (!raices.length) {
      return [];
    }

    const archivos: File[] = [];
    await Promise.all(raices.map((entrada) => this.recorrer(entrada, '', archivos)));
    return archivos;
  }

  private async recorrer(
    entrada: FileSystemEntry,
    prefijo: string,
    salida: File[],
  ): Promise<void> {
    const ruta = prefijo ? `${prefijo}/${entrada.name}` : entrada.name;

    if (entrada.isFile) {
      const file = await new Promise<File | null>((resolver) =>
        (entrada as FileSystemFileEntry).file(resolver, () => resolver(null)),
      );
      if (file) {
        // `webkitRelativePath` es de sólo lectura, así que se redefine para
        // que coincida con lo que entrega el input de carpetas.
        Object.defineProperty(file, 'webkitRelativePath', { value: ruta });
        salida.push(file);
      }
      return;
    }

    if (entrada.isDirectory) {
      const lector = (entrada as FileSystemDirectoryEntry).createReader();
      // readEntries entrega por lotes: hay que llamarlo hasta que devuelva
      // vacío o se pierden archivos en carpetas grandes.
      for (;;) {
        const lote = await new Promise<FileSystemEntry[]>((resolver) =>
          lector.readEntries(resolver, () => resolver([])),
        );
        if (!lote.length) {
          return;
        }
        await Promise.all(lote.map((hijo) => this.recorrer(hijo, ruta, salida)));
      }
    }
  }

  /**
   * Agrupa los archivos en expedientes y los suma a la cola.
   *
   * Un archivo con ruta ("297541/CONTRATO.pdf") se agrupa con los demás de su
   * carpeta. Uno sin ruta es un expediente propio, como antes.
   */
  private agregar(archivos: readonly File[]): void {
    // Sin servicios contratados no hay dónde enviarlos, y `servicio()` estaría
    // devolviendo el relleno del catálogo.
    if (!archivos.length || !this.servicios().length) {
      return;
    }

    const porCarpeta = new Map<string, File[]>();
    const sueltos: File[] = [];

    for (const file of archivos) {
      const carpeta = this.carpetaDe(file);
      if (carpeta) {
        const grupo = porCarpeta.get(carpeta) ?? [];
        grupo.push(file);
        porCarpeta.set(carpeta, grupo);
      } else {
        sueltos.push(file);
      }
    }

    const nuevos: ExpedienteEnCola[] = [];

    for (const [numero, files] of porCarpeta) {
      nuevos.push(this.armar(numero, files));
    }
    for (const file of sueltos) {
      nuevos.push(this.armar(null, [file]));
    }

    this.cola.update((actual) => [...actual, ...nuevos]);

    // La duración se resuelve después: los archivos aparecen de inmediato en
    // vez de dejar la pantalla quieta mientras se leen los encabezados.
    for (const expediente of nuevos) {
      for (const documento of expediente.documentos) {
        if (documento.error) {
          continue;
        }
        void this.duracionEnMinutos(documento.file).then((minutos) => {
          if (minutos !== null) {
            this.parcharDocumento(expediente.id, documento.id, { minutos });
          }
        });
      }
    }
  }

  /**
   * La carpeta que contiene directamente al archivo, que es la que da el
   * número de solicitud.
   *
   * Se toma la última del camino, no la primera, para que dé igual desde dónde
   * se eligió: seleccionar `297541` da la ruta "297541/CONTRATO.pdf", y
   * seleccionar la carpeta que la contiene da "Victor IA/297541/CONTRATO.pdf".
   * En los dos casos el expediente es 297541. Así se pueden subir todas las
   * carpetas de una vez eligiendo la que las agrupa.
   */
  private carpetaDe(file: File): string | null {
    const ruta = file.webkitRelativePath;
    if (!ruta || !ruta.includes('/')) {
      return null;
    }
    const partes = ruta.split('/').filter(Boolean);
    return partes.length > 1 ? partes[partes.length - 2] : null;
  }

  private armar(numero: string | null, files: readonly File[]): ExpedienteEnCola {
    const documentos = files.map((file) => ({
      id: this.siguienteId++,
      file,
      minutos: null,
      error: this.validar(file) ?? undefined,
    }));

    // Un expediente donde ningún documento sirve no tiene nada que enviar.
    const utiles = documentos.filter((d) => !d.error).length;

    // El resumen sólo aporta cuando hay varios: para un archivo suelto, el
    // error del propio archivo ya dice todo, y hablar de "esta carpeta" cuando
    // no hay carpeta confunde.
    const resumen =
      !utiles && documentos.length > 1
        ? 'Ningún archivo de esta carpeta sirve para el servicio.'
        : undefined;

    return {
      id: this.siguienteId++,
      numero,
      documentos,
      estado: utiles ? 'pendiente' : 'error',
      progreso: 0,
      error: resumen,
    };
  }

  private validar(file: File): string | null {
    const servicio = this.servicio();
    const extension = '.' + (file.name.split('.').pop() ?? '').toLowerCase();

    if (!servicio.acepta.includes(extension)) {
      return `${extension} no sirve para este servicio.`;
    }
    if (file.size > servicio.maxMb * 1024 * 1024) {
      return `Supera el máximo de ${servicio.maxMb} MB.`;
    }
    if (file.size === 0) {
      return 'El archivo está vacío.';
    }
    return null;
  }

  /** Lee la duración con un elemento multimedia; null si no es audio/video. */
  private duracionEnMinutos(file: File): Promise<number | null> {
    if (!/^(audio|video)\//.test(file.type)) {
      return Promise.resolve(null);
    }

    return new Promise((resolver) => {
      const medio = document.createElement('video');
      const url = URL.createObjectURL(file);

      const terminar = (valor: number | null) => {
        URL.revokeObjectURL(url);
        resolver(valor);
      };

      medio.preload = 'metadata';
      medio.onloadedmetadata = () =>
        terminar(Number.isFinite(medio.duration) ? Math.ceil(medio.duration / 60) : null);
      medio.onerror = () => terminar(null);
      medio.src = url;
    });
  }

  protected quitar(id: number): void {
    this.cola.update((actual) => actual.filter((e) => e.id !== id));
  }

  protected limpiar(): void {
    this.cola.set([]);
  }

  /* ===== Envío ===== */

  protected async enviar(): Promise<void> {
    if (this.enviando() || !this.pendientes().length) {
      return;
    }

    this.enviando.set(true);
    // De a uno: un expediente que falla no arrastra a los demás, y el
    // progreso por expediente es legible.
    for (const expediente of this.pendientes()) {
      await this.subir(expediente);
    }
    this.enviando.set(false);
  }

  private subir(expediente: ExpedienteEnCola): Promise<void> {
    const servicio = this.servicio();

    return new Promise((resolver) => {
      this.parchar(expediente.id, { estado: 'subiendo', progreso: 0 });

      // Los documentos con error no viajan: el backend los rechazaría igual y
      // se llevaría el expediente completo con ellos.
      const archivos = expediente.documentos.filter((d) => !d.error).map((d) => d.file);

      this.api.enviar(archivos, servicio.id, expediente.numero).subscribe({
        next: (evento) => {
          if (evento.type === HttpEventType.UploadProgress && evento.total) {
            this.parchar(expediente.id, {
              progreso: Math.round((evento.loaded / evento.total) * 100),
            });
          }
          if (evento.type === HttpEventType.Response) {
            this.parchar(expediente.id, {
              estado: 'listo',
              progreso: 100,
              codigo: evento.body?.codigo,
            });
          }
        },
        error: (respuesta) => {
          // El backend explica el rechazo —saldo, formato, archivo ilegible—
          // y eso es más útil que un mensaje genérico.
          this.parchar(expediente.id, {
            estado: 'error',
            error:
              respuesta?.error?.detail ??
              'No se pudo enviar. Revisa tu conexión e inténtalo de nuevo.',
          });
          resolver();
        },
        complete: () => resolver(),
      });
    });
  }

  private parchar(id: number, cambios: Partial<ExpedienteEnCola>): void {
    this.cola.update((actual) =>
      actual.map((e) => (e.id === id ? { ...e, ...cambios } : e)),
    );
  }

  private parcharDocumento(
    idExpediente: number,
    idDocumento: number,
    cambios: Partial<DocumentoEnCola>,
  ): void {
    this.cola.update((actual) =>
      actual.map((e) =>
        e.id !== idExpediente
          ? e
          : {
              ...e,
              documentos: e.documentos.map((d) =>
                d.id === idDocumento ? { ...d, ...cambios } : d,
              ),
            },
      ),
    );
  }

  protected irAlPanel(): void {
    this.router.navigate(['/panel']);
  }

  /* ===== Presentación ===== */

  protected nombreDe(expediente: ExpedienteEnCola): string {
    return expediente.numero ?? expediente.documentos[0]?.file.name ?? 'Sin nombre';
  }

  protected pesoDe(expediente: ExpedienteEnCola): string {
    const bytes = expediente.documentos.reduce((suma, d) => suma + d.file.size, 0);
    return this.peso(bytes);
  }

  protected minutosDe(expediente: ExpedienteEnCola): number | null {
    const conDuracion = expediente.documentos.filter((d) => d.minutos !== null);
    if (!conDuracion.length) {
      return null;
    }
    return conDuracion.reduce((suma, d) => suma + (d.minutos ?? 0), 0);
  }

  protected peso(bytes: number): string {
    const mb = bytes / 1024 / 1024;
    return mb < 1 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${mb.toFixed(1)} MB`;
  }
}

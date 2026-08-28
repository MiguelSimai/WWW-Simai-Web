import { provideHttpClient } from '@angular/common/http';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { HttpEventType } from '@angular/common/http';
import { AUTH, Auth } from '../../core/auth';
import { ServicioId, Usuario } from '../../core/modelos';
import { SolicitudesApi } from '../../core/solicitudes-api.service';
import { EnviarComponent } from './enviar.component';

/** Sesión con los servicios que la cuenta tiene contratados. */
function authDoble(servicios: readonly ServicioId[]): Auth {
  const usuario: Usuario = {
    id: 'u-1',
    email: 'ana@acme.cl',
    nombre: 'Ana',
    empresa: 'Acme',
    contratado: true,
    servicios,
  };
  return {
    usuario: signal(usuario).asReadonly(),
    autenticado: signal(true).asReadonly(),
    cargarSesion: () => Promise.resolve(),
    listo: () => Promise.resolve(),
    irALogin: () => {},
    salir: () => Promise.resolve(),
    expirar: () => {},
  } as unknown as Auth;
}

/** Lo que tiene contratado el cliente en la mayoría de estas pruebas. */
const CONTRATADOS: readonly ServicioId[] = ['transcripcion', 'documentos', 'conversaciones'];

/** Construye un File con tamaño simulado, sin reservar memoria de verdad. */
function archivo(nombre: string, mb = 1, tipo = ''): File {
  const f = new File(['x'], nombre, { type: tipo });
  Object.defineProperty(f, 'size', { value: Math.round(mb * 1024 * 1024) });
  return f;
}

/** Un archivo como los que entrega el input de carpetas: con su ruta. */
function enCarpeta(carpeta: string, nombre: string, mb = 1, tipo = ''): File {
  const f = archivo(nombre, mb, tipo);
  Object.defineProperty(f, 'webkitRelativePath', { value: `${carpeta}/${nombre}` });
  return f;
}

function soltar(html: HTMLElement, ...files: File[]): void {
  const evento = new Event('drop') as DragEvent;
  // Sin `items` el componente cae a `files`, que es la vía de los archivos
  // sueltos. Las carpetas arrastradas usan webkitGetAsEntry, que no existe
  // en este entorno de pruebas.
  Object.defineProperty(evento, 'dataTransfer', { value: { files } });
  html.querySelector('.zona')!.dispatchEvent(evento);
}

describe('EnviarComponent', () => {
  let fixture: ComponentFixture<EnviarComponent>;
  let html: HTMLElement;
  let enviar: jasmine.Spy;

  async function montar(servicios: readonly ServicioId[] = CONTRATADOS) {
    TestBed.resetTestingModule();
    enviar = jasmine
      .createSpy('enviar')
      .and.returnValue(
        of({ type: HttpEventType.Response, body: { codigo: 'SOL-1', estado: 'procesando' } }),
      );

    await TestBed.configureTestingModule({
      imports: [EnviarComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: SolicitudesApi, useValue: { enviar } },
        { provide: AUTH, useValue: authDoble(servicios) },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(EnviarComponent);
    fixture.detectChanges();
    html = fixture.nativeElement;
  }

  beforeEach(async () => {
    await montar();
  });

  /** Cada fila de la cola es un expediente, no un archivo. */
  const items = () => html.querySelectorAll('.item');

  async function asentar() {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('parte en transcripción y muestra sus extensiones', () => {
    expect(html.querySelector('.zona__ayuda')?.textContent).toContain('.mp3');
    expect(html.querySelector('.zona__ayuda')?.textContent).toContain('25 MB');
  });

  it('ofrece elegir archivos y carpetas', () => {
    const inputs = html.querySelectorAll<HTMLInputElement>('.zona input[type=file]');

    expect(inputs.length).toBe(2);
    expect(inputs[1].hasAttribute('webkitdirectory')).toBeTrue();
  });

  it('no ofrece servicios que el portal todavía no puede procesar', () => {
    const nombres = Array.from(html.querySelectorAll('.opcion')).map((o) => o.textContent);

    expect(nombres.length).toBe(3);
    expect(nombres.join(' ')).not.toContain('Automatización');
  });

  it('ofrece sólo lo que la cuenta tiene contratado', async () => {
    await montar(['documentos']);

    const nombres = Array.from(html.querySelectorAll('.opcion')).map((o) => o.textContent);

    expect(nombres.length).toBe(1);
    expect(nombres[0]).toContain('Análisis de documentos');
  });

  it('avisa en vez de dejar subir cuando la cuenta no tiene nada activo', async () => {
    await montar([]);

    expect(html.querySelector('.sin-servicios')).toBeTruthy();
    expect(html.querySelector('.zona')).withContext('sin zona de carga').toBeNull();
    expect(html.querySelectorAll('.opcion').length).toBe(0);
  });

  it('acepta un archivo válido y lo deja listo para enviar', async () => {
    soltar(html, archivo('reunion.mp3', 5, 'audio/mpeg'));
    await asentar();

    expect(items().length).toBe(1);
    expect(html.querySelector('.item--error')).toBeNull();
    expect(html.querySelector('.resumen')).toBeTruthy();
  });

  it('rechaza una extensión que el servicio no procesa', async () => {
    soltar(html, archivo('contrato.pdf', 1, 'application/pdf'));
    await asentar();

    expect(html.querySelector('.item--error')).toBeTruthy();
    expect(html.querySelector('.item__error')?.textContent).toContain('.pdf');
    expect(html.querySelector('.resumen'))
      .withContext('un archivo inválido no debería habilitar el envío')
      .toBeNull();
  });

  it('rechaza un archivo que supera el tope de tamaño', async () => {
    soltar(html, archivo('largo.mp3', 30, 'audio/mpeg'));
    await asentar();

    expect(html.querySelector('.item__error')?.textContent).toContain('25 MB');
  });

  it('rechaza un archivo vacío', async () => {
    soltar(html, archivo('vacio.mp3', 0, 'audio/mpeg'));
    await asentar();

    expect(html.querySelector('.item__error')?.textContent).toContain('vacío');
  });

  it('no promete un total cuando el volumen no se puede medir', async () => {
    // Documentos: las páginas no se conocen hasta abrir el archivo.
    (html.querySelectorAll('.opcion')[1] as HTMLButtonElement).click();
    fixture.detectChanges();

    soltar(html, archivo('contrato.pdf', 2, 'application/pdf'));
    await asentar();

    expect(html.querySelector('.resumen__total')).toBeNull();
    expect(html.querySelector('.resumen__nota')?.textContent).toContain('35');
  });

  it('vacía la cola al cambiar de servicio', async () => {
    soltar(html, archivo('reunion.mp3', 5, 'audio/mpeg'));
    await asentar();
    expect(items().length).toBe(1);

    (html.querySelectorAll('.opcion')[1] as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(items().length).toBe(0);
  });

  it('permite quitar un expediente de la cola', async () => {
    soltar(html, archivo('reunion.mp3', 5, 'audio/mpeg'));
    await asentar();

    (html.querySelector('.item__quitar') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(items().length).toBe(0);
  });

  it('envía cada archivo suelto como su propia solicitud', async () => {
    soltar(html, archivo('a.mp3', 2, 'audio/mpeg'), archivo('b.mp3', 3, 'audio/mpeg'));
    await asentar();
    expect(items().length).toBe(2);

    (html.querySelector('.resumen .btn') as HTMLButtonElement).click();
    await asentar();

    expect(enviar).toHaveBeenCalledTimes(2);
    // (archivos, servicio, numeroCliente)
    expect(enviar.calls.first().args[1]).toBe('transcripcion');
    expect(enviar.calls.first().args[2]).toBeNull();
    expect(html.querySelector('.final')).toBeTruthy();
    expect(html.querySelectorAll('.badge--ok').length).toBe(2);
  });

  it('no envía los archivos rechazados', async () => {
    soltar(html, archivo('ok.mp3', 2, 'audio/mpeg'), archivo('malo.pdf', 1, 'application/pdf'));
    await asentar();

    (html.querySelector('.resumen .btn') as HTMLButtonElement).click();
    await asentar();

    expect(enviar).toHaveBeenCalledTimes(1);
  });

  describe('carpetas', () => {
    /** Elige documentos, que es el servicio del caso de los expedientes. */
    async function conDocumentos(...files: File[]) {
      (html.querySelectorAll('.opcion')[1] as HTMLButtonElement).click();
      fixture.detectChanges();
      soltar(html, ...files);
      await asentar();
    }

    it('agrupa los archivos de una carpeta en una sola solicitud', async () => {
      await conDocumentos(
        enCarpeta('297541', 'CARTA COMPROMISO DE PAGO.pdf', 1, 'application/pdf'),
        enCarpeta('297541', 'CAV FINAL.pdf', 1, 'application/pdf'),
        enCarpeta('297541', 'CONTRATO.pdf', 1, 'application/pdf'),
        enCarpeta('297541', 'PAGARE.pdf', 2, 'application/pdf'),
      );

      expect(items().length).withContext('cuatro archivos, un expediente').toBe(1);
      expect(html.querySelector('.item__etiqueta')?.textContent).toContain('297541');
      expect(html.querySelector('.item__meta')?.textContent).toContain('4 archivos');
    });

    it('manda el número de la carpeta como número de solicitud', async () => {
      await conDocumentos(
        enCarpeta('297541', 'CONTRATO.pdf', 1, 'application/pdf'),
        enCarpeta('297541', 'PAGARE.pdf', 1, 'application/pdf'),
      );

      (html.querySelector('.resumen .btn') as HTMLButtonElement).click();
      await asentar();

      expect(enviar).toHaveBeenCalledTimes(1);
      const [archivos, servicio, numero] = enviar.calls.first().args;
      expect(archivos.length).toBe(2);
      expect(servicio).toBe('documentos');
      expect(numero).toBe('297541');
    });

    it('separa las subcarpetas cuando se elige la carpeta que las agrupa', async () => {
      // Elegir "Victor IA" entrega las rutas con la raíz por delante: el
      // expediente sigue siendo la carpeta que contiene cada archivo.
      await conDocumentos(
        enCarpeta('Victor IA/297541', 'CONTRATO.pdf', 1, 'application/pdf'),
        enCarpeta('Victor IA/297541', 'PAGARE.pdf', 1, 'application/pdf'),
        enCarpeta('Victor IA/609395', 'CONTRATO.pdf', 1, 'application/pdf'),
      );

      expect(items().length).withContext('dos expedientes, no uno').toBe(2);

      const etiquetas = Array.from(html.querySelectorAll('.item__etiqueta')).map((e) =>
        e.textContent?.trim(),
      );
      expect(etiquetas).toEqual(['Solicitud 297541', 'Solicitud 609395']);
    });

    it('separa dos carpetas en dos solicitudes', async () => {
      await conDocumentos(
        enCarpeta('297541', 'CONTRATO.pdf', 1, 'application/pdf'),
        enCarpeta('297541', 'PAGARE.pdf', 1, 'application/pdf'),
        enCarpeta('609395', 'CONTRATO.pdf', 1, 'application/pdf'),
      );

      expect(items().length).toBe(2);

      (html.querySelector('.resumen .btn') as HTMLButtonElement).click();
      await asentar();

      expect(enviar).toHaveBeenCalledTimes(2);
      const numeros = enviar.calls.all().map((c) => c.args[2]);
      expect(numeros).toEqual(['297541', '609395']);
    });

    it('deja fuera el archivo que no sirve pero manda el resto de la carpeta', async () => {
      await conDocumentos(
        enCarpeta('297541', 'CONTRATO.pdf', 1, 'application/pdf'),
        enCarpeta('297541', 'notas.docx', 1),
      );

      expect(items().length).toBe(1);
      expect(html.querySelector('.item__error')?.textContent).toContain('notas.docx');

      (html.querySelector('.resumen .btn') as HTMLButtonElement).click();
      await asentar();

      expect(enviar).toHaveBeenCalledTimes(1);
      expect(enviar.calls.first().args[0].length)
        .withContext('sólo el PDF viaja')
        .toBe(1);
    });

    it('no envía una carpeta donde ningún archivo sirve', async () => {
      await conDocumentos(
        enCarpeta('297541', 'a.docx', 1),
        enCarpeta('297541', 'b.xlsx', 1),
      );

      expect(html.querySelector('.item--error')).toBeTruthy();
      expect(html.querySelector('.resumen')).toBeNull();
    });

    it('muestra el motivo que da el backend cuando rechaza el expediente', async () => {
      enviar.and.returnValue(
        throwError(() => ({ error: { detail: 'Saldo insuficiente: cuesta $560.' } })),
      );

      await conDocumentos(enCarpeta('297541', 'CONTRATO.pdf', 1, 'application/pdf'));

      (html.querySelector('.resumen .btn') as HTMLButtonElement).click();
      await asentar();

      expect(html.querySelector('.item__error')?.textContent).toContain('Saldo insuficiente');
    });
  });
});

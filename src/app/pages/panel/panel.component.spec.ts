import { registerLocaleData } from '@angular/common';
import localeEsCl from '@angular/common/locales/es-CL';
import { LOCALE_ID, computed, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AUTH, Auth } from '../../core/auth';
import { EstadoSolicitud, Solicitud, Usuario } from '../../core/modelos';
import { SolicitudesService } from '../../core/solicitudes.service';
import { PanelComponent } from './panel.component';

const ANA: Usuario = {
  id: 'u-1',
  email: 'ana.perez@acme.cl',
  nombre: 'Ana Pérez',
  empresa: 'Acme',
  saldo: 48_600,
  contratado: true,
};

/** Un expediente de ejemplo, con lo mínimo para pintar una fila. */
function solicitud(
  codigo: string,
  estado: EstadoSolicitud,
  extra: Partial<Solicitud> = {},
): Solicitud {
  return {
    codigo,
    servicio: 'documentos',
    numeroCliente: null,
    etiqueta: 'informe.pdf',
    documentos: 1,
    unidades: 4,
    costo: 140,
    fecha: '2026-08-22T10:00:00',
    estado,
    resultado: 'Sin observaciones',
    ...extra,
  };
}

const SOLICITUDES: readonly Solicitud[] = [
  solicitud('SOL-0001', 'completada'),
  solicitud('SOL-0002', 'procesando'),
  solicitud('SOL-0003', 'procesando'),
  solicitud('SOL-0004', 'revisar'),
  solicitud('SOL-0005', 'error'),
  // Un expediente de verdad: carpeta con número y varios documentos.
  solicitud('SOL-0006', 'completada', {
    numeroCliente: '297541',
    etiqueta: '297541',
    documentos: 4,
    unidades: 16,
    costo: 560,
  }),
];

function authDoble(usuario: Usuario | null): Auth {
  const actual = signal(usuario);
  return {
    usuario: actual.asReadonly(),
    autenticado: signal(usuario !== null).asReadonly(),
    cargarSesion: () => Promise.resolve(),
    listo: () => Promise.resolve(),
    irALogin: () => {},
    salir: () => Promise.resolve(),
    expirar: () => {},
  } as unknown as Auth;
}

/**
 * Doble del servicio: el panel se prueba contra datos fijos, sin HTTP. Que la
 * carga y el polling funcionen es asunto del servicio, no de esta pantalla.
 */
function solicitudesDoble(datos: readonly Solicitud[] = SOLICITUDES) {
  const lista = signal(datos);
  const vigilar = jasmine.createSpy('vigilar').and.resolveTo();
  const detener = jasmine.createSpy('detener');

  return {
    solicitudes: lista.asReadonly(),
    cargando: signal(false).asReadonly(),
    error: signal<string | null>(null).asReadonly(),
    total: computed(() => lista().length),
    enProceso: computed(() => lista().filter((s) => s.estado === 'procesando').length),
    porRevisar: computed(() => lista().filter((s) => s.estado === 'revisar').length),
    gastoTotal: computed(() => lista().reduce((t, s) => t + s.costo, 0)),
    filtrarPorEstado: (e: EstadoSolicitud | 'todas') =>
      e === 'todas' ? lista() : lista().filter((s) => s.estado === e),
    cargar: () => Promise.resolve(),
    descargarExcel: jasmine.createSpy('descargarExcel').and.resolveTo(),
    detalle: jasmine
      .createSpy('detalle')
      .and.callFake((codigo: string) =>
        Promise.resolve({ codigo, documentosDetalle: DOCUMENTOS } as never),
      ),
    vigilar,
    detener,
  };
}

const DOCUMENTOS = [
  {
    codigo: 'DOC-0001',
    archivo: 'CONTRATO.pdf',
    unidades: 9,
    costo: 315,
    estado: 'completada' as EstadoSolicitud,
    resultado: 'Sin observaciones',
    confianza: 94,
    error: null,
    respuestaIa: null,
  },
  {
    codigo: 'DOC-0002',
    archivo: 'PAGARE.pdf',
    unidades: 4,
    costo: 140,
    estado: 'revisar' as EstadoSolicitud,
    resultado: 'Firma del aval ausente',
    confianza: 41,
    error: null,
    respuestaIa: null,
  },
];

registerLocaleData(localeEsCl);

describe('PanelComponent', () => {
  let fixture: ComponentFixture<PanelComponent>;
  let html: HTMLElement;
  let doble: ReturnType<typeof solicitudesDoble>;

  const filas = () => html.querySelectorAll('.solicitud');
  const filtro = (label: string) =>
    Array.from(html.querySelectorAll<HTMLButtonElement>('.filtro')).find((b) =>
      b.textContent?.includes(label),
    );

  async function montar(usuario: Usuario | null, datos?: readonly Solicitud[]) {
    TestBed.resetTestingModule();
    doble = solicitudesDoble(datos);

    await TestBed.configureTestingModule({
      imports: [PanelComponent],
      providers: [
        provideRouter([]),
        { provide: LOCALE_ID, useValue: 'es-CL' },
        // El guard ya garantiza la sesión; aquí se da por abierta.
        { provide: AUTH, useValue: authDoble(usuario) },
        { provide: SolicitudesService, useValue: doble },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(PanelComponent);
    fixture.detectChanges();
    html = fixture.nativeElement;
  }

  beforeEach(async () => {
    await montar(ANA);
  });

  it('saluda al usuario de la sesión', () => {
    expect(html.querySelector('.panel__titulo')?.textContent).toContain('Ana Pérez');
  });

  it('muestra el saldo que entrega el backend', () => {
    const saldo = html.querySelector('.indicador__valor')?.textContent?.trim();

    expect(saldo).toContain('48.600');
  });

  it('empieza a vigilar al entrar y deja de hacerlo al salir', () => {
    expect(doble.vigilar).toHaveBeenCalled();

    fixture.destroy();

    expect(doble.detener).toHaveBeenCalled();
  });

  it('parte mostrando todas las solicitudes', () => {
    expect(filas().length).toBe(SOLICITUDES.length);
  });

  it('nombra un expediente por su número y dice cuántos archivos lleva', () => {
    const expediente = Array.from(filas()).find((f) =>
      f.textContent?.includes('SOL-0006'),
    );

    expect(expediente?.textContent).toContain('297541');
    expect(expediente?.textContent).toContain('4 archivos');
  });

  it('no cuenta archivos cuando el expediente trae uno solo', () => {
    const suelta = Array.from(filas()).find((f) => f.textContent?.includes('SOL-0001'));

    expect(suelta?.textContent).not.toContain('1 archivos');
  });

  it('filtra por estado al pulsar un filtro', () => {
    filtro('Procesando')?.click();
    fixture.detectChanges();

    expect(filas().length).toBe(2);
  });

  it('vuelve al total al pulsar "Todas"', () => {
    filtro('Con error')?.click();
    fixture.detectChanges();
    expect(filas().length).toBeLessThan(SOLICITUDES.length);

    filtro('Todas')?.click();
    fixture.detectChanges();
    expect(filas().length).toBe(SOLICITUDES.length);
  });

  it('muestra un indicador por métrica de la cuenta', () => {
    expect(html.querySelectorAll('.indicador').length).toBe(4);
  });

  it('ofrece ver los archivos de cada solicitud', () => {
    const expediente = Array.from(filas()).find((f) => f.textContent?.includes('SOL-0006'));

    expect(expediente?.querySelector('.documentos summary')?.textContent).toContain(
      'los 4 archivos',
    );
  });

  it('trae los archivos recién al abrir el desplegable', async () => {
    const expediente = Array.from(filas()).find((f) => f.textContent?.includes('SOL-0006'))!;
    const detalles = expediente.querySelector('details') as HTMLDetailsElement;

    expect(doble.detalle).withContext('nada se pide de entrada').not.toHaveBeenCalled();

    detalles.open = true;
    detalles.dispatchEvent(new Event('toggle'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(doble.detalle).toHaveBeenCalledWith('SOL-0006');
    expect(expediente.querySelectorAll('.documento').length).toBe(2);
    expect(expediente.textContent).toContain('CONTRATO.pdf');
    expect(expediente.textContent).toContain('Firma del aval ausente');
  });

  it('no vuelve a pedir los archivos al cerrar y abrir', async () => {
    const expediente = Array.from(filas()).find((f) => f.textContent?.includes('SOL-0006'))!;
    const detalles = expediente.querySelector('details') as HTMLDetailsElement;

    for (const abierto of [true, false, true]) {
      detalles.open = abierto;
      detalles.dispatchEvent(new Event('toggle'));
      await fixture.whenStable();
    }
    fixture.detectChanges();

    expect(doble.detalle).toHaveBeenCalledTimes(1);
  });

  describe('descarga de la planilla', () => {
    const boton = () =>
      Array.from(html.querySelectorAll<HTMLButtonElement>('.descarga .btn')).find((b) =>
        b.textContent?.includes('Descargar'),
      )!;

    it('propone el último mes por defecto', () => {
      const fechas = html.querySelectorAll<HTMLInputElement>('.campo-fecha input');

      expect(fechas.length).toBe(2);
      const dias =
        (new Date(fechas[1].value).getTime() - new Date(fechas[0].value).getTime()) / 86_400_000;
      expect(Math.round(dias)).toBe(30);
    });

    it('descarga con el rango elegido', async () => {
      const fechas = html.querySelectorAll<HTMLInputElement>('.campo-fecha input');
      fechas[0].value = '2026-08-01';
      fechas[0].dispatchEvent(new Event('change'));
      fechas[1].value = '2026-08-23';
      fechas[1].dispatchEvent(new Event('change'));
      fixture.detectChanges();

      boton().click();
      await fixture.whenStable();

      expect(doble.descargarExcel).toHaveBeenCalledWith('2026-08-01', '2026-08-23');
    });

    it('explica el 404 como que no hay nada en el rango', async () => {
      doble.descargarExcel.and.rejectWith({ status: 404 });

      boton().click();
      await fixture.whenStable();
      fixture.detectChanges();

      expect(html.querySelector('.descarga__error')?.textContent).toContain(
        'No hay expedientes terminados',
      );
    });

    it('avisa de un fallo cualquiera sin culpar al usuario', async () => {
      doble.descargarExcel.and.rejectWith({ status: 500 });

      boton().click();
      await fixture.whenStable();
      fixture.detectChanges();

      expect(html.querySelector('.descarga__error')?.textContent).toContain(
        'No pudimos generar la planilla',
      );
    });
  });

  it('avisa cuando no hay nada en un estado', async () => {
    await montar(ANA, [solicitud('SOL-0001', 'completada')]);

    filtro('Con error')?.click();
    fixture.detectChanges();

    expect(html.querySelector('.vacio')).toBeTruthy();
    expect(filas().length).toBe(0);
  });

  it('ofrece contratar en vez de un panel vacío a quien no ha cargado saldo', async () => {
    await montar({ id: 'u-3', email: 'nuevo@y.cl', nombre: 'Nuevo', contratado: false });

    expect(html.querySelector('.bienvenida')).toBeTruthy();
    expect(filas().length).toBe(0);
    expect(html.querySelector('.indicadores')).toBeNull();
  });
});

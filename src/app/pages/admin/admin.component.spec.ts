import { registerLocaleData } from '@angular/common';
import localeEsCl from '@angular/common/locales/es-CL';
import { LOCALE_ID, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AdminService, CuentaAdmin, UsuarioAdmin } from '../../core/admin.service';
import { AdminComponent } from './admin.component';

const ACME: CuentaAdmin = {
  id: 'c-1',
  nombre: 'Acme Créditos',
  rut: '76543210-3',
  saldo: 106_110,
  usuarios: 2,
  solicitudes: 6,
  procesos: [
    {
      servicio: 'documentos',
      tipo_servicio: 'documentos',
      proceso_codigo: 'simai_doc_acme',
      id_proceso: 7,
      plantilla_id: 'pl-1',
      plantilla: 'Operaciones',
    },
  ],
};

const SIN_SERVICIOS: CuentaAdmin = {
  id: 'c-2',
  nombre: 'Cliente nuevo',
  rut: null,
  saldo: 0,
  usuarios: 1,
  solicitudes: 0,
  procesos: [],
};

const USUARIOS: UsuarioAdmin[] = [
  {
    id: 'u-1',
    email: 'ana@acme.cl',
    nombre: 'Ana',
    cuenta_id: 'c-1',
    cuenta: 'Acme Créditos',
    ultimo_acceso_en: null,
  },
  {
    id: 'u-2',
    email: 'pedro@acme.cl',
    nombre: 'Pedro',
    cuenta_id: 'c-2',
    cuenta: 'Cliente nuevo',
    ultimo_acceso_en: null,
  },
];

function adminDoble() {
  return {
    cuentas: signal<readonly CuentaAdmin[]>([ACME, SIN_SERVICIOS]),
    usuarios: signal<readonly UsuarioAdmin[]>(USUARIOS),
    plantillas: signal([{ id: 'pl-1', servicio: 'documentos', nombre: 'Operaciones' }]),
    recargas: signal([
      {
        id: 'r-1',
        estado: 'pendiente' as const,
        pack_id: 'impulso',
        monto_declarado: 100_000,
        referencia: 'TEF-9911',
        monto_acreditado: null,
        nota: null,
        creada_en: '2026-09-02T12:00:00Z',
        resuelta_en: null,
        resuelta_por: null,
        cuenta_id: 'c-1',
        cuenta: 'Acme Créditos',
        cuenta_rut: '76543210-3',
        declarada_por: 'ana@acme.cl',
        bonus: 8_000,
        sugerido: 108_000,
      },
    ]),
    cargar: jasmine.createSpy('cargar').and.resolveTo(),
    acreditarRecarga: jasmine.createSpy('acreditarRecarga').and.resolveTo(),
    rechazarRecarga: jasmine.createSpy('rechazarRecarga').and.resolveTo(),
    crearCuenta: jasmine.createSpy('crearCuenta').and.resolveTo(),
    habilitarProceso: jasmine.createSpy('habilitarProceso').and.resolveTo(),
    quitarProceso: jasmine.createSpy('quitarProceso').and.resolveTo(),
    moverUsuario: jasmine.createSpy('moverUsuario').and.resolveTo(),
  };
}

registerLocaleData(localeEsCl);

describe('AdminComponent', () => {
  let fixture: ComponentFixture<AdminComponent>;
  let html: HTMLElement;
  let doble: ReturnType<typeof adminDoble>;

  beforeEach(async () => {
    doble = adminDoble();

    await TestBed.configureTestingModule({
      imports: [AdminComponent],
      providers: [
        { provide: LOCALE_ID, useValue: 'es-CL' },
        { provide: AdminService, useValue: doble },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    html = fixture.nativeElement;
  });

  it('propone acreditar lo declarado más el bono del pack', () => {
    const monto = html.querySelector<HTMLInputElement>('.recarga input[type="number"]')!;

    expect(monto.value).toBe('108000');
    expect(html.querySelector('.recarga__ref')?.textContent).toContain('TEF-9911');
  });

  it('acredita con el monto que quedó en el campo, no con el declarado', async () => {
    const monto = html.querySelector<HTMLInputElement>('.recarga input[type="number"]')!;
    // Llegó menos de lo declarado: se acredita lo que dice la cartola.
    monto.value = '50000';
    monto.dispatchEvent(new Event('input'));

    html.querySelector<HTMLButtonElement>('.recarga .btn--primary')!.click();
    await fixture.whenStable();

    expect(doble.acreditarRecarga).toHaveBeenCalledWith('r-1', 50_000, null);
  });

  it('no rechaza una recarga sin motivo', async () => {
    html.querySelector<HTMLButtonElement>('.recarga .btn--ghost')!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(doble.rechazarRecarga).not.toHaveBeenCalled();
    expect(html.querySelector('.field__error')?.textContent).toContain('motivo');
  });

  it('carga las cuentas al entrar', () => {
    expect(doble.cargar).toHaveBeenCalled();
    expect(html.querySelectorAll('.cuenta').length).toBe(2);
  });

  it('muestra el proceso del motor de cada servicio habilitado', () => {
    const proceso = html.querySelector('.proceso');

    expect(proceso?.textContent).toContain('Análisis de documentos');
    expect(proceso?.textContent).toContain('simai_doc_acme');
    expect(proceso?.textContent).toContain('id 7');
    expect(proceso?.textContent).toContain('Operaciones');
  });

  it('advierte cuando una cuenta no puede enviar nada', () => {
    const avisos = html.querySelectorAll('.cuenta__sin');

    expect(avisos.length).toBe(1);
    expect(avisos[0].textContent).toContain('no puede enviar nada');
  });

  it('crea una cuenta con el nombre escrito', async () => {
    const input = html.querySelector<HTMLInputElement>('.nueva input')!;
    input.value = 'Nueva Empresa';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    html.querySelector<HTMLFormElement>('.nueva')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    // Sin RUT: el campo es opcional y viaja como null.
    expect(doble.crearCuenta).toHaveBeenCalledWith('Nueva Empresa', null);
  });

  it('crea una cuenta con RUT cuando se escribe', async () => {
    const [nombre, rut] = Array.from(
      html.querySelectorAll<HTMLInputElement>('.nueva input'),
    );
    nombre.value = 'Nueva Empresa';
    nombre.dispatchEvent(new Event('input'));
    rut.value = '76.543.210-3';
    rut.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    html.querySelector<HTMLFormElement>('.nueva')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    // Se manda tal cual se escribió: normalizarlo es cosa del servidor, que es
    // quien además valida el dígito verificador.
    expect(doble.crearCuenta).toHaveBeenCalledWith('Nueva Empresa', '76.543.210-3');
  });

  it('muestra el RUT de la cuenta, o que falta', () => {
    const botones = Array.from(html.querySelectorAll('.cuenta__rut'));

    expect(botones[0].textContent?.trim()).toBe('76543210-3');
    expect(botones[1].textContent?.trim()).toBe('Sin RUT');
  });

  it('no crea una cuenta sin nombre', async () => {
    html.querySelector<HTMLFormElement>('.nueva')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(doble.crearCuenta).not.toHaveBeenCalled();
  });

  it('habilita un servicio con los datos del proceso del motor', async () => {
    const abrir = Array.from(html.querySelectorAll<HTMLButtonElement>('.btn')).find((b) =>
      b.textContent?.includes('Habilitar servicio'),
    )!;
    abrir.click();
    fixture.detectChanges();

    const alta = html.querySelector('.alta')!;
    // Por formControlName: hay dos inputs de texto y el primero es
    // tipo_servicio, así que un selector por tipo apuntaría al equivocado.
    const codigo = alta.querySelector<HTMLInputElement>('[formControlName=proceso_codigo]')!;
    const id = alta.querySelector<HTMLInputElement>('[formControlName=id_proceso]')!;

    codigo.value = 'simai_doc_nuevo';
    codigo.dispatchEvent(new Event('input'));
    id.value = '12';
    id.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    alta.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(doble.habilitarProceso).toHaveBeenCalledWith('c-1', {
      servicio: 'documentos',
      tipo_servicio: 'documentos',
      proceso_codigo: 'simai_doc_nuevo',
      id_proceso: 12,
      plantilla_id: null,
    });
  });

  it('no habilita sin el código del proceso', async () => {
    Array.from(html.querySelectorAll<HTMLButtonElement>('.btn'))
      .find((b) => b.textContent?.includes('Habilitar servicio'))!
      .click();
    fixture.detectChanges();

    html.querySelector('.alta')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(doble.habilitarProceso).not.toHaveBeenCalled();
  });

  it('quita un servicio', async () => {
    html.querySelector<HTMLButtonElement>('.proceso__quitar')!.click();
    await fixture.whenStable();

    expect(doble.quitarProceso).toHaveBeenCalledWith('c-1', 'documentos');
  });

  it('mueve un usuario a otra cuenta', async () => {
    const select = html.querySelectorAll<HTMLSelectElement>('.usuario select')[0];
    select.value = 'c-2';
    select.dispatchEvent(new Event('change'));
    await fixture.whenStable();

    expect(doble.moverUsuario).toHaveBeenCalledWith('u-1', 'c-2');
  });

  it('no ofrece mover a la cuenta en la que ya está', () => {
    const opciones = Array.from(
      html.querySelectorAll<HTMLSelectElement>('.usuario select')[0].options,
    ).map((o) => o.value);

    expect(opciones).not.toContain('c-1');
    expect(opciones).toContain('c-2');
  });
});

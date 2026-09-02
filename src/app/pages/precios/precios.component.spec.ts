import { registerLocaleData } from '@angular/common';
import localeEsCl from '@angular/common/locales/es-CL';
import { LOCALE_ID, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { AUTH, Auth } from '../../core/auth';
import { CATALOGO } from '../../core/catalogo';
import { CuentaService } from '../../core/cuenta.service';
import { PreciosComponent } from './precios.component';

registerLocaleData(localeEsCl);

describe('PreciosComponent', () => {
  let fixture: ComponentFixture<PreciosComponent>;
  let html: HTMLElement;
  let irALogin: jasmine.Spy;
  let contratar: jasmine.Spy;
  let autenticado: ReturnType<typeof signal<boolean>>;

  const texto = (selector: string) => html.querySelector(selector)?.textContent?.trim() ?? '';

  beforeEach(async () => {
    irALogin = jasmine.createSpy('irALogin');
    contratar = jasmine.createSpy('contratar').and.resolveTo(undefined);
    autenticado = signal(false);

    await TestBed.configureTestingModule({
      imports: [PreciosComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: LOCALE_ID, useValue: 'es-CL' },
        { provide: CuentaService, useValue: { contratar } },
        {
          provide: AUTH,
          useValue: {
            usuario: signal({ id: 'u-1', email: 'ana@acme.cl', nombre: 'Ana' }).asReadonly(),
            autenticado: autenticado.asReadonly(),
            proveedores: signal(['google']).asReadonly(),
            cargarSesion: () => Promise.resolve(),
    listo: () => Promise.resolve(),
            irALogin,
            salir: () => Promise.resolve(),
            expirar: () => {},
          } as unknown as Auth,
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(PreciosComponent);
    fixture.detectChanges();
    html = fixture.nativeElement;
  });

  it('lista una fila de tarifa por servicio del catálogo', () => {
    expect(html.querySelectorAll('.tarifas tbody tr').length).toBe(CATALOGO.length);
  });

  it('estima el costo como precio unitario por cantidad', () => {
    // Por defecto: transcripción (12/min) × 120 min.
    expect(texto('.calc__total-monto')).toContain('1.440');

    const cantidad = html.querySelector('#calc-cantidad') as HTMLInputElement;
    cantidad.value = '300';
    cantidad.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(texto('.calc__total-monto')).toContain('3.600');
  });

  it('recalcula al cambiar de servicio', () => {
    const servicio = html.querySelector('#calc-servicio') as HTMLSelectElement;
    servicio.value = 'documentos';
    servicio.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    // Documentos: 35 por página × 120 páginas.
    expect(texto('.calc__total-monto')).toContain('4.200');
  });

  it('ignora cantidades negativas en vez de estimar un cobro negativo', () => {
    const cantidad = html.querySelector('#calc-cantidad') as HTMLInputElement;
    cantidad.value = '-50';
    cantidad.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(texto('.calc__total-monto')).toContain('0');
    expect(texto('.calc__total-monto')).not.toContain('-');
  });

  it('suma el saldo de regalo del pack seleccionado', () => {
    // "Impulso" viene marcado por defecto: 100.000 + 8.000.
    expect(texto('.contratar__total')).toContain('108.000');
  });

  it('no envía el formulario incompleto y explica por qué', () => {
    const form = html.querySelector('.contratar__form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(html.querySelectorAll('.field__error').length).toBeGreaterThan(0);
    expect(irALogin)
      .withContext('no debería mandar al login con el formulario inválido')
      .not.toHaveBeenCalled();
  });

  it('deriva al ingreso con Google cuando aún no hay sesión', () => {
    const escribir = (id: string, valor: string) => {
      const campo = html.querySelector(`#${id}`) as HTMLInputElement;
      campo.value = valor;
      campo.dispatchEvent(new Event('input'));
    };

    escribir('nombre', 'Ana Pérez');
    escribir('email', 'ana@acme.cl');
    (html.querySelector('.contratar__form') as HTMLFormElement)
      .dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(irALogin).toHaveBeenCalledWith('/precios', 'google');
    expect(contratar).not.toHaveBeenCalled();
  });

  describe('con sesión ya iniciada', () => {
    beforeEach(() => {
      autenticado.set(true);
      fixture.detectChanges();
    });

    it('no vuelve a pedir los datos que Google ya entregó', () => {
      expect(html.querySelector('#nombre')).toBeNull();
      expect(html.querySelector('#email')).toBeNull();
      expect(html.querySelector('.contratar__quien')?.textContent).toContain('Ana');
    });

    it('contrata sin mandar de nuevo al login', async () => {
      (html.querySelector('.contratar__form') as HTMLFormElement)
        .dispatchEvent(new Event('submit'));
      await fixture.whenStable();

      expect(contratar).toHaveBeenCalledWith('impulso');
      expect(irALogin).not.toHaveBeenCalled();
    });

    it('manda el id del pack, nunca el monto', async () => {
      (html.querySelectorAll('.pack')[2] as HTMLButtonElement).click();
      fixture.detectChanges();
      (html.querySelector('.contratar__form') as HTMLFormElement)
        .dispatchEvent(new Event('submit'));
      await fixture.whenStable();

      expect(contratar).toHaveBeenCalledWith('volumen');
    });
  });
});

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { LandingComponent } from './landing.component';

describe('LandingComponent', () => {
  let fixture: ComponentFixture<LandingComponent>;
  let html: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LandingComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(LandingComponent);
    fixture.detectChanges();
    html = fixture.nativeElement;
  });

  it('se crea correctamente', () => {
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('tiene un único h1', () => {
    expect(html.querySelectorAll('h1').length).toBe(1);
  });

  it('renderiza las secciones que enlaza la navegación', () => {
    const ids = [
      'inicio',
      'nosotros',
      'vision',
      'propuesta',
      'servicios',
      'como-trabajamos',
      'compromiso',
      'seguridad',
      'contacto',
    ];
    for (const id of ids) {
      expect(html.querySelector(`#${id}`))
        .withContext(`falta la sección #${id}`)
        .toBeTruthy();
    }
  });

  it('el hero no habla de precios', () => {
    const hero = html.querySelector('.hero__copy')?.textContent?.toLowerCase() ?? '';

    // El hero plantea la propuesta, no la tarifa: el precio se ve en /precios,
    // cuando el visitante ya sabe qué está comprando.
    for (const palabra of ['saldo', 'pago por uso', 'tarifa', 'por página', 'por minuto']) {
      expect(hero)
        .withContext(`el hero no debería mencionar "${palabra}"`)
        .not.toContain(palabra);
    }
    expect(hero).not.toMatch(/\$\s?\d/);
  });

  it('cierra el hero con la promesa de la marca', () => {
    const cierre = html.querySelector('.hero__cierre')?.textContent ?? '';

    expect(cierre).toContain('crecimiento exponencial');
  });

  it('presenta los cuatro servicios, cada uno con sus listas', () => {
    const soluciones = html.querySelectorAll('.solucion');
    expect(soluciones.length).toBe(4);

    // Ninguno puede quedar como un título sin contenido.
    soluciones.forEach((solucion, i) => {
      expect(solucion.querySelectorAll('.bloque').length)
        .withContext(`el servicio ${i + 1} no tiene bloques`)
        .toBeGreaterThan(0);
      expect(solucion.querySelectorAll('.bloque__lista li').length)
        .withContext(`el servicio ${i + 1} no tiene ítems`)
        .toBeGreaterThan(0);
    });
  });

  it('agrupa las fuentes de información en familias', () => {
    const familias = html.querySelectorAll('.fuente');

    expect(familias.length).toBe(3);
    expect(html.querySelectorAll('.fuente__lista li').length).toBe(12);
  });

  it('lista los cuatro pasos y las seis garantías', () => {
    expect(html.querySelectorAll('.paso').length).toBe(4);
    expect(html.querySelectorAll('.garantia').length).toBe(6);
  });

  it('declara la misión en el compromiso', () => {
    const mision = html.querySelector('.mision__texto')?.textContent ?? '';

    expect(mision).toContain('crecimiento');
    expect(mision.length).toBeGreaterThan(80);
  });

  describe('formulario de contacto', () => {
    const escribir = (id: string, valor: string) => {
      const campo = html.querySelector(`#${id}`) as HTMLInputElement | HTMLTextAreaElement;
      campo.value = valor;
      campo.dispatchEvent(new Event('input'));
    };

    const enviar = () => {
      html.querySelector('.contacto__form')?.dispatchEvent(new Event('submit'));
      fixture.detectChanges();
    };

    it('ofrece el correo de contacto como alternativa al formulario', () => {
      const mailto = html.querySelector('#contacto a[href^="mailto:"]');
      expect(mailto?.getAttribute('href')).toBe('mailto:contacto@simai.cl');
    });

    it('no muestra errores antes del primer envío', () => {
      expect(html.querySelectorAll('#contacto .field__error').length).toBe(0);
    });

    it('rechaza el envío vacío y mantiene el formulario a la vista', () => {
      enviar();

      expect(html.querySelectorAll('#contacto .field__error').length).toBe(3);
      expect(html.querySelector('.contacto__ok')).toBeNull();
    });

    it('confirma la recepción con datos válidos', () => {
      escribir('c-nombre', 'Ana Pérez');
      escribir('c-email', 'ana@acme.cl');
      escribir('c-mensaje', 'Revisamos cientos de documentos al mes a mano.');
      enviar();

      expect(html.querySelector('.contacto__ok')).toBeTruthy();
      expect(html.querySelector('.contacto__form')).toBeNull();
    });

    it('permite volver a escribir tras confirmar', () => {
      escribir('c-nombre', 'Ana Pérez');
      escribir('c-email', 'ana@acme.cl');
      escribir('c-mensaje', 'Revisamos cientos de documentos al mes a mano.');
      enviar();

      (html.querySelector('.contacto__ok .btn') as HTMLButtonElement).click();
      fixture.detectChanges();

      expect(html.querySelector('.contacto__form')).toBeTruthy();
      expect(html.querySelectorAll('#contacto .field__error').length).toBe(0);
    });
  });
});

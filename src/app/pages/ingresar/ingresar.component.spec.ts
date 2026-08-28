import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { AUTH, Auth } from '../../core/auth';
import { IngresarComponent } from './ingresar.component';

/** Doble de sesión: sólo nos interesa a dónde manda el botón. */
function authDoble(): Auth & { irALogin: jasmine.Spy } {
  const usuario = signal(null);
  return {
    usuario: usuario.asReadonly(),
    autenticado: signal(false).asReadonly(),
    cargarSesion: () => Promise.resolve(),
    listo: () => Promise.resolve(),
    irALogin: jasmine.createSpy('irALogin'),
    salir: () => Promise.resolve(),
    expirar: () => {},
  } as unknown as Auth & { irALogin: jasmine.Spy };
}

async function montar(params: Record<string, string> = {}) {
  const auth = authDoble();

  await TestBed.configureTestingModule({
    imports: [IngresarComponent],
    providers: [
      provideRouter([]),
      { provide: AUTH, useValue: auth },
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { queryParamMap: convertToParamMap(params) } },
      },
    ],
  }).compileComponents();

  const fixture: ComponentFixture<IngresarComponent> =
    TestBed.createComponent(IngresarComponent);
  fixture.detectChanges();

  return { fixture, auth, html: fixture.nativeElement as HTMLElement };
}

describe('IngresarComponent', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('ofrece entrar con Google', async () => {
    const { html } = await montar();
    const boton = html.querySelector('.btn--google');

    expect(boton).toBeTruthy();
    expect(boton?.textContent).toContain('Continuar con Google');
  });

  it('ya no pide correo ni contraseña', async () => {
    const { html } = await montar();

    expect(html.querySelector('input[type="password"]')).toBeNull();
    expect(html.querySelector('form')).toBeNull();
  });

  it('manda al login conservando la ruta interrumpida', async () => {
    const { html, auth } = await montar({ volver: '/panel' });
    (html.querySelector('.btn--google') as HTMLButtonElement).click();

    expect(auth.irALogin).toHaveBeenCalledWith('/panel');
  });

  it('vuelve al panel por defecto si no hay ruta pendiente', async () => {
    const { html, auth } = await montar();
    (html.querySelector('.btn--google') as HTMLButtonElement).click();

    expect(auth.irALogin).toHaveBeenCalledWith('/panel');
  });

  it('explica por qué falló el ingreso', async () => {
    const { html } = await montar({ error: 'sesion-expirada' });
    const alerta = html.querySelector('.acceso__error');

    expect(alerta?.textContent).toContain('sesión expiró');
    expect(alerta?.getAttribute('role')).toBe('alert');
  });

  it('no inventa un mensaje cuando el código de error es desconocido', async () => {
    const { html } = await montar({ error: 'algo-raro' });

    expect(html.querySelector('.acceso__error')?.textContent)
      .toContain('No pudimos completar el ingreso');
  });

  it('no muestra alerta si no hubo error', async () => {
    const { html } = await montar();
    expect(html.querySelector('.acceso__error')).toBeNull();
  });
});

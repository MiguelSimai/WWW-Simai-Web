import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AUTH, Auth } from '../../core/auth';
import { Usuario } from '../../core/modelos';
import { SiteHeaderComponent } from './site-header.component';

function authDoble(usuario: Usuario | null): Auth {
  return {
    usuario: signal(usuario).asReadonly(),
    autenticado: signal(usuario !== null).asReadonly(),
    cargarSesion: () => Promise.resolve(),
    listo: () => Promise.resolve(),
    irALogin: () => {},
    salir: () => Promise.resolve(),
    expirar: () => {},
  } as unknown as Auth;
}

describe('SiteHeaderComponent', () => {
  let fixture: ComponentFixture<SiteHeaderComponent>;
  let html: HTMLElement;

  async function montar(usuario: Usuario | null) {
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [SiteHeaderComponent],
      providers: [provideRouter([]), { provide: AUTH, useValue: authDoble(usuario) }],
    }).compileComponents();

    fixture = TestBed.createComponent(SiteHeaderComponent);
    fixture.detectChanges();
    html = fixture.nativeElement;
  }

  it('no muestra sesión a quien no ha entrado', async () => {
    await montar(null);

    expect(html.querySelector('.sesion')).toBeNull();
    expect(html.textContent).toContain('Ingresar');
  });

  it('muestra el primer nombre de quien está conectado', async () => {
    await montar({
      id: 'u-1',
      email: 'maria.jose.fernandez@acme.cl',
      nombre: 'María José Fernández',
      contratado: true,
    });

    expect(html.querySelector('.sesion__nombre')?.textContent?.trim()).toBe('María');
    expect(html.querySelector('.sesion__inicial')?.textContent?.trim()).toBe('M');
  });

  it('deja el correo completo en el title, que es lo que no se repite', async () => {
    await montar({
      id: 'u-1',
      email: 'ana.perez@acme.cl',
      nombre: 'Ana Pérez',
      contratado: true,
    });

    expect(html.querySelector('.sesion')?.getAttribute('title')).toBe('ana.perez@acme.cl');
  });

  it('cae al correo cuando no hay nombre', async () => {
    await montar({ id: 'u-1', email: 'operaciones@acme.cl', nombre: '', contratado: true });

    expect(html.querySelector('.sesion__nombre')?.textContent?.trim()).toBe('operaciones');
  });
});

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { environment } from '../../environments/environment';
import { AuthHttp } from './auth.http';

describe('AuthHttp', () => {
  let auth: AuthHttp;
  let http: HttpTestingController;

  const URL_ME = `${environment.apiUrl}/api/auth/me`;
  const URL_PROVEEDORES = `${environment.apiUrl}/api/auth/proveedores`;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [AuthHttp, provideHttpClient(), provideHttpClientTesting()],
    });

    auth = TestBed.inject(AuthHttp);
    http = TestBed.inject(HttpTestingController);
  });

  it('reconoce la sesión cuando el servidor la devuelve', async () => {
    const cargando = auth.cargarSesion();

    http.expectOne(URL_ME).flush({
      id: 'u-1',
      email: 'ana@acme.cl',
      nombre: 'Ana',
      contratado: true,
    });
    http.expectOne(URL_PROVEEDORES).flush({ proveedores: ['google'] });
    await cargando;

    expect(auth.autenticado()).toBeTrue();
    expect(auth.usuario()?.email).toBe('ana@acme.cl');
  });

  it('sigue sin sesión ante un 401, que es lo normal para un visitante', async () => {
    const cargando = auth.cargarSesion();

    http.expectOne(URL_ME).flush(
      { detail: 'Sin sesión' },
      { status: 401, statusText: 'Unauthorized' },
    );
    http.expectOne(URL_PROVEEDORES).flush({ proveedores: ['google'] });
    await cargando;

    expect(auth.autenticado()).toBeFalse();
  });

  it('ofrece los proveedores que habilita el servidor', async () => {
    const cargando = auth.cargarSesion();

    http.expectOne(URL_ME).flush(
      { detail: 'Sin sesión' },
      { status: 401, statusText: 'Unauthorized' },
    );
    http.expectOne(URL_PROVEEDORES).flush({ proveedores: ['google', 'microsoft'] });
    await cargando;

    expect(auth.proveedores()).toEqual(['google', 'microsoft']);
  });

  /**
   * Degradar a Google y no a una lista vacía: si la consulta falla, dejar la
   * pantalla de ingreso sin botones impediría entrar a quien sí podía.
   */
  it('se queda con Google si no puede consultar los proveedores', async () => {
    const cargando = auth.cargarSesion();

    http.expectOne(URL_ME).flush(
      { detail: 'Sin sesión' },
      { status: 401, statusText: 'Unauthorized' },
    );
    http.expectOne(URL_PROVEEDORES).error(new ProgressEvent('error'));
    await cargando;

    expect(auth.proveedores()).toEqual(['google']);
  });

  /**
   * Esta consulta corre antes de mostrar la primera pantalla. Si no tuviera
   * tope de tiempo, una API caída dejaría el sitio en blanco y el visitante no
   * vería ni la landing, que es contenido estático.
   */
  it('no se queda esperando para siempre si la API no responde', fakeAsync(() => {
    let termino = false;
    void auth.cargarSesion().then(() => (termino = true));

    // La petición queda abierta: el servidor nunca contesta.
    http.expectOne(URL_ME);

    tick(4000);
    expect(termino).withContext('antes del tope sigue esperando').toBeFalse();

    tick(1500);
    expect(termino).withContext('pasado el tope, resuelve y deja arrancar').toBeTrue();
    expect(auth.autenticado()).toBeFalse();
  }));

  it('limpia la sesión al expirar', () => {
    auth.expirar();

    expect(auth.autenticado()).toBeFalse();
    expect(auth.usuario()).toBeNull();
  });
});

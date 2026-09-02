import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom, timeout } from 'rxjs';
import { environment } from '../../environments/environment';
import { Auth } from './auth';
import { ProveedorAuth, Usuario } from './modelos';

/**
 * Cuánto se espera la consulta de sesión del arranque.
 *
 * Cinco segundos: suficiente para una conexión lenta, y poco para que nadie
 * se quede mirando una pantalla vacía si la API no responde.
 */
const ESPERA_SESION_MS = 5000;

/**
 * Sesión real: la sostiene una cookie httpOnly que este código no puede leer
 * —ni necesita leer—. Para saber quién eres, se lo pregunta al servidor.
 */
@Injectable()
export class AuthHttp implements Auth {
  private readonly http = inject(HttpClient);
  private readonly _usuario = signal<Usuario | null>(null);

  readonly usuario = this._usuario.asReadonly();
  readonly autenticado = computed(() => this._usuario() !== null);

  // Google por defecto: es el que siempre existió, así que si la consulta
  // falla el portal ofrece lo que con seguridad está disponible.
  private readonly _proveedores = signal<readonly ProveedorAuth[]>(['google']);
  readonly proveedores = this._proveedores.asReadonly();

  /** La consulta del arranque, para que los guards la puedan esperar. */
  private enCurso: Promise<void> | null = null;

  listo(): Promise<void> {
    return this.enCurso ?? Promise.resolve();
  }

  cargarSesion(): Promise<void> {
    // Las dos consultas van en paralelo y ninguna depende de la otra: el 401
    // rutinario de quien no ha entrado no tiene por qué dejar la pantalla de
    // ingreso sin saber con qué proveedores se puede entrar.
    this.enCurso = Promise.all([this.consultar(), this.consultarProveedores()]).then(
      () => undefined,
    );
    return this.enCurso;
  }

  private async consultarProveedores(): Promise<void> {
    try {
      const respuesta = await firstValueFrom(
        this.http
          .get<{ proveedores: readonly ProveedorAuth[] }>(
            `${environment.apiUrl}/api/auth/proveedores`,
          )
          .pipe(timeout(ESPERA_SESION_MS)),
      );
      if (respuesta.proveedores?.length) {
        this._proveedores.set(respuesta.proveedores);
      }
    } catch {
      // Se queda con el valor por defecto. Un fallo acá no debe impedir entrar.
    }
  }

  private async consultar(): Promise<void> {
    try {
      const usuario = await firstValueFrom(
        this.http
          .get<Usuario>(`${environment.apiUrl}/api/auth/me`)
          // Con tope de tiempo: esta consulta corre ANTES de mostrar la
          // primera pantalla (ver `provideAppInitializer` en app.config.ts).
          // Sin el tope, una API caída o lenta deja el sitio en blanco: el
          // visitante no ve ni la landing, que es contenido estático y no
          // necesita saber nada de la sesión.
          .pipe(timeout(ESPERA_SESION_MS)),
      );
      this._usuario.set(usuario);
    } catch {
      // Acá caen tres casos y en los tres la respuesta correcta es la misma
      // —seguir sin sesión—: el 401 de quien no ha entrado, que es lo normal;
      // un error de red; y el tope de tiempo. Quien sí tenía sesión y se topó
      // con la API lenta la recupera al navegar, porque el interceptor
      // reacciona al 401.
      this._usuario.set(null);
    }
  }

  irALogin(volver = '/panel', proveedor: ProveedorAuth = 'google'): void {
    const destino = encodeURIComponent(volver);
    window.location.href =
      `${environment.apiUrl}/api/auth/login/${proveedor}?volver=${destino}`;
  }

  async salir(): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/api/auth/logout`, {}),
      );
    } finally {
      // Aunque falle la llamada, localmente la sesión se termina.
      this._usuario.set(null);
    }
  }

  expirar(): void {
    this._usuario.set(null);
  }
}

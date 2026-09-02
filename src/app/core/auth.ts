import { InjectionToken, Signal } from '@angular/core';
import { ProveedorAuth, Usuario } from './modelos';

/**
 * Contrato de sesión que ven los componentes.
 *
 * Hay dos implementaciones: `AuthHttp` (real, contra el backend) y `AuthMock`
 * (simulada, para desarrollar sin backend). Cuál se usa lo decide el archivo
 * de entorno, y el build de producción ni siquiera compila la simulada.
 */
export interface Auth {
  readonly usuario: Signal<Usuario | null>;
  readonly autenticado: Signal<boolean>;

  /**
   * Proveedores con los que se puede entrar, según lo que el servidor tenga
   * configurado. Se resuelve en el arranque, junto con la sesión.
   */
  readonly proveedores: Signal<readonly ProveedorAuth[]>;

  /**
   * Pregunta al servidor si hay sesión. Se llama una vez, al arrancar la app,
   * **sin esperarla**: el sitio público no necesita saber de la sesión para
   * mostrarse.
   */
  cargarSesion(): Promise<void>;

  /**
   * Se resuelve cuando la consulta del arranque terminó.
   *
   * La esperan los guards de las rutas protegidas, que sí necesitan saber si
   * hay sesión antes de decidir. Si ya terminó, resuelve de inmediato.
   */
  listo(): Promise<void>;

  /** Sale del SPA hacia el proveedor de identidad. No retorna. */
  irALogin(volver?: string, proveedor?: ProveedorAuth): void;

  salir(): Promise<void>;

  /** Limpia el estado local cuando el servidor responde que la sesión murió. */
  expirar(): void;
}

export const AUTH = new InjectionToken<Auth>('AUTH');

import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Auth } from './auth';
import { Usuario } from './modelos';

const CLAVE_SESION = 'simai.sesion';

/**
 * Sesión SIMULADA, sólo para desarrollo sin backend.
 *
 * No autentica nada: `irALogin()` inventa un usuario y lo guarda en
 * `sessionStorage`. Este archivo no entra al bundle de producción — el
 * `fileReplacements` de angular.json lo deja fuera.
 */
@Injectable()
export class AuthMock implements Auth {
  private readonly router = inject(Router);
  private readonly _usuario = signal<Usuario | null>(this.leer());

  readonly usuario = this._usuario.asReadonly();
  readonly autenticado = computed(() => this._usuario() !== null);

  /** La sesión simulada se lee del navegador: nunca hay nada que esperar. */
  listo(): Promise<void> {
    return Promise.resolve();
  }

  async cargarSesion(): Promise<void> {
    this._usuario.set(this.leer());
  }

  irALogin(volver = '/panel'): void {
    const usuario: Usuario = {
      id: 'demo-0001',
      email: 'ana.perez@acme.cl',
      nombre: 'Ana Pérez',
      empresa: 'Acme',
      saldo: 48_600,
    };

    this._usuario.set(usuario);
    this.guardar(usuario);
    this.router.navigateByUrl(volver);
  }

  async salir(): Promise<void> {
    this.expirar();
  }

  expirar(): void {
    this._usuario.set(null);
    try {
      sessionStorage.removeItem(CLAVE_SESION);
    } catch {
      // El signal ya quedó en null; sin almacenamiento no hay nada más que hacer.
    }
  }

  private leer(): Usuario | null {
    // En modo privado o con cookies bloqueadas, `sessionStorage` lanza.
    try {
      const crudo = sessionStorage.getItem(CLAVE_SESION);
      return crudo ? (JSON.parse(crudo) as Usuario) : null;
    } catch {
      return null;
    }
  }

  private guardar(usuario: Usuario): void {
    try {
      sessionStorage.setItem(CLAVE_SESION, JSON.stringify(usuario));
    } catch {
      // Sin persistencia la sesión dura lo que dure la pestaña. Aceptable.
    }
  }
}

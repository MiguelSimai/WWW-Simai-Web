import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AUTH } from './auth';
import { ServicioId } from './modelos';

/** Un servicio habilitado a una cuenta, apuntando a un proceso del motor. */
export interface ProcesoCuenta {
  readonly servicio: ServicioId;
  readonly tipo_servicio: string;
  readonly proceso_codigo: string;
  readonly id_proceso: number;
  readonly plantilla_id: string | null;
  readonly plantilla: string | null;
}

export interface CuentaAdmin {
  readonly id: string;
  readonly nombre: string;
  /** RUT normalizado (`76543210-3`), o null si todavía no se registró. */
  readonly rut: string | null;
  readonly saldo: number;
  readonly usuarios: number;
  readonly solicitudes: number;
  readonly procesos: readonly ProcesoCuenta[];
}

export interface UsuarioAdmin {
  readonly id: string;
  readonly email: string;
  readonly nombre: string;
  readonly cuenta_id: string | null;
  readonly cuenta: string | null;
  readonly ultimo_acceso_en: string | null;
}

export interface PlantillaAdmin {
  readonly id: string;
  readonly servicio: string;
  readonly nombre: string;
}

/**
 * Administración de clientes.
 *
 * Sin esto, dar de alta un cliente es correr SQL: crear su cuenta, moverle los
 * usuarios y cargar `cuenta_procesos`.
 *
 * Los endpoints responden 404 a quien no administra, así que un error acá no
 * distingue "no existe" de "no tienes permiso" — y está bien que sea así.
 */
@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AUTH);
  private readonly base = `${environment.apiUrl}/api/admin`;

  readonly cuentas = signal<readonly CuentaAdmin[]>([]);
  readonly usuarios = signal<readonly UsuarioAdmin[]>([]);
  readonly plantillas = signal<readonly PlantillaAdmin[]>([]);

  /**
   * Recarga el listado y **además la sesión**.
   *
   * Hace falta cuando la operación puede haber cambiado la cuenta del propio
   * administrador —acreditarle saldo, fusionar su cuenta, moverlo de cuenta—:
   * el saldo que muestran el header y el panel viene del usuario de la sesión,
   * que se consulta una sola vez al arrancar. Sin esto hay que salir y volver
   * a entrar para ver la cifra nueva, que es exactamente lo que pasaba.
   */
  private async recargarConSesion(): Promise<void> {
    await Promise.all([this.cargar(), this.auth.cargarSesion()]);
  }

  async cargar(): Promise<void> {
    const [cuentas, usuarios, plantillas] = await Promise.all([
      firstValueFrom(this.http.get<{ cuentas: CuentaAdmin[] }>(`${this.base}/cuentas`)),
      firstValueFrom(this.http.get<{ usuarios: UsuarioAdmin[] }>(`${this.base}/usuarios`)),
      firstValueFrom(this.http.get<{ plantillas: PlantillaAdmin[] }>(`${this.base}/plantillas`)),
    ]);

    this.cuentas.set(cuentas.cuentas);
    this.usuarios.set(usuarios.usuarios);
    this.plantillas.set(plantillas.plantillas);
  }

  async crearCuenta(nombre: string, rut: string | null = null): Promise<void> {
    await firstValueFrom(this.http.post(`${this.base}/cuentas`, { nombre, rut }));
    await this.cargar();
  }

  /**
   * Fija o corrige el RUT de la cuenta, que es a quién se le factura.
   *
   * El servidor valida el dígito verificador y rechaza con 422 si no cuadra,
   * o con 409 si otra cuenta ya lo tiene.
   */
  async fijarRut(cuentaId: string, rut: string): Promise<void> {
    await firstValueFrom(this.http.post(`${this.base}/cuentas/${cuentaId}/rut`, { rut }));
    await this.cargar();
  }

  async habilitarProceso(
    cuentaId: string,
    datos: {
      servicio: string;
      tipo_servicio: string;
      proceso_codigo: string;
      id_proceso: number;
      plantilla_id: string | null;
    },
  ): Promise<void> {
    await firstValueFrom(this.http.post(`${this.base}/cuentas/${cuentaId}/procesos`, datos));
    await this.cargar();
  }

  async quitarProceso(cuentaId: string, servicio: string): Promise<void> {
    await firstValueFrom(
      this.http.delete(`${this.base}/cuentas/${cuentaId}/procesos/${servicio}`),
    );
    await this.cargar();
  }

  /**
   * Traspasa saldo, expedientes y usuarios de `origenId` a `destinoId`.
   *
   * Distinto de mover un usuario: eso deja su saldo y su historial en la
   * cuenta que abandona.
   */
  async fusionar(destinoId: string, origenId: string): Promise<void> {
    await firstValueFrom(
      this.http.post(`${this.base}/cuentas/${destinoId}/fusionar`, { origen_id: origenId }),
    );
    await this.recargarConSesion();
  }

  /**
   * Acredita saldo a mano, contra un pago recibido fuera del portal.
   *
   * Un monto negativo corrige uno anterior. La referencia es lo que permite
   * reconciliar después con la cartola del banco, así que va siempre.
   */
  async cargarSaldo(cuentaId: string, monto: number, referencia: string): Promise<void> {
    await firstValueFrom(
      this.http.post(`${this.base}/cuentas/${cuentaId}/saldo`, { monto, referencia }),
    );
    await this.recargarConSesion();
  }

  async moverUsuario(usuarioId: string, cuentaId: string): Promise<void> {
    await firstValueFrom(
      this.http.post(`${this.base}/usuarios/${usuarioId}/cuenta`, { cuenta_id: cuentaId }),
    );
    await this.recargarConSesion();
  }
}

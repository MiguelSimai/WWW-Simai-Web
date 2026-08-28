import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
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
  private readonly base = `${environment.apiUrl}/api/admin`;

  readonly cuentas = signal<readonly CuentaAdmin[]>([]);
  readonly usuarios = signal<readonly UsuarioAdmin[]>([]);
  readonly plantillas = signal<readonly PlantillaAdmin[]>([]);

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

  async crearCuenta(nombre: string): Promise<void> {
    await firstValueFrom(this.http.post(`${this.base}/cuentas`, { nombre }));
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
    await this.cargar();
  }

  async moverUsuario(usuarioId: string, cuentaId: string): Promise<void> {
    await firstValueFrom(
      this.http.post(`${this.base}/usuarios/${usuarioId}/cuenta`, { cuenta_id: cuentaId }),
    );
    await this.cargar();
  }
}

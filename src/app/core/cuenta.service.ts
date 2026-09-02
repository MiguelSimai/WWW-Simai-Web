import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';

/** A dónde transferir. Lo entrega el servidor; no vive en el front. */
export interface DatosTransferencia {
  readonly configurada: boolean;
  readonly banco?: string;
  readonly tipo?: string;
  readonly numero?: string;
  readonly rut?: string;
  readonly titular?: string;
  readonly email?: string;
}

/** Una transferencia declarada por el cliente, a la espera de verificación. */
export interface Recarga {
  readonly id: string;
  readonly pack_id: string | null;
  readonly monto_declarado: number;
  readonly referencia: string;
  readonly estado: 'pendiente' | 'acreditada' | 'rechazada';
  readonly monto_acreditado: number | null;
  readonly nota: string | null;
  readonly creada_en: string;
  readonly resuelta_en: string | null;
}

/**
 * Recarga de saldo por transferencia.
 *
 * El cliente transfiere a la cuenta corriente y declara acá lo que transfirió.
 * **Declarar no acredita nada**: el saldo se mueve cuando alguien verifica la
 * transferencia en la cartola, desde la administración. Este servicio ocupa el
 * lugar que tendría una pasarela de pago, con la confirmación hecha a mano.
 *
 * El monto de los packs vive en el servidor: el cliente elige *qué* pack,
 * nunca *cuánto* vale.
 */
@Injectable({ providedIn: 'root' })
export class CuentaService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/api/cuenta`;

  private readonly _transferencia = signal<DatosTransferencia | null>(null);
  readonly transferencia = this._transferencia.asReadonly();

  private readonly _recargas = signal<readonly Recarga[]>([]);
  readonly recargas = this._recargas.asReadonly();

  /**
   * Pide los datos bancarios. Requiere sesión, así que se llama al entrar a la
   * pantalla y no al arrancar la app.
   */
  async cargarTransferencia(): Promise<void> {
    try {
      const datos = await firstValueFrom(
        this.http.get<DatosTransferencia>(`${this.base}/transferencia`),
      );
      this._transferencia.set(datos);
    } catch {
      // Sin datos la pantalla ofrece contactar, que es mejor que mostrar una
      // cuenta bancaria a medias.
      this._transferencia.set({ configurada: false });
    }
  }

  async cargarRecargas(): Promise<void> {
    const respuesta = await firstValueFrom(
      this.http.get<{ recargas: Recarga[] }>(`${this.base}/recargas`),
    );
    this._recargas.set(respuesta.recargas);
  }

  /**
   * Declara una transferencia ya hecha. No mueve saldo.
   *
   * `montoDeclarado` es lo que el cliente dice haber transferido; lo que se
   * acredite sale de la cartola.
   */
  async declarar(
    packId: string | null,
    montoDeclarado: number,
    referencia: string,
  ): Promise<void> {
    await firstValueFrom(
      this.http.post(`${this.base}/recargas`, {
        pack_id: packId,
        monto_declarado: montoDeclarado,
        referencia,
      }),
    );
    await this.cargarRecargas();
  }
}

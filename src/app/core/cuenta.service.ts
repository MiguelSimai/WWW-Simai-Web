import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AUTH } from './auth';

/**
 * Operaciones sobre la cuenta del usuario que ya entró.
 *
 * El pack se identifica por su id: el monto lo pone el servidor. Mandar el
 * monto desde el navegador dejaría que cualquiera se acredite lo que quiera
 * editando la petición.
 */
@Injectable({ providedIn: 'root' })
export class CuentaService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AUTH);

  async contratar(packId: string): Promise<void> {
    await firstValueFrom(
      this.http.post(`${environment.apiUrl}/api/cuenta/contratar/${packId}`, {}),
    );

    // El saldo y el estado de contratación viven en el usuario de la sesión.
    await this.auth.cargarSesion();
  }
}

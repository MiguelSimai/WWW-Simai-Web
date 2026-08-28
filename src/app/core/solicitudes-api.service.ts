import { HttpClient, HttpEvent } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { ServicioId } from './modelos';

/**
 * ÚNICO punto de contacto con la API de solicitudes.
 *
 *   POST {apiUrl}/api/solicitudes
 *   Content-Type: multipart/form-data
 *     archivo         un campo por documento del expediente
 *     servicio        'transcripcion' | 'documentos' | 'conversaciones' | ...
 *     numero_cliente  número del expediente (nombre de la carpeta), opcional
 *
 *   201 →  { "codigo": "SOL-10493", "estado": "procesando" }
 *
 * Un expediente por petición, con todos sus documentos dentro: cincuenta
 * carpetas de cuatro archivos son cincuenta subidas, no doscientas. Y el saldo
 * se valida por expediente completo, así que no puede pasar que se acepten dos
 * documentos y el tercero se rechace por saldo.
 */
export interface RespuestaSolicitud {
  readonly codigo: string;
  readonly estado: string;
}

@Injectable({ providedIn: 'root' })
export class SolicitudesApi {
  private readonly http = inject(HttpClient);

  /**
   * Sube un expediente. Emite eventos de progreso, así que la pantalla puede
   * mostrar la barra sin saber nada de HTTP.
   *
   * `numeroCliente` es el nombre de la carpeta que subió el cliente. En null
   * cuando eligió archivos sueltos: el backend usa entonces el código de la
   * solicitud como referencia.
   */
  enviar(
    archivos: readonly File[],
    servicio: ServicioId,
    numeroCliente: string | null,
  ): Observable<HttpEvent<RespuestaSolicitud>> {
    const datos = new FormData();
    for (const archivo of archivos) {
      datos.append('archivo', archivo, archivo.name);
    }
    datos.append('servicio', servicio);
    if (numeroCliente) {
      datos.append('numero_cliente', numeroCliente);
    }

    return this.http.post<RespuestaSolicitud>(
      `${environment.apiUrl}/api/solicitudes`,
      datos,
      { reportProgress: true, observe: 'events' },
    );
  }
}

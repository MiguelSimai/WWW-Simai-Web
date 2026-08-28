import { Type } from '@angular/core';
import { Auth } from '../app/core/auth';
import { AuthHttp } from '../app/core/auth.http';

/**
 * Entorno POR DEFECTO = producción.
 *
 * Es deliberado que el valor seguro sea el que se usa si nadie configura
 * nada: si el reemplazo de archivo fallara, la app intenta autenticar de
 * verdad y falla ruidosamente, en vez de dejar entrar a cualquiera en
 * silencio.
 */
export const environment = {
  produccion: true,
  apiUrl: 'https://api.simai.cl',
  proveedorAuth: AuthHttp as Type<Auth>,
  authSimulada: false,
};

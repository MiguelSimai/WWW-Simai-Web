import { Type } from '@angular/core';
import { Auth } from '../app/core/auth';
import { AuthHttp } from '../app/core/auth.http';

/**
 * Entorno de DESARROLLO. Reemplaza a environment.ts vía `fileReplacements`.
 *
 * Autentica de verdad contra el backend local (Google + Postgres). Para
 * trabajar en el portal sin levantar el backend, cambia `AuthHttp` por
 * `AuthMock` —de `./core/auth.mock`— y vuelve a arrancar `npm start`.
 */
export const environment = {
  produccion: false,
  apiUrl: 'http://localhost:8000',
  proveedorAuth: AuthHttp as Type<Auth>,
  authSimulada: false,
};

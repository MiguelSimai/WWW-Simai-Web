import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AUTH } from './auth';

/**
 * Deja pasar sólo con sesión iniciada. Guarda la ruta pedida en `volver`
 * para retomarla después de entrar.
 *
 * Espera a que termine la consulta de sesión del arranque: el sitio se muestra
 * sin esperarla (ver `provideAppInitializer` en app.config.ts), así que acá
 * puede no estar resuelta todavía. Sin esta espera, entrar directo a /panel
 * rebotaría al login aunque hubiera sesión.
 *
 * Es una comodidad de navegación, no un control de seguridad: la autorización
 * real se valida en el servidor, en cada petición.
 */
export const sesionGuard: CanActivateFn = async (_ruta, estado) => {
  const auth = inject(AUTH);
  const router = inject(Router);

  await auth.listo();

  return (
    auth.autenticado() ||
    router.createUrlTree(['/ingresar'], { queryParams: { volver: estado.url } })
  );
};

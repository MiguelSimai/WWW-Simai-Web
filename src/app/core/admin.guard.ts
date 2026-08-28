import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AUTH } from './auth';

/**
 * Deja pasar sólo a quien administra.
 *
 * Como el guard de sesión, es una comodidad de navegación: quien fuerce la URL
 * verá la pantalla vacía, porque el backend responde 404 a todas sus llamadas.
 * La autorización real está allá.
 */
export const adminGuard: CanActivateFn = async () => {
  const auth = inject(AUTH);
  const router = inject(Router);

  // Como el guard de sesión: la consulta del arranque puede no haber
  // terminado, y sin esperarla se rebotaría al home teniendo permiso.
  await auth.listo();

  return auth.usuario()?.esAdmin === true || router.createUrlTree(['/']);
};

import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { environment } from '../../environments/environment';
import { AUTH } from './auth';

/**
 * Adjunta la cookie de sesión a las llamadas al backend y reacciona cuando
 * el servidor dice que la sesión ya no vale.
 *
 * `withCredentials` es imprescindible: sin él el navegador no envía cookies
 * a otro origen, y el backend vería todas las peticiones como anónimas.
 */
export const apiInterceptor: HttpInterceptorFn = (req, next) => {
  // inject() sólo vale en el cuerpo del interceptor, nunca dentro del
  // callback de catchError: para entonces ya no hay contexto de inyección.
  const auth = inject(AUTH);
  const router = inject(Router);

  const esApi = req.url.startsWith(environment.apiUrl);
  const peticion = esApi ? req.clone({ withCredentials: true }) : req;

  return next(peticion).pipe(
    catchError((error: HttpErrorResponse) => {
      // `/me` responde 401 de forma rutinaria para quien no ha entrado:
      // eso no es una sesión caída, es el estado normal de un visitante.
      const esConsultaDeSesion = req.url.endsWith('/api/auth/me');

      if (esApi && error.status === 401 && !esConsultaDeSesion) {
        const volver = router.url;
        auth.expirar();
        router.navigate(['/ingresar'], {
          queryParams: { volver, error: 'sesion-expirada' },
        });
      }

      return throwError(() => error);
    }),
  );
};

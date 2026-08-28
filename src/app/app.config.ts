import { registerLocaleData } from '@angular/common';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import localeEsCl from '@angular/common/locales/es-CL';
import {
  ApplicationConfig,
  LOCALE_ID,
  inject,
  provideAppInitializer,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideRouter, withInMemoryScrolling } from '@angular/router';

import { environment } from '../environments/environment';
import { routes } from './app.routes';
import { AUTH } from './core/auth';
import { apiInterceptor } from './core/api.interceptor';

// Fechas y montos en formato chileno: "14 ago 2026", "$4.480".
registerLocaleData(localeEsCl);

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(
      routes,
      // Las anclas de la landing se navegan desde otras rutas, así que el
      // router debe encargarse del scroll en vez del salto nativo.
      withInMemoryScrolling({
        anchorScrolling: 'enabled',
        scrollPositionRestoration: 'enabled',
      }),
    ),
    provideHttpClient(withInterceptors([apiInterceptor])),

    // Cuál implementación de sesión se usa lo decide el entorno. El build de
    // producción no incluye siquiera el código de la simulada.
    { provide: AUTH, useClass: environment.proveedorAuth },

    // Se dispara la consulta de sesión y NO se espera: devolver la promesa
    // acá bloquearía el primer render, y una API lenta dejaría el sitio en
    // blanco. La landing es contenido estático y no necesita saber de la
    // sesión; los guards de /panel y /admin sí la esperan, vía `listo()`.
    provideAppInitializer(() => {
      void inject(AUTH).cargarSesion();
    }),

    { provide: LOCALE_ID, useValue: 'es-CL' },
  ],
};

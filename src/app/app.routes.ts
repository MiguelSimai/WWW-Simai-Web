import { Routes } from '@angular/router';
import { adminGuard } from './core/admin.guard';
import { sesionGuard } from './core/sesion.guard';

export const routes: Routes = [
  {
    path: '',
    title: 'SimAI — Inteligencia artificial aplicada, pago por uso',
    loadComponent: () =>
      import('./pages/landing/landing.component').then((m) => m.LandingComponent),
  },
  {
    path: 'precios',
    title: 'Precios — SimAI',
    loadComponent: () =>
      import('./pages/precios/precios.component').then((m) => m.PreciosComponent),
  },
  {
    path: 'ingresar',
    title: 'Ingresar — SimAI',
    loadComponent: () =>
      import('./pages/ingresar/ingresar.component').then((m) => m.IngresarComponent),
  },
  {
    path: 'enviar',
    title: 'Enviar archivos — SimAI',
    canActivate: [sesionGuard],
    loadComponent: () => import('./pages/enviar/enviar.component').then((m) => m.EnviarComponent),
  },
  {
    path: 'panel',
    title: 'Mis solicitudes — SimAI',
    canActivate: [sesionGuard],
    loadComponent: () => import('./pages/panel/panel.component').then((m) => m.PanelComponent),
  },
  {
    path: 'admin',
    title: 'Administración — SimAI',
    canActivate: [adminGuard],
    loadComponent: () => import('./pages/admin/admin.component').then((m) => m.AdminComponent),
  },
  // Cualquier ruta desconocida vuelve al home. Cuando exista el 404 propio,
  // reemplazar por su componente.
  { path: '**', redirectTo: '' },
];

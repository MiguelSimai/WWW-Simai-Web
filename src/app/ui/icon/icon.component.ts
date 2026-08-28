import { Component, input } from '@angular/core';

export type IconName =
  | 'transcripcion'
  | 'documento'
  | 'audio'
  | 'automatizacion'
  | 'extraer'
  | 'api'
  | 'evidencia'
  | 'rayo'
  | 'reloj'
  | 'grafico'
  | 'pago'
  | 'escudo'
  | 'nube'
  | 'usuario'
  | 'correo'
  | 'lugar';

/**
 * Íconos de trazo, 24×24, heredan `currentColor`.
 * Decorativos por defecto: el significado lo aporta el texto que acompañan.
 */
@Component({
  selector: 'app-icon',
  template: `
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.7"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false">
      @switch (name()) {
        @case ('transcripcion') {
          <rect x="9" y="2.5" width="6" height="10" rx="3" />
          <path d="M5.5 11a6.5 6.5 0 0 0 13 0" />
          <path d="M12 17.5v3" />
          <path d="M7 21h10" />
        }
        @case ('documento') {
          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
          <path d="M14 3v5h5M9 12h6M9 16h4" />
        }
        @case ('audio') {
          <path d="M3 12h1.5" />
          <path d="M7.5 8v8" />
          <path d="M11 5v14" />
          <path d="M14.5 9v6" />
          <path d="M18 7v10" />
          <path d="M21.5 11v2" />
        }
        @case ('automatizacion') {
          <circle cx="12" cy="12" r="3" />
          <path
            d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.3a2 2 0 1 1-4 0v-.2a1.6 1.6 0 0 0-2.8-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.5 15H3a2 2 0 1 1 0-4h.2A1.6 1.6 0 0 0 4.3 8.2l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 9.9 4.4V4a2 2 0 1 1 4 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.3a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.2.9Z" />
        }
        @case ('extraer') {
          <path d="M4 5.5h16" />
          <path d="M4 10h9" />
          <path d="M4 14.5h5" />
          <path d="M14 14.5h6v6h-6z" />
          <path d="m16 17.5 1.2 1.2 2.3-2.4" />
        }
        @case ('api') {
          <path d="m8.5 8-4 4 4 4" />
          <path d="m15.5 8 4 4-4 4" />
          <path d="m13.5 5-3 14" />
        }
        @case ('evidencia') {
          <path d="M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
          <path d="M9 8h4M9 12h6" />
          <path d="m9 16 1.6 1.6L14 14" />
        }
        @case ('rayo') {
          <path d="M13 2 4.5 13.5H11l-.5 8.5L19 10.5h-6.5L13 2Z" />
        }
        @case ('reloj') {
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3.5 2" />
        }
        @case ('grafico') {
          <path d="M4 20V4" />
          <path d="M4 20h16" />
          <path d="M8 20v-6" />
          <path d="M13 20V9" />
          <path d="M18 20v-9" />
        }
        @case ('pago') {
          <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
          <path d="M2.5 10h19" />
          <path d="M6.5 14.5h3" />
        }
        @case ('escudo') {
          <path d="M12 3 5 6v6c0 4.4 3 8.3 7 9 4-.7 7-4.6 7-9V6l-7-3Z" />
          <path d="m9 12 2 2 4-4" />
        }
        @case ('nube') {
          <path d="M7 18h10.5a3.5 3.5 0 0 0 .3-7 5.5 5.5 0 0 0-10.6-1.3A4.2 4.2 0 0 0 7 18Z" />
        }
        @case ('usuario') {
          <circle cx="12" cy="8" r="4" />
          <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
        }
        @case ('correo') {
          <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
          <path d="m3.5 7 8.5 6 8.5-6" />
        }
        @case ('lugar') {
          <path d="M19 10.5c0 5-7 10.5-7 10.5S5 15.5 5 10.5a7 7 0 1 1 14 0Z" />
          <circle cx="12" cy="10.5" r="2.5" />
        }
      }
    </svg>
  `,
  styles: `
    :host {
      display: inline-grid;
      place-items: center;
    }

    svg {
      width: 100%;
      height: 100%;
    }
  `,
})
export class IconComponent {
  readonly name = input.required<IconName>();
}

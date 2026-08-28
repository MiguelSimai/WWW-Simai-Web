import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { AUTH } from '../../core/auth';
import { LogoComponent } from '../../ui/logo/logo.component';

interface NavLink {
  readonly label: string;
  readonly ruta: string;
  /** Ancla dentro de la landing, cuando corresponde. */
  readonly fragmento?: string;
}

@Component({
  selector: 'app-site-header',
  imports: [RouterLink, RouterLinkActive, LogoComponent],
  templateUrl: './site-header.component.html',
  styleUrl: './site-header.component.scss',
})
export class SiteHeaderComponent {
  private readonly auth = inject(AUTH);
  private readonly router = inject(Router);

  protected readonly usuario = this.auth.usuario;
  protected readonly autenticado = this.auth.autenticado;

  /**
   * Sólo el primer nombre: en la barra no cabe "María José Fernández Soto", y
   * el correo completo va en el `title` para desambiguar.
   */
  protected readonly nombreCorto = computed(() => {
    const usuario = this.usuario();
    if (!usuario) {
      return '';
    }
    const nombre = usuario.nombre?.trim();
    // Sin nombre, la parte del correo antes de la arroba identifica igual.
    return nombre ? nombre.split(/\s+/)[0] : usuario.email.split('@')[0];
  });

  protected readonly inicial = computed(() => this.nombreCorto().charAt(0).toUpperCase());

  /** El acceso a la administración sólo se muestra a quien administra. */
  protected readonly esAdmin = computed(() => this.usuario()?.esAdmin === true);

  protected readonly links: readonly NavLink[] = [
    { label: 'Nosotros', ruta: '/', fragmento: 'nosotros' },
    { label: 'Servicios', ruta: '/', fragmento: 'servicios' },
    { label: 'Cómo trabajamos', ruta: '/', fragmento: 'como-trabajamos' },
    { label: 'Precios', ruta: '/precios' },
    { label: 'Contacto', ruta: '/', fragmento: 'contacto' },
  ];

  /** Menú desplegable en viewport angosto. */
  protected readonly menuOpen = signal(false);

  protected toggleMenu(): void {
    this.menuOpen.update((open) => !open);
  }

  protected closeMenu(): void {
    this.menuOpen.set(false);
  }

  protected async salir(): Promise<void> {
    this.closeMenu();
    await this.auth.salir();
    this.router.navigate(['/']);
  }

  /** Cerrar con Escape es lo que espera cualquier usuario de teclado. */
  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    this.closeMenu();
  }
}

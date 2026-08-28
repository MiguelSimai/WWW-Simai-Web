import { Component, computed, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { environment } from '../../../environments/environment';
import { AUTH } from '../../core/auth';
import { LogoComponent } from '../../ui/logo/logo.component';

const MENSAJES: Readonly<Record<string, string>> = {
  'sesion-expirada': 'Tu sesión expiró por seguridad. Vuelve a entrar para continuar.',
  oauth: 'No pudimos completar el ingreso con Google. Inténtalo otra vez.',
  incompleto: 'Google no entregó los datos necesarios para identificarte.',
  'correo-no-verificado': 'Tu correo no está verificado en Google, así que no podemos enlazarlo.',
};

@Component({
  selector: 'app-ingresar',
  imports: [RouterLink, LogoComponent],
  templateUrl: './ingresar.component.html',
  styleUrl: './ingresar.component.scss',
})
export class IngresarComponent {
  private readonly auth = inject(AUTH);
  private readonly ruta = inject(ActivatedRoute);

  protected readonly simulada = environment.authSimulada;

  /** Ruta que el guard interrumpió, para retomarla tras entrar. */
  private readonly volver = this.ruta.snapshot.queryParamMap.get('volver') ?? '/panel';

  /** El backend devuelve el motivo en `?error=` cuando el ingreso falla. */
  protected readonly error = computed(() => {
    const codigo = this.ruta.snapshot.queryParamMap.get('error');
    return codigo ? (MENSAJES[codigo] ?? 'No pudimos completar el ingreso.') : null;
  });

  protected entrar(): void {
    this.auth.irALogin(this.volver);
  }
}

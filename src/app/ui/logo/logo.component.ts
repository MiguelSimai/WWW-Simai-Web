import { Component, computed, input } from '@angular/core';

/** Cómo se compone el logotipo. */
export type VarianteLogo = 'apilado' | 'horizontal' | 'completo' | 'simbolo';

/**
 * Logotipo de SimAI.
 *
 *   apilado     símbolo arriba, nombre y lema debajo   como el original
 *   horizontal  símbolo y nombre en una línea          barras muy bajas
 *   completo    la imagen original tal cual            footer y landing
 *   simbolo     sólo el símbolo                        espacios estrechos
 *
 * En `apilado` y `horizontal` el nombre y el lema van como **texto**, no como
 * imagen. El archivo original apila los tres elementos, y al reducirlo a la
 * altura de una barra de navegación el nombre queda en unos 12px y el lema en
 * 3: ilegibles. Con texto se leen nítidos a cualquier tamaño, respetan el zoom
 * del navegador y pesan cero.
 *
 * Los colores siguen al original: "Sim" en el azul de la marca, "AI" en verde.
 *
 * La imagen es decorativa (`alt=""`): el nombre accesible lo aporta el enlace
 * que la envuelve, o el texto de al lado. Si usas `simbolo` fuera de un enlace
 * etiquetado, etiqueta el contenedor.
 */
@Component({
  selector: 'app-logo',
  template: `
    @if (variante() === 'completo') {
      <img class="logo__img" src="logo-simai.png" alt="" [style.height.px]="alto()" />
    } @else {
      <span class="logo" [class.logo--apilado]="variante() === 'apilado'">
        <img
          class="logo__img"
          src="logo-simai-simbolo.png"
          alt=""
          [style.height.px]="altoSimbolo()" />

        @if (variante() !== 'simbolo') {
          <span class="logo__texto">
            <span class="logo__nombre" [style.font-size.px]="tamanoNombre()">
              Sim<span class="logo__ai">AI</span>
            </span>

            @if (conLema()) {
              <!-- Dos líneas, como en el logotipo original. -->
              <span class="logo__lema" [style.font-size.px]="tamanoLema()">
                <span>Inteligencia artificial · Resultados reales</span>
                <span class="logo__lema-cierre">Personas siempre</span>
              </span>
            }
          </span>
        }
      </span>
    }
  `,
  styles: `
    :host {
      display: inline-block;
      line-height: 0;
    }

    .logo {
      display: inline-flex;
      align-items: center;
      gap: 0.45em;
    }

    /* Apilado: símbolo arriba, texto debajo, todo centrado. */
    .logo--apilado {
      flex-direction: column;
      gap: 0.28em;
      text-align: center;
    }

    .logo__img {
      width: auto;
      display: block;
      flex: none;
    }

    .logo__texto {
      display: grid;
      gap: 0.18em;
    }

    .logo__nombre {
      font-weight: 800;
      letter-spacing: -0.035em;
      line-height: 1;
      /* El azul de la marca, no el color del texto que lo rodea: el logotipo
         se lee igual sobre cualquier superficie clara. */
      color: var(--c-brand);
      white-space: nowrap;
    }

    .logo__ai {
      color: var(--c-accent);
    }

    /* El lema, en versalitas espaciadas como en el original. */
    .logo__lema {
      display: grid;
      gap: 0.1em;
      font-weight: 600;
      letter-spacing: 0.04em;
      line-height: 1.15;
      text-transform: uppercase;
      color: var(--c-brand);
      white-space: nowrap;
    }

    /* La segunda línea va entre guiones largos, como el logotipo. */
    .logo__lema-cierre::before,
    .logo__lema-cierre::after {
      content: '—';
      margin-inline: 0.4em;
      color: var(--c-accent);
    }

    /* En pantallas angostas el lema no cabe y partirlo descuadraría la barra:
       se oculta y queda el nombre, que es lo que identifica el sitio. */
    @media (max-width: 720px) {
      .logo__lema {
        display: none;
      }
    }
  `,
})
export class LogoComponent {
  /** Cómo se compone. */
  readonly variante = input<VarianteLogo>('apilado');

  /**
   * Alto de referencia en píxeles: el del símbolo en las variantes con texto,
   * y el de la imagen completa en `completo`.
   */
  readonly alto = input(40);

  /** Muestra el lema. No aplica a `simbolo` ni a `completo`. */
  readonly conLema = input(false);

  /**
   * Apilado, el símbolo se achica un poco: sumado al nombre y al lema, a
   * tamaño completo el logotipo crecería demasiado en alto.
   */
  protected readonly altoSimbolo = computed(() =>
    this.variante() === 'apilado' ? Math.round(this.alto() * 0.86) : this.alto(),
  );

  /**
   * El nombre, más chico que el símbolo: si igualara su altura, las mayúsculas
   * dominarían sobre el dibujo. Con lema baja un poco más.
   */
  protected readonly tamanoNombre = computed(() =>
    Math.round(this.alto() * (this.conLema() ? 0.52 : 0.62)),
  );

  /** El lema es una línea de apoyo: bastante más chico que el nombre. */
  protected readonly tamanoLema = computed(() => Math.max(8, Math.round(this.alto() * 0.19)));
}

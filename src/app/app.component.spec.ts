import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AppComponent } from './app.component';
import { routes } from './app.routes';
import { AUTH } from './core/auth';
import { AuthMock } from './core/auth.mock';

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter(routes), { provide: AUTH, useClass: AuthMock }],
    }).compileComponents();
  });

  it('se crea correctamente', () => {
    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('monta el header, el main y el footer', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const html: HTMLElement = fixture.nativeElement;
    expect(html.querySelector('app-site-header')).toBeTruthy();
    expect(html.querySelector('main#contenido')).toBeTruthy();
    expect(html.querySelector('app-site-footer')).toBeTruthy();
  });

  it('expone un enlace para saltar al contenido', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const skip = fixture.nativeElement.querySelector('a.skip-link') as HTMLAnchorElement | null;
    expect(skip).toBeTruthy();
    expect(skip?.getAttribute('href')).toBe('#contenido');
  });
});

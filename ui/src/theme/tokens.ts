/**
 * Design tokens, transcribed from docs/tasks/UI_tokens.md (D-794). Values marked "derived" there were
 * chosen by the supervisor; nothing here is invented. Exposed as CSS variables `--sf-<name>` per
 * colour scheme (theme.ts).
 */

export const colorTokens = {
  bg: ['#0A0E16', '#F4F6FA'],
  'bg-sidebar': ['#0E131D', '#FFFFFF'],
  surface: ['#111826', '#FFFFFF'],
  'surface-2': ['#121A28', '#F1F4F9'],
  'surface-3': ['#0D1420', '#F6F8FC'],
  'surface-sunken': ['#0B111B', '#F3F5F9'],
  'surface-hover': ['#1A2232', '#E8ECF2'],
  'surface-alt': ['#1B2638', '#E9EDF3'],
  'nav-active-bg': ['#16202F', '#E6F4F1'],
  border: ['#1C2536', '#E3E8F0'],
  'border-sidebar': ['#1B2332', '#E3E8F0'],
  'border-panel': ['#1E2839', '#DDE3EC'],
  'border-strong': ['#243047', '#D5DCE7'],
  'border-strong-2': ['#222D40', '#D5DCE7'],
  'border-input': ['#2E3B52', '#CBD5E3'],
  track: ['#2A3547', '#C9D1DD'],
  text: ['#E6EAF2', '#141A26'],
  'text-strong': ['#FFFFFF', '#141A26'],
  'text-secondary': ['#B6BFD0', '#3E4859'],
  'text-body-2': ['#C7D0DF', '#2F3848'],
  'text-tertiary': ['#A3ADBF', '#4F5B6E'],
  'text-subtle': ['#9AA4B8', '#566275'],
  'text-muted': ['#8E99AE', '#5F6B80'],
  'text-faint': ['#7D889C', '#6A7588'],
  'text-disabled': ['#4B5568', '#4B5568'],
  link: ['#7FB2FF', '#1D5FD0'],
  'link-hover': ['#A9CBFF', '#1D4ED8'],
  accent: ['#2DD4BF', '#2DD4BF'],
  'on-accent': ['#04211D', '#04211D'],
  'accent-fg': ['#7DEBD7', '#0F766E'],
  'accent-fg-2': ['#9FE8D8', '#0F766E'],
  'accent-bg': ['#0F3A33', '#DDF5F0'],
  blue: ['#5B8DEF', '#5B8DEF'],
  'blue-fg': ['#A9CBFF', '#1D4ED8'],
  'blue-bg': ['#16233A', '#E4ECFB'],
  'status-running': ['#7DB2FF', '#1D5FD0'],
  amber: ['#F5A524', '#F5A524'],
  'amber-fg': ['#F6C26B', '#9A5B00'],
  'amber-fg-2': ['#F6D29B', '#7A4700'],
  'amber-bg': ['#3A2A0E', '#FCEFD9'],
  'amber-bg-2': ['#2A1E0B', '#FFF4E0'],
  'amber-border': ['#5A3F12', '#F0D29A'],
  'amber-mid': ['#8A6420', '#D9A441'],
  violet: ['#C4A5FF', '#6D28D9'],
  'violet-strong': ['#D9CBFF', '#5B21B6'],
  'violet-bg': ['#2A1F45', '#EDE7FB'],
  'violet-bg-2': ['#1A1430', '#F1ECFC'],
  'violet-border': ['#3A2C63', '#D8CCF6'],
  danger: ['#FF8A7A', '#D92D20'],
  'danger-fg': ['#FF9A8A', '#B42318'],
  'danger-bg': ['#2A1616', '#FDECEA'],
  waiting: ['#4B5568', '#9AA4B8'],
  'selected-card-bg': ['#132033', '#E4ECFB'],
} as const satisfies Record<string, readonly [dark: string, light: string]>;

export type ColorToken = keyof typeof colorTokens;
export type Scheme = 'dark' | 'light';

export function tokenValue(name: ColorToken, scheme: Scheme): string {
  return colorTokens[name][scheme === 'dark' ? 0 : 1];
}

/** `var(--sf-<name>)` */
export function v(name: ColorToken): string {
  return `var(--sf-${name})`;
}

export const fonts = {
  sans: 'Manrope, system-ui, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, monospace',
};

/** Type sizes (px). */
export const fontSize = { caption: 11, small: 12, secondary: 13, body: 14, section: 16, title: 26 };

/** Radii (px). */
export const radius = { dot: 3, bar: 6, sm: 8, control: 10, panel: 12, card: 16, pill: 999 };

export const layout = { sidebar: 248, pagePadY: 26, pagePadX: 32, cardPad: 20, gap: 16 };

/** Chart series order (UI_tokens.md, chart palette). */
export function chartPalette(scheme: Scheme): string[] {
  return (['accent', 'blue', 'violet', 'amber', 'danger', 'blue-fg', 'accent-fg'] as const).map(
    (t) => tokenValue(t, scheme),
  );
}

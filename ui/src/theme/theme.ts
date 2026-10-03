/** The Mantine theme and the CSS variables of both schemes, from tokens.ts (UI_tokens.md, D-785). */
import {
  colorsTuple,
  createTheme,
  localStorageColorSchemeManager,
  type CSSVariablesResolver,
} from '@mantine/core';
import { colorTokens, fonts, radius, type ColorToken } from './tokens';

export const colorSchemeManager = localStorageColorSchemeManager({ key: 'sfac-color-scheme' });

export const theme = createTheme({
  fontFamily: fonts.sans,
  fontFamilyMonospace: fonts.mono,
  headings: { fontFamily: fonts.sans, fontWeight: '800' },
  primaryColor: 'sfaccent',
  primaryShade: 6,
  colors: { sfaccent: colorsTuple(colorTokens.accent[0]) },
  fontSizes: { xs: '11px', sm: '12px', md: '14px', lg: '16px', xl: '26px' },
  radius: {
    xs: `${radius.bar}px`,
    sm: `${radius.sm}px`,
    md: `${radius.control}px`,
    lg: `${radius.panel}px`,
    xl: `${radius.card}px`,
  },
  defaultRadius: 'md',
  components: {
    Card: { defaultProps: { radius: 'xl', padding: 20, withBorder: true } },
    Badge: { defaultProps: { radius: 'xl' } },
    Tooltip: { defaultProps: { withArrow: true } },
  },
});

function schemeVars(i: 0 | 1): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [name, values] of Object.entries(colorTokens)) {
    out[`--sf-${name}`] = values[i];
  }
  const t = (n: ColorToken) => colorTokens[n][i];
  // Mantine's own variables, so its components follow the tokens.
  out['--mantine-color-body'] = t('bg');
  out['--mantine-color-text'] = t('text');
  out['--mantine-color-dimmed'] = t('text-muted');
  out['--mantine-color-placeholder'] = t('text-faint');
  out['--mantine-color-anchor'] = t('link');
  out['--mantine-color-default'] = t('surface-3');
  out['--mantine-color-default-hover'] = t('surface-hover');
  out['--mantine-color-default-color'] = t('text');
  out['--mantine-color-default-border'] = t('border-input');
  out['--mantine-color-sfaccent-filled'] = t('accent');
  out['--mantine-color-sfaccent-text'] = t('accent-fg');
  out['--mantine-color-sfaccent-light'] = t('accent-bg');
  out['--mantine-color-sfaccent-light-color'] = t('accent-fg');
  return out;
}

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  dark: schemeVars(0),
  light: schemeVars(1),
});

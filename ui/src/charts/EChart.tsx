/**
 * A thin ECharts wrapper of our own (D-776): init with the scheme's theme, resize with the container,
 * dispose on unmount. Tree-shaken imports from `echarts/core`: register a chart type here before use.
 */
import { useComputedColorScheme } from '@mantine/core';
import { BarChart, CustomChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { useEffect, useRef } from 'react';
import { chartPalette, fonts, tokenValue, type Scheme } from '../theme/tokens';

echarts.use([
  BarChart,
  CustomChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export type EChartsOption = echarts.EChartsCoreOption;

/** The ECharts theme of one scheme (UI_tokens.md, chart palette). */
export function echartsTheme(scheme: Scheme): Record<string, unknown> {
  const t = (n: Parameters<typeof tokenValue>[0]) => tokenValue(n, scheme);
  const axis = {
    axisLine: { lineStyle: { color: t('border') } },
    axisTick: { lineStyle: { color: t('border') } },
    axisLabel: { color: t('text-muted'), fontSize: 11, fontFamily: fonts.mono },
    splitLine: { lineStyle: { color: t('border') } },
  };
  return {
    color: chartPalette(scheme),
    backgroundColor: 'transparent',
    textStyle: { fontFamily: fonts.sans, color: t('text-secondary') },
    categoryAxis: axis,
    valueAxis: axis,
    timeAxis: axis,
    legend: { textStyle: { color: t('text-muted'), fontSize: 11 } },
    tooltip: {
      backgroundColor: t('surface-2'),
      borderColor: t('border-panel'),
      textStyle: { color: t('text'), fontSize: 12 },
    },
  };
}

export function EChart({
  option,
  height,
  ariaLabel,
}: {
  option: EChartsOption;
  height: number;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const scheme = useComputedColorScheme('dark');

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const name = `sfac-${scheme}`;
    echarts.registerTheme(name, echartsTheme(scheme));
    const c = echarts.init(el, name, { renderer: 'canvas' });
    chart.current = c;
    // Resize on the next frame: resizing inside the observer's callback re-triggers it.
    let frame = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => c.resize());
    });
    ro.observe(el);
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, [scheme]);

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true, lazyUpdate: true });
  }, [option, scheme]);

  return <div ref={ref} role="img" aria-label={ariaLabel} style={{ width: '100%', height }} />;
}

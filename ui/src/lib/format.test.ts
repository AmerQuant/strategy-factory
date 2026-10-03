import { describe, expect, it } from 'vitest';
import { formatDateTime, formatDuration, formatEta, percent, stageLabel, toCsv } from './format';

describe('T17a-FE formatting', () => {
  it('formats durations', () => {
    expect(formatDuration(0)).toBe('0s');
    expect(formatDuration(42.4)).toBe('42s');
    expect(formatDuration(13 * 60 + 4)).toBe('13m 04s');
    expect(formatDuration(2 * 3600 + 7 * 60 + 59)).toBe('2h 07m');
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(-5)).toBe('0s');
  });

  it('formats an estimate, or says it is not available yet', () => {
    expect(formatEta(null)).toBe('estimating…');
    expect(formatEta(90)).toBe('~1m 30s');
  });

  it('shows times in UTC', () => {
    expect(formatDateTime('2026-09-29T19:04:31Z')).toBe('2026-09-29 19:04 UTC');
    expect(formatDateTime(null)).toBe('—');
  });

  it('clamps a percentage and names stages', () => {
    expect(percent(5, 10)).toBe(50);
    expect(percent(5, null)).toBe(0);
    expect(percent(12, 10)).toBe(100);
    expect(stageLabel('s01_edge')).toBe('S1 edge');
    expect(stageLabel('custom')).toBe('custom');
  });

  it('writes RFC 4180 CSV', () => {
    expect(
      toCsv(
        ['a', 'b'],
        [
          ['x,y', 'say "hi"'],
          [1, null],
        ],
      ),
    ).toBe('a,b\r\n"x,y","say ""hi"""\r\n1,\r\n');
  });
});

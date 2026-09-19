# tests/fixtures

Small synthetic series with hand-computed answers and small samples of real data per
source (added from T02/T04 onward). Parity fixtures are never edited outside an explicit task.

## tv_golden/

TradingView golden exports for the indicator tests (T07, F-0.4.2): `<EXCHANGE>_<SYMBOL>_<TF>.csv.gz`,
produced with `tools/tradingview/sf_golden_indicators.pine` ("Export chart data", UNIX time).
Each file holds TradingView's own OHLC plus one column per plot title; `tests/unit/test_F_0_4_2_golden.py`
feeds that OHLC into our indicators and compares every plot column. The CSVs are stored gzip-compressed
(level 9, empty file name, mtime 0) so the bytes are reproducible; the decompressed bytes are the
original export, unchanged. Columns that do not come from the Pine script (e.g. another indicator that
was on the chart, `Upper Line (Lowest + ATR)`) are ignored. If the folder is empty the golden tests skip.

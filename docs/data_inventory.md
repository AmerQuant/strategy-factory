# Data inventory (T00 · F-0.1.12)

Generated 2026-09-19 10:43:28 UTC by `scripts/data_inventory.py` in 56.7 s. Read-only scan.

**Source integrity check:** 34899 source files stat-ed before and after the run (+ 14 evidence files outside the roots: logs, manifests, downloader code); changed: 0, added: 0, removed: 0 → **no source file was modified**.

Source roots:
- `QuantPlatform`: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data`
- `MarketScanner candles`: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles`
- `MarketEdge futures`: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketEdge\Data\Futures`
- `ATM futures`: `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07`

Method: every file gets a *light pass* (size, symbol, first/last timestamp from the head/tail lines or parquet min/max); at most 50 files per group get a *deep pass* (full read: timeframe, sessions, timezone tests, quality). Deep-sample files = priority tickers (split probes / cross-source tickers) + evenly spaced files from the sorted list.

## Summary

| group | source | asset class | #symbols | timeframe | date range | format | timezone; bar label | price type | adjustment | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| QP-US-EQ-1D | Alpaca (free IEX feed) via QuantPlatform downloader | US equity / ETF | 6362 | 1d | 2020-07-13 → 2026-06-18 | parquet | UTC; MIXED: midnight-NY (04/05 UTC) in most files, 00:00 UTC in some; session date | trade (last-trade OHLC); no bid/ask/spread columns | split + dividend adjusted; EXCEPTIONS: AVGO not adjusted for a split | deep stats on 50/6362 files; 475 empty files; IEX-only volume (≈1–4% of SIP); two timestamp conventions |
| QP-US-EQ-1H | Alpaca (free IEX feed) via QuantPlatform downloader | US equity / ETF | 5887 | 1h | 2020-07-13 → 2026-06-18 | parquet | UTC (tz-aware); bar-start (hour-aligned) | trade (last-trade OHLC); no bid/ask/spread columns | split + dividend adjusted; EXCEPTIONS: AVGO not adjusted for a split | deep stats on 50/5887 files; IEX-only volume; sparse 08:00/16:00 ET extended-hours bars (not RTH-filtered) |
| QP-CRYPTO-1H | ccxt public exchange (binanceus by default; fallback kraken/kucoin/bitstamp) | crypto (spot) | 31 | 1h | 2017-01-01 → 2026-06-19 | parquet | UTC (tz-aware); bar-start (ccxt convention) | trade (last-trade OHLC); no bid/ask/spread columns | n/a (crypto) |  |
| QP-STOOQ-1H | Stooq (stooq.com bulk download) | US equity / ETF (NASDAQ, NYSE, NYSE MKT) | 12382 | 1h | 2024-06-03 → 2026-06-18 | txt (CSV) | naive Europe/Warsaw (CET/CEST) wall clock; bar-end | trade (last-trade OHLC); no bid/ask/spread columns | split-adjusted only (no dividend adj.) | deep stats on 50/12382 files; 39 empty files; only ≈2 years of history; volume ≈55–85% of SIP daily |
| QP-REF | Alpaca assets endpoint (asset list) / market-cap snapshot (see downloader) | reference data (not prices) | 3 | — | — | parquet + csv | as_of date;  | — | n/a | not price data |
| MS-US-1D | Alpaca SIP (consolidated tape), adjustment=all | US equity / ETF (S&P 500 point-in-time members + small/mid caps) | 6711 | 1d | 2016-01-04 → 2026-07-01 | csv | date only (session date); session date | trade (last-trade OHLC); no bid/ask/spread columns | split + dividend adjusted (splits: probes; dividends: adjustment=all in downloader code) | deep stats on 50/6711 files |
| MS-CRYPTO-1D | Binance spot via ccxt (`ccxt_binance` in manifest) | crypto (spot); PAXG = gold-backed token | 101 | 1d | 2017-08-17 → 2026-06-30 | csv | date only (UTC day, exchange convention); session date | trade (last-trade OHLC); no bid/ask/spread columns | n/a (crypto) | deep stats on 50/102 files; PAXG_USDT appears twice (crypto_ and gold_ prefix) |
| MS-PIT-CRYPTO-1D | Binance spot via ccxt (point-in-time universe incl. delisted) | crypto (spot), includes delisted pairs | 601 | 1d | 2017-08-17 → 2026-06-30 | csv | date only (UTC day, exchange convention); session date | trade (last-trade OHLC); no bid/ask/spread columns | n/a (crypto) | deep stats on 50/601 files; includes delisted pairs (survivorship-free) |
| MS-IRAN-1D | TSETMC via pytse (MarketScanner pytse adapter) | Iranian equities, funds, sukuk/bonds (TSETMC instruments) | 2365 | 1d | 2001-03-25 → 2026-06-30 | csv | date only (Asia/Tehran session date); session date | trade (last-trade OHLC); no bid/ask/spread columns | likely unadjusted (jumps beyond daily limits) | deep stats on 50/2365 files; includes funds, sukuk, rights |
| ME-FUT-15M | TradeStation (or MultiCharts) chart export via 'Data Exporter v3.0' indicator | futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto) | 65 | 15m | 2006-01-03 → 2023-11-01 | txt (CSV + 7-line header) | naive exchange-local (US/Central for CME/CBOT/NYMEX); bar-end | trade (last-trade OHLC); no bid/ask/spread columns | continuous, additive back-adjusted (negative prices, no roll gaps); roll rule unknown | deep stats on 50/65 files; all series end 2023-11-01 (stale) |
| ATM-FUT-1H | TradeStation chart export via 'Data Exporter v3.0' indicator (exported 2025-07-09) | futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto) | 64 | 1h | 2006-01-09 → 2025-07-09 | txt (CSV + 7-line header) | naive exchange-local (US/Central for CME/CBOT/NYMEX); bar-end | trade (last-trade OHLC); no bid/ask/spread columns | continuous, additive back-adjusted (negative prices, no roll gaps); roll rule unknown | deep stats on 50/64 files; `.txt` twins byte-identical; 2 `- Copy` + 2 `.bak` files excluded; @ED ends 2023-05 (Eurodollar delisted) |
| ATM-FUT-1440 | TradeStation chart export via 'Data Exporter v3.0' indicator (exported 2025-07-09) | futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto) | 64 | 1d | 2006-05-25 → 2025-07-08 | txt (CSV + 7-line header) | naive exchange-local (US/Central for CME/CBOT/NYMEX); bar-end | trade (last-trade OHLC); no bid/ask/spread columns | continuous, additive back-adjusted (negative prices, no roll gaps); roll rule unknown | deep stats on 50/64 files; not copied (only 1H decided) |
| ATM-FUT-DAILY | TradeStation chart export via 'Data Exporter v3.0' indicator (exported 2025-07-09) | futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto) | 64 | 1d | 2006-05-30 → 2025-07-08 | txt (CSV + 7-line header) | naive exchange-local (US/Central for CME/CBOT/NYMEX); bar-end | trade (last-trade OHLC); no bid/ask/spread columns | continuous, additive back-adjusted (negative prices, no roll gaps); roll rule unknown | deep stats on 50/64 files; not copied (only 1H decided) |

## Overlaps (same normalised symbol in more than one group)

Normalisation: upper-case, separators `. - / _` removed (e.g. `BRK.B`=`BRK-B`=`BRKB`, `BTC_USDT`=`BTCUSDT`).

| group A | group B | # common | examples (first 25) |
|---|---|---|---|
| QP-US-EQ-1D | QP-US-EQ-1H | 5887 | A, AA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABCB, ABCL, ABEO, ABEV, ABG |
| QP-US-EQ-1D | QP-STOOQ-1H | 5372 | A, AA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABCB, ABCL, ABEO, ABEV, ABG |
| QP-US-EQ-1D | MS-US-1D | 6048 | A, AA, AABA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABCB, ABCL, ABDC, ABEO |
| QP-US-EQ-1H | QP-STOOQ-1H | 5360 | A, AA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABCB, ABCL, ABEO, ABEV, ABG |
| QP-US-EQ-1H | MS-US-1D | 5625 | A, AA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABCB, ABCL, ABEO, ABEV, ABG |
| QP-CRYPTO-1H | MS-CRYPTO-1D | 14 | ADAUSDT, ATOMUSDT, BCHUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, FILUSDT, LTCUSDT, PAXGUSDT, SOLUSDT, UNIUSDT, XLMUSDT, XRPUSDT |
| QP-CRYPTO-1H | MS-PIT-CRYPTO-1D | 27 | ADAUSDT, ATOMUSDT, BATUSDT, BCHUSDT, BNBUSDT, BTCUSDT, COMPUSDT, DOGEUSDT, ETCUSDT, ETHUSDT, FILUSDT, KNCUSDT, LTCUSDT, MKRUSDT, NEOUSDT, ONEUSDT, ONTUSDT, OXTUSDT, QTUMUSDT, SOLUSDT, UNIUSDT, VETUSDT, VTHOUSDT, XLMUSDT, XRPUSDT |
| QP-STOOQ-1H | MS-US-1D | 5458 | A, AA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABCB, ABCL, ABEO, ABEV, ABG |
| MS-CRYPTO-1D | MS-PIT-CRYPTO-1D | 94 | AAVEUSDT, ACTUSDT, ADAUSDT, AGLDUSDT, AIGENSYNUSDT, AIUSDT, ALGOUSDT, ALICEUSDT, ALLOUSDT, ANIMEUSDT, APTUSDT, ARBUSDT, ARUSDT, ASTERUSDT, ATMUSDT, ATOMUSDT, AVAXUSDT, BCHUSDT, BICOUSDT, BNBUSDT, BTCUSDT, CAKEUSDT, CELOUSDT, CHZUSDT, CRCLBUSDT |
| ME-FUT-15M | ATM-FUT-1H | 61 | @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC |
| ME-FUT-15M | ATM-FUT-1440 | 61 | @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC |
| ME-FUT-15M | ATM-FUT-DAILY | 61 | @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC |
| ATM-FUT-1H | ATM-FUT-1440 | 64 | @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC |
| ATM-FUT-1H | ATM-FUT-DAILY | 64 | @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC |
| ATM-FUT-1440 | ATM-FUT-DAILY | 64 | @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC |

## ATM folder file variants (`Historical Data - 2025-07-07`)

388 files. Standard names per timeframe/extension: `{"1440min.csv": 64, "1440min.txt": 64, "60min.csv": 64, "60min.txt": 64, "Daily.csv": 64, "Daily.txt": 64}`.
- `.csv` vs `.txt` twins: 192 byte-identical (sha256), 0 different. The inventory groups use the `.csv` copy; the `.txt` twins are duplicates.
- Files that do not fit the `Data Export,@SYM, <tf>.<ext>` pattern (not grouped, not copied): `Data Export,@AD, 60min - Copy.csv`, `Data Export,@AD, 60min - Copy.csv.bak`, `Data Export,@NG, 60min - Copy.txt`, `Data Export,@NG, 60min - Copy.txt.bak`.
  - `Data Export,@AD, 60min - Copy.csv`: first line `Date,Time,Open,High,Low,Close,Volume` (header block missing); standard file `Data Export,@AD, 60min.csv` exists.
  - `Data Export,@NG, 60min - Copy.txt`: first line `Date,Time,Open,High,Low,Close,Volume` (header block missing); standard file `Data Export,@NG, 60min.txt` exists.

## Futures overlap: ATM-FUT-1H vs ME-FUT-15M resampled to 1H

15-minute bars (bar-end labels) are aggregated into hourly bars ending on the full hour and joined to the ATM hourly bars on the label. Only hours built from 4 complete 15-minute bars are compared. Both sets are additively back-adjusted but anchored to different last contracts (`[Dec23]` vs `[Sep25]`), so closes differ by an offset that is constant between rolls; bar ranges (high−low) and volume do not depend on the offset.

| symbol | common period | 1H bars (ATM) | matched labels (share) | hours compared | modal close diff | share at modal diff | distinct diffs | range equal | volume equal |
|---|---|---|---|---|---|---|---|---|---|
| @ES | 2006-01-09 03:00:00 → 2023-11-01 16:00:00 | 105050 | 105050 (1.0) | 102200 | 417.0 | 0.9992 | 9 | 1.0 | 0.9975 |
| @NQ | 2006-01-09 03:00:00 → 2023-11-01 16:00:00 | 105025 | 105025 (1.0) | 100484 | 1668.0 | 0.9994 | 13 | 1.0 | 0.999 |
| @CL | 2006-01-10 09:00:00 → 2023-11-01 17:00:00 | 104323 | 104323 (1.0) | 103669 | -10.9 | 0.9997 | 4 | 1.0 | 0.9996 |
| @GC | 2006-01-10 14:00:00 → 2023-11-01 17:00:00 | 103856 | 103856 (1.0) | 103001 | 239.8 | 0.9996 | 11 | 1.0 | 0.9993 |
| @TY | 2006-01-09 07:00:00 → 2023-11-01 16:00:00 | 104104 | 104104 (1.0) | 102600 | 2.0625 | 0.9992 | 24 | 0.9995 | 0.999 |
| @EC | 2006-01-09 03:00:00 → 2023-11-01 16:00:00 | 105196 | 105196 (1.0) | 105032 | 0.0343 | 0.9997 | 5 | 1.0 | 0.9995 |

## MarketScanner manifest (`data/symbols.csv`, read-only corroboration)

2778 rows (the candles folder holds 9779 files → the manifest covers only part of them).

| market_slug | source_key | rows |
|---|---|---|
| iran-stocks | pytse | 2034 |
| us-stocks | alpaca | 503 |
| crypto | ccxt_binance | 100 |
| iran-indices | pytse | 55 |
| etfs | alpaca | 35 |
| indices | alpaca | 34 |
| commodities | alpaca | 17 |

## Iran instrument types (`data/iran_meta.csv`, read-only corroboration)

2034 rows; 2034 of 2365 candle files have a matching `ins` code. Name-keyword counts (whole meta file):

| keyword | rows |
|---|---|
| صندوق (fund/ETF) | 296 |
| مرابحه (murabaha sukuk) | 300 |
| اجاره (ijara sukuk) | 121 |
| مشارکت (participation bond) | 9 |
| اسناد خزانه (treasury bill) | 10 |
| حق تقدم (rights) | 0 |

## Files under the source roots not assigned to any group

```
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@AD, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@AD, 60min - Copy.csv
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@AD, 60min - Copy.csv.bak
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@AD, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@AD, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BO, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BO, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BO, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BP, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BP, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BP, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BTC, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BTC, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@BTC, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@C, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@C, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@C, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CC, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CC, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CC, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CD, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CD, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CD, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CL, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CL, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CL, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CT, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CT, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@CT, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@DX, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@DX, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@DX, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@E7, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@E7, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@E7, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@EC, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@EC, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@EC, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ED, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ED, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ED, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@EMD, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@EMD, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@EMD, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, Daily.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES.D, 1440min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES.D, 60min.txt
F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES.D, Daily.txt
... 146 more
```

## Questions for the user

1. Dukascopy: no Dukascopy data exists yet (confirmed by you). Where will the minute bid/ask data be downloaded to, and which symbols (FX majors, XAUUSD, index CFDs such as USA500IDXUSD / USA30IDXUSD)? The spec relies on it for spread profiles and FX/metal/CFD research.
2. US equities — reference source: QP-US-EQ-1D/1H are Alpaca **IEX** (volume is a small fraction of the consolidated tape), MS-US-1D is Alpaca **SIP** daily, QP-STOOQ-1H is Stooq hourly. Which is the reference source for US equities per timeframe? (Suggestion to decide: SIP for daily; for hourly only IEX or Stooq exist today.)
3. Is there an Alpaca SIP **hourly** download anywhere (the spec prefers SIP + RTH filter)? If not, should T04 include a downloader or should we use IEX/Stooq hourly for now?
4. QP-US-EQ-1H is hour-aligned bar-start (09:00–15:00 ET) and NOT RTH-filtered (sparse 08:00 and 16:00 ET extended-hours bars exist). The 09:00 bar therefore probably mixes 09:00–09:30 pre-market with the first 30 RTH minutes. Is this data acceptable for 1h research, or should hourly bars be rebuilt from minute data with an RTH filter (09:30-anchored bars)?
5. QuantPlatform AVGO: the QP series is not adjusted for the 2024-07-15 10:1 split (prices ×10 before the split vs. SIP), while other split tickers are adjusted. Probably the file was downloaded before the split and later extended incrementally. Should QP data be re-downloaded, or do we treat MS-US-1D (SIP) as the reference and QP only as a fallback?
6. Stooq hourly is split-adjusted but NOT dividend-adjusted (older prices of dividend payers sit 1–8% above the SIP adjustment=all series). Which price basis should the canonical store use: raw/split-only (TradingView-like, needed for parity) or total-return adjusted? Also, Stooq intraday history covers only ≈2 years (2024-06 →). Is that enough for the 1h research track?
7. Stooq half-days show a 5th bar labelled 14:00 ET that holds the closing auction. How should Stooq bars be binned on half-days (drop, merge into the last RTH bar, keep)?
8. Futures (MarketEdge): exported from TradeStation or MultiCharts? Which back-adjustment setting was used (TradeStation default for `@` symbols is *not* back-adjusted unless enabled; the data suggests back-adjusted — please confirm), and which roll rule (volume-based / N days before expiry)?
9. Futures timestamps: confirm the export used **exchange time** (US/Central for CME/CBOT/NYMEX/COMEX; US/Eastern for ICE softs) rather than the PC local time.
10. Futures data ends 2023-11-01 for every file. Is a refreshed export planned? Are the ICE softs, VIX futures and the `.D` (day-session) variants in scope?
11. Crypto: two sources disagree on venue — QP-CRYPTO-1H (binanceus hourly, thin volume) vs MS crypto daily (Binance global). Is crypto in scope for Strategy Factory at all? If yes, which venue is the reference?
12. Iran (TSE/Farabourse, 2365 instruments incl. funds and sukuk): in scope for Strategy Factory? If yes we need an adjustment policy (capital increases/dividends appear unadjusted) and a session/calendar definition (Sat–Wed, Asia/Tehran).
13. QuantPlatform `us_equity` holds 6362 daily and 5887 hourly files: were delisted tickers included (survivorship) or only currently active symbols? `reference/assets` lists status active/inactive — should it drive the universe?
14. Auxiliary series (VIX index, SPX index, rates) from Yahoo: none found in these folders. Where should they come from?
15. Execution broker(s) for cost profiles are still open (HANDOFF §7.3) — no broker/MT5 exports were found in the scanned folders.
16. ATM futures (T00b): the new 1H export matches the old 15-minute set exactly on the common period (identical labels and bar ranges; closes differ by one constant back-adjustment offset per roll segment), so it is the same TradeStation feed and settings. Please confirm the TradeStation settings used for both exports: back-adjustment on (the data shows additive back-adjustment), roll rule (volume-based or N days before expiry), and time zone = exchange time.
17. ATM futures: `1440min` and `Daily` files differ (e.g. @ES 2025-07-07 close 6263.25 in 1440min vs 6276.00 in Daily; Daily looks like settlement prices, 1440min like the last trade of the session). Only 1H is imported now; should one of the daily variants be imported too, and which one is the reference for daily futures research?
18. ATM futures: ICE softs (@CC, @CT, @KC, @OJ, @SB) — confirm their timestamps are US/Eastern exchange time (the other exchanges are US/Central).
19. Security (outside scope, noticed while collecting source evidence): `MarketScanner/scripts/host_download.py` and `host_download_us_pit.py` contain a hard-coded fallback Alpaca API key in `os.environ.get(...)`. Consider rotating that key and removing the default. (Value not reproduced here.)

## Files that could not be read

None.

---

## QP-US-EQ-1D — QuantPlatform · US equities · daily parquet

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us_equity` | `*/1d.parquet` | 6362 | 126.5 MB | `{".parquet": 6362}` |

### 2. Probable source
**Alpaca (free IEX feed) via QuantPlatform downloader**

- Canonical schema `ts(UTC) | symbol | open | high | low | close | volume` = QuantPlatform's own normalised layout (one folder per ticker, `1d.parquet`/`1h.parquet`).
- `alpaca.py:3`: Pulls 1h US-equity bars (~7y of history on the free IEX feed) and normalises them
- `alpaca.py:44`: "feed": "iex",
- `alpaca.py:52`: the ``X-Ratelimit-Limit`` response header). The free IEX feed returns hourly
- `alpaca.py:143`: feed: str = "iex",

### 3–4. Symbols & asset class
- Asset class guess: **US equity / ETF**
- 6362 symbols; first 30: A, AA, AABA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABCB, ABCL, ABDC, ABEO, ABEV, ABG, ABLV, ABM, ABNB

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1d** in 48 of 50 deep-sample files; the other 2 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1d": 48, "14400min": 1, "33090min": 1}`
- Most frequent spacing per file (bar grid): `{"1d": 49, "5760min": 1}` → mixed timeframes: True; median share of diffs equal to the median: 0.781
- **Empty files (no data rows):** 475 of 6362; e.g. AABA/1d.parquet, ABDC/1d.parquet, ACETQ/1d.parquet, ACLL/1d.parquet, ACSF/1d.parquet, AETI/1d.parquet, AGN/1d.parquet, AKP/1d.parquet, AKS/1d.parquet, ALDR/1d.parquet, ALGR/1d.parquet, ALN/1d.parquet, ALO/1d.parquet, ALOG/1d.parquet, ALOV/1d.parquet

### 6. Date range
- Across all 6362 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2020-07-13 04:00:00+00:00", "median": "2020-07-27 04:00:00+00:00", "max": "2026-06-18 04:00:00+00:00"}`; last ts `{"min": "2020-07-27 04:00:00+00:00", "median": "2026-06-18 04:00:00+00:00", "max": "2026-06-18 04:00:00+00:00"}`

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us_equity\AAPL\1d.parquet`

`{"ts": "Datetime(time_unit='us', time_zone='UTC')", "symbol": "String", "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64", "volume": "Float64"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us_equity\AAPL\1d.parquet`
_parquet: rows rendered from the stored values (Python repr), dtypes listed in schema_

First 5 rows (with header lines):
```
(datetime.datetime(2020, 7, 27, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 90.76, 91.86, 90.51, 91.85, 794984.0)
(datetime.datetime(2020, 7, 28, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 91.36, 91.51, 90.32, 90.33, 601320.0)
(datetime.datetime(2020, 7, 29, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 90.85, 92.18, 90.85, 92.0, 545508.0)
(datetime.datetime(2020, 7, 30, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 91.21, 93.2, 90.86, 93.19, 1290656.0)
(datetime.datetime(2020, 7, 31, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 99.97, 103.02, 97.71, 102.97, 3571328.0)
```
Last 3 rows:
```
(datetime.datetime(2026, 6, 16, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 295.8, 300.445, 293.99, 299.26, 1229175.0)
(datetime.datetime(2026, 6, 17, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 300.845, 301.95, 294.39, 296.07, 1195185.0)
(datetime.datetime(2026, 6, 18, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 296.87, 300.56, 295.635, 297.86, 1278255.0)
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- Stored as `datetime[μs, UTC]`. Distinct time-of-day sets per file (all 6362 files): `{"04:00,05:00": 5677, "04:00": 170, "00:00": 39, "05:00": 1}`. `04:00,05:00` = Alpaca's native daily stamp (midnight America/New_York → 04:00 UTC in EDT, 05:00 UTC in EST); `00:00` = session date re-stamped at 00:00 UTC. **Two conventions coexist** — 39 files use 00:00 UTC, e.g. AAPL, ABBV, ADBE, AMD, AMZN, AVGO, BAC, COST, CRM, CSCO, CVX, DIS, GOOGL, HD, INTC, JNJ, JPM, KO, LLY, MA.
- Weekday distribution (sample): `{"Tue": 11150, "Wed": 11085, "Fri": 10799, "Thu": 10769, "Mon": 10015}`
- Rows on NYSE full-holiday dates `["2020-11-26", "2021-12-24", "2022-06-20", "2023-04-07", "2024-07-04", "2024-12-25", "2025-01-09", "2025-04-18"]`: 0 (files with any: 0)

### 13–14. Adjustment / futures specifics
Split probes (previous close ÷ open on split date; ≈1 → split-adjusted, ≈factor → unadjusted):

| ticker | split | factor | prev close | open | ratio | verdict |
|---|---|---|---|---|---|---|
| AAPL | 2020-08-31 (prev 2020-08-28) | 4.0 | 121.09 | 121.98 | 0.993 | adjusted |
| TSLA | 2020-08-31 (prev 2020-08-28) | 5.0 | 147.7 | 148.67 | 0.993 | adjusted |
| NVDA | 2021-07-20 (prev 2021-07-19) | 4.0 | 18.71 | 18.82 | 0.994 | adjusted |
| AMZN | 2022-06-06 (prev 2022-06-03) | 20.0 | 122.32 | 124.3 | 0.984 | adjusted |
| GOOGL | 2022-07-18 (prev 2022-07-15) | 20.0 | 110.79 | 112.26 | 0.987 | adjusted |
| TSLA | 2022-08-25 (prev 2022-08-24) | 3.0 | 296.97 | 301.95 | 0.984 | adjusted |
| WMT | 2024-02-26 (prev 2024-02-23) | 3.0 | 57.08 | 57.69 | 0.989 | adjusted |
| NVDA | 2024-06-10 (prev 2024-06-07) | 10.0 | 120.63 | 120.29 | 1.003 | adjusted |
| CMG | 2024-06-26 (prev 2024-06-25) | 50.0 | 65.66 | 65.62 | 1.001 | adjusted |
| AVGO | 2024-07-15 (prev 2024-07-12) | 10.0 | 1669.9 | 167.31 | 9.981 | unadjusted |
| SMCI | 2024-10-01 (prev 2024-09-30) | 10.0 | 41.61 | 42.06 | 0.989 | adjusted |

Cross-source close ratio vs MS-US-1D (Alpaca SIP, adjustment=all), median per year. A ratio drifting away from 1 in older years indicates a different dividend-adjustment basis; flat ≈1 means same basis:

| ticker | common days | close ratio by year | volume ratio by year |
|---|---|---|---|
| AAPL | 1481 | `{"2020": 1.0001, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 0.9999}` | `{"2020": 0.0112, "2021": 0.0129, "2022": 0.0167, "2023": 0.0153, "2024": 0.0163, "2025": 0.0267, "2026": 0.0282}` |
| MSFT | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0001, "2024": 1.0, "2025": 1.0, "2026": 0.9999}` | `{"2020": 0.0195, "2021": 0.0204, "2022": 0.0209, "2023": 0.0175, "2024": 0.0168, "2025": 0.024, "2026": 0.0254}` |
| SPY | 1481 | `{"2020": 1.0001, "2021": 1.0001, "2022": 1.0001, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 0.9999}` | `{"2020": 0.0106, "2021": 0.015, "2022": 0.0174, "2023": 0.0154, "2024": 0.015, "2025": 0.0167, "2026": 0.0224}` |
| KO | 1479 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0001}` | `{"2020": 0.0244, "2021": 0.0261, "2022": 0.0275, "2023": 0.0225, "2024": 0.0261, "2025": 0.0364, "2026": 0.0601}` |
| XOM | 1478 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0166, "2021": 0.0204, "2022": 0.0209, "2023": 0.0179, "2024": 0.0189, "2025": 0.0358, "2026": 0.0405}` |
| JPM | 1478 | `{"2020": 1.0001, "2021": 1.0, "2022": 1.0001, "2023": 1.0, "2024": 1.0001, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0238, "2021": 0.023, "2022": 0.0277, "2023": 0.0195, "2024": 0.0189, "2025": 0.0244, "2026": 0.0248}` |
| T | 1479 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.015, "2021": 0.0189, "2022": 0.0226, "2023": 0.0236, "2024": 0.0255, "2025": 0.0387, "2026": 0.0554}` |
| TSLA | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 0.9999, "2026": 0.9998}` | `{"2020": 0.0089, "2021": 0.0198, "2022": 0.0226, "2023": 0.0057, "2024": 0.0073, "2025": 0.0095, "2026": 0.0135}` |
| NVDA | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 0.9999, "2026": 0.9998}` | `{"2020": 0.0158, "2021": 0.022, "2022": 0.02, "2023": 0.0123, "2024": 0.0096, "2025": 0.0158, "2026": 0.0261}` |
| AMZN | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0001, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0273, "2021": 0.0315, "2022": 0.026, "2023": 0.0169, "2024": 0.0178, "2025": 0.0319, "2026": 0.0394}` |
| GOOGL | 1481 | `{"2020": 1.0, "2021": 1.0001, "2022": 1.0, "2023": 1.0001, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0355, "2021": 0.0382, "2022": 0.0321, "2023": 0.0209, "2024": 0.0211, "2025": 0.0323, "2026": 0.0297}` |
| WMT | 1479 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0261, "2021": 0.0261, "2022": 0.0319, "2023": 0.0279, "2024": 0.023, "2025": 0.037, "2026": 0.0356}` |
| CMG | 1479 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 0.9999}` | `{"2020": 0.0386, "2021": 0.0607, "2022": 0.0703, "2023": 0.0592, "2024": 0.0427, "2025": 0.0521, "2026": 0.0688}` |
| AVGO | 1481 | `{"2020": 10.0145, "2021": 10.0165, "2022": 10.0162, "2023": 10.0162, "2024": 10.0037, "2025": 1.0015, "2026": 1.0015}` | `{"2020": 0.0031, "2021": 0.0036, "2022": 0.0036, "2023": 0.0033, "2024": 0.005, "2025": 0.0267, "2026": 0.0275}` |
| SMCI | 1482 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0373, "2021": 0.0324, "2022": 0.0423, "2023": 0.0329, "2024": 0.0132, "2025": 0.02, "2026": 0.0355}` |

Dividend-payer drift (first-year minus last-year ratio, KO/XOM/T/JPM): `[-0.0001, 0.0, 0.0001, 0.0]` → **same dividend basis as SIP adjustment=all (split + dividend adjusted)**.

**Anomaly:** AVGO — whole years differ from the SIP series by a split factor → split adjustment not applied consistently for these tickers.

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 53818 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 2 |
| null_cells | 0 |
| big_moves | 102 |
| missing_bar_gaps | 100 |
| zero_volume_share_median_file | 0.0 |
| zero_volume_share_max_file | 0.9496 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 18 |
| files_with_nonpos_price | 2 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 6847802, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 254, "big_moves": 12978, "missing_bar_gaps": 12724}` |

_Per-file statistics computed on 50 of 6362 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: AAPL, TSLA, NVDA, AMZN, GOOGL, WMT, CMG, AVGO, SMCI, MSFT, SPY, KO, XOM, JPM, T, A, AI, ANSC, ATV, BETA, BRK.B, CCK, CLW, CRVO, DFLI, ECX, ETS, FLYE, GEF, GSHR, HPR, INDB, JOBY, LB, LVGO, MHO, MWG, NPCE, OKE, PCAP, PRA, RBAC, RPLA.U, SGC, SONO, SY, TMUSI, UG, VNTG, WSBK

---

## QP-US-EQ-1H — QuantPlatform · US equities · hourly parquet

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us_equity` | `*/1h.parquet` | 5887 | 542.5 MB | `{".parquet": 5887}` |

### 2. Probable source
**Alpaca (free IEX feed) via QuantPlatform downloader**

- Same folder layout and schema as QP-US-EQ-1D.
- `alpaca.py:3`: Pulls 1h US-equity bars (~7y of history on the free IEX feed) and normalises them
- `alpaca.py:42`: "session": "09:30-16:00 ET",
- `alpaca.py:44`: "feed": "iex",
- `alpaca.py:52`: the ``X-Ratelimit-Limit`` response header). The free IEX feed returns hourly

### 3–4. Symbols & asset class
- Asset class guess: **US equity / ETF**
- 5887 symbols; first 30: A, AA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABCB, ABCL, ABEO, ABEV, ABG, ABLV, ABM, ABNB, ABOS, ABSI

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1h** in 40 of 50 deep-sample files; the other 10 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1h": 40, "1500min": 1, "6480min": 1, "180min": 2, "25920min": 1, "1380min": 1, "22920min": 1, "120min": 1, "1d": 1, "1410min": 1}`
- Most frequent spacing per file (bar grid): `{"1h": 49, "4h": 1}` → mixed timeframes: True; median share of diffs equal to the median: 0.816

### 6. Date range
- Across all 5887 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2020-07-13 13:00:00+00:00", "median": "2020-07-27 15:00:00+00:00", "max": "2026-06-18 16:00:00+00:00"}`; last ts `{"min": "2020-07-27 18:00:00+00:00", "median": "2026-06-18 19:00:00+00:00", "max": "2026-06-18 20:00:00+00:00"}`

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us_equity\AAPL\1h.parquet`

`{"ts": "Datetime(time_unit='us', time_zone='UTC')", "symbol": "String", "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64", "volume": "Float64"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us_equity\AAPL\1h.parquet`
_parquet: rows rendered from the stored values (Python repr), dtypes listed in schema_

First 5 rows (with header lines):
```
(datetime.datetime(2020, 7, 27, 13, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 90.76, 91.84, 90.54, 91.43, 310520.0)
(datetime.datetime(2020, 7, 27, 14, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 91.43, 91.72, 91.02, 91.3, 195700.0)
(datetime.datetime(2020, 7, 27, 15, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 91.34, 91.42, 90.51, 90.96, 53624.0)
(datetime.datetime(2020, 7, 27, 16, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 90.94, 91.23, 90.8, 91.23, 34056.0)
(datetime.datetime(2020, 7, 27, 17, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 91.26, 91.55, 91.19, 91.55, 64616.0)
```
Last 3 rows:
```
(datetime.datetime(2026, 6, 18, 17, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 297.19, 298.345, 297.04, 297.56, 92182.0)
(datetime.datetime(2026, 6, 18, 18, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 297.575, 298.065, 297.02, 297.73, 93463.0)
(datetime.datetime(2026, 6, 18, 19, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'AAPL', 297.69, 299.22, 297.04, 297.86, 261497.0)
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- Stored as `datetime[μs, UTC]` (tz-aware) → timezone explicit: **UTC**.
- Bar labels converted to America/New_York — first label per day: `{"09:00": 39068, "10:00": 4018, "08:00": 3835, "11:00": 1285, "12:00": 646}`; last label per day: `{"15:00": 43800, "16:00": 3570, "14:00": 821, "12:00": 783, "13:00": 573}`
- All NY-local labels (count across sample): `{"08:00": 3923, "09:00": 42970, "10:00": 45589, "11:00": 45209, "12:00": 44822, "13:00": 44575, "14:00": 45079, "15:00": 47400, "16:00": 3614}`
- Literal UTC probe: bars with UTC time in [08:00,13:30): 31825; bars ≥ 20:00 UTC: 19934 (note: 13:00–13:30 UTC is inside RTH-hour-aligned bars in summer, so the NY-local probe below is the meaningful one)
- NY-local probe: bars labelled before 09:00 ET: 3923; labelled ≥ 16:00 ET: 3614; ≥ 17:00 ET: 0
- UTC first label per day, NY summer (EDT): `{"13:00": 25468, "14:00": 2675, "12:00": 2383, "15:00": 827, "19:00": 323}`; NY winter (EST): `{"14:00": 13581, "13:00": 1444, "15:00": 1336, "16:00": 367, "20:00": 159}` → a 1-hour shift in UTC between seasons means timestamps track the US exchange clock correctly after conversion.
- Bars per NY day: `{"7": 32648, "8": 4136, "6": 2967, "5": 1784, "1": 1680}`
- Half-days in sample: `[{"2023-11-24": "4 bars, last label 12:00 ET", "2024-11-29": "4 bars, last label 12:00 ET", "2024-12-24": "4 bars, last label 12:00 ET"}, {"2023-11-24": "5 bars, last label 12:00 ET", "2024-11-29": "5 bars, last label 13:00 ET", "2024-12-24": "5 bars, last label 13:00 ET"}, {"2023-11-24": "4 bars, last label 12:00 ET", "2024-11-29": "4 bars, last label 12:00 ET", "2024-12-24": "6 bars, last label 13:00 ET"}]`
- Bars on NYSE full holidays: 0 (files with any: 0)
- Interpretation: the regular labels are 09:00–15:00 ET (7 per day, no 09:30 label) → **bar-start of hour-aligned bars** (a bar-end convention would need a 16:00 label every day). Sparse extra labels `{"08:00": 3923, "16:00": 3614}` are **extended-hours bars** (08:00 = 08:00–09:00 pre-market, 16:00 = 16:00–17:00 after-hours) carrying 0.12% of volume → the data is **not RTH-filtered**; the 09:00 bar therefore most likely also contains 09:00–09:30 pre-market prints.

### 13–14. Adjustment / futures specifics
Split probes (previous close ÷ open on split date; ≈1 → split-adjusted, ≈factor → unadjusted):

| ticker | split | factor | prev close | open | ratio | verdict |
|---|---|---|---|---|---|---|
| AAPL | 2020-08-31 (prev 2020-08-28) | 4.0 | 121.09 | 121.98 | 0.993 | adjusted |
| TSLA | 2020-08-31 (prev 2020-08-28) | 5.0 | 147.7 | 148.67 | 0.993 | adjusted |
| NVDA | 2021-07-20 (prev 2021-07-19) | 4.0 | 18.71 | 18.82 | 0.994 | adjusted |
| AMZN | 2022-06-06 (prev 2022-06-03) | 20.0 | 122.32 | 124.3 | 0.984 | adjusted |
| GOOGL | 2022-07-18 (prev 2022-07-15) | 20.0 | 110.79 | 112.26 | 0.987 | adjusted |
| TSLA | 2022-08-25 (prev 2022-08-24) | 3.0 | 296.97 | 301.95 | 0.984 | adjusted |
| WMT | 2024-02-26 (prev 2024-02-23) | 3.0 | 57.08 | 57.69 | 0.989 | adjusted |
| NVDA | 2024-06-10 (prev 2024-06-07) | 10.0 | 120.63 | 120.29 | 1.003 | adjusted |
| CMG | 2024-06-26 (prev 2024-06-25) | 50.0 | 65.66 | 66.24 | 0.991 | adjusted |
| AVGO | 2024-07-15 (prev 2024-07-12) | 10.0 | 1669.9 | 167.31 | 9.981 | unadjusted |
| SMCI | 2024-10-01 (prev 2024-09-30) | 10.0 | 41.61 | 42.06 | 0.989 | adjusted |

Cross-source close ratio vs MS-US-1D (Alpaca SIP, adjustment=all), median per year. A ratio drifting away from 1 in older years indicates a different dividend-adjustment basis; flat ≈1 means same basis:

| ticker | common days | close ratio by year | volume ratio by year |
|---|---|---|---|
| AAPL | 1481 | `{"2020": 1.0001, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 0.9999}` | `{"2020": 0.0112, "2021": 0.0129, "2022": 0.0167, "2023": 0.0153, "2024": 0.0163, "2025": 0.0267, "2026": 0.0282}` |
| MSFT | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0001, "2024": 1.0, "2025": 1.0, "2026": 0.9999}` | `{"2020": 0.0195, "2021": 0.0204, "2022": 0.0209, "2023": 0.0175, "2024": 0.0168, "2025": 0.024, "2026": 0.0254}` |
| SPY | 1481 | `{"2020": 1.0001, "2021": 1.0001, "2022": 1.0001, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 0.9999}` | `{"2020": 0.0106, "2021": 0.015, "2022": 0.0174, "2023": 0.0154, "2024": 0.015, "2025": 0.0167, "2026": 0.0224}` |
| KO | 1479 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0001}` | `{"2020": 0.0244, "2021": 0.0261, "2022": 0.0275, "2023": 0.0225, "2024": 0.0261, "2025": 0.0364, "2026": 0.0601}` |
| XOM | 1478 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0166, "2021": 0.0204, "2022": 0.0209, "2023": 0.0179, "2024": 0.0189, "2025": 0.0358, "2026": 0.0405}` |
| JPM | 1478 | `{"2020": 1.0001, "2021": 1.0, "2022": 1.0001, "2023": 1.0, "2024": 1.0001, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0238, "2021": 0.023, "2022": 0.0277, "2023": 0.0195, "2024": 0.0189, "2025": 0.0244, "2026": 0.0248}` |
| T | 1478 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.015, "2021": 0.0189, "2022": 0.0225, "2023": 0.0236, "2024": 0.0254, "2025": 0.0385, "2026": 0.0554}` |
| TSLA | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 0.9999, "2026": 0.9998}` | `{"2020": 0.0089, "2021": 0.0198, "2022": 0.0226, "2023": 0.0057, "2024": 0.0073, "2025": 0.0095, "2026": 0.0135}` |
| NVDA | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 0.9999, "2026": 0.9998}` | `{"2020": 0.0158, "2021": 0.022, "2022": 0.02, "2023": 0.0123, "2024": 0.0096, "2025": 0.0158, "2026": 0.0261}` |
| AMZN | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0001, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0273, "2021": 0.0315, "2022": 0.026, "2023": 0.0169, "2024": 0.0178, "2025": 0.0319, "2026": 0.0394}` |
| GOOGL | 1481 | `{"2020": 1.0, "2021": 1.0001, "2022": 1.0, "2023": 1.0001, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0355, "2021": 0.0382, "2022": 0.0321, "2023": 0.0209, "2024": 0.0211, "2025": 0.0323, "2026": 0.0297}` |
| WMT | 1478 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0001}` | `{"2020": 0.0258, "2021": 0.0257, "2022": 0.0314, "2023": 0.0267, "2024": 0.0228, "2025": 0.0368, "2026": 0.0355}` |
| CMG | 1478 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 0.9999}` | `{"2020": 0.0298, "2021": 0.0408, "2022": 0.0412, "2023": 0.0271, "2024": 0.0295, "2025": 0.052, "2026": 0.0688}` |
| AVGO | 1481 | `{"2020": 10.0145, "2021": 10.0165, "2022": 10.0162, "2023": 10.0162, "2024": 10.0037, "2025": 1.0015, "2026": 1.0015}` | `{"2020": 0.0031, "2021": 0.0036, "2022": 0.0036, "2023": 0.0033, "2024": 0.005, "2025": 0.0267, "2026": 0.0275}` |
| SMCI | 1481 | `{"2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0, "2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2020": 0.0341, "2021": 0.0244, "2022": 0.0346, "2023": 0.03, "2024": 0.0117, "2025": 0.02, "2026": 0.0355}` |

Dividend-payer drift (first-year minus last-year ratio, KO/XOM/T/JPM): `[-0.0001, 0.0, 0.0001, 0.0]` → **same dividend basis as SIP adjustment=all (split + dividend adjusted)**.

**Anomaly:** AVGO — whole years differ from the SIP series by a split factor → split adjustment not applied consistently for these tickers.

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 323181 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 7 |
| null_cells | 0 |
| big_moves | 78 |
| missing_bar_gaps | 1119 |
| missing_day_gaps | 461 |
| zero_volume_share_median_file | 0.0 |
| zero_volume_share_max_file | 0.0 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 16 |
| files_with_nonpos_price | 3 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 38051331, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 824, "big_moves": 9184, "missing_bar_gaps": 131751}` |

_Per-file statistics computed on 50 of 5887 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: AAPL, TSLA, NVDA, AMZN, GOOGL, WMT, CMG, AVGO, SMCI, MSFT, SPY, KO, XOM, JPM, T, A, AI, ANSC, ATV, BETA, BRK.B, CCK, CLW, CRVO, DFLI, ECX, ETS, FLYE, GEF, GSHR, HPR, INDB, JOBY, LB, LVGO, MHO, MWG, NPCE, OKE, PCAP, PRA, RBAC, RPLA.U, SGC, SONO, SY, TMUSI, UG, VNTG, WSBK

---

## QP-CRYPTO-1H — QuantPlatform · crypto · hourly parquet

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\crypto` | `*/1h.parquet` | 31 | 30.3 MB | `{".parquet": 31}` |

### 2. Probable source
**ccxt public exchange (binanceus by default; fallback kraken/kucoin/bitstamp)**

- Folder names are ccxt pairs without slash (`BTCUSDT`, `BTCUSD`, `PAXGUSDT`).
- `crypto.py:24`: "binanceus",
- `crypto.py:25`: "kraken",
- `crypto.py:26`: "kucoin",
- `crypto.py:27`: "bitstamp",
- `select_and_pull_crypto.py:61`: parser.add_argument("--exchange", default="binanceus")

### 3–4. Symbols & asset class
- Asset class guess: **crypto (spot)**
- 31 symbols; first 30: ADAUSDT, ATOMUSDT, BATUSDT, BCHUSDT, BNBUSDT, BTCUSD, BTCUSDT, COMPUSDT, DOGEUSDT, ETCUSDT, ETHUSD, ETHUSDT, FILUSDT, KNCUSDT, LTCUSD, LTCUSDT, MKRUSDT, NEOUSDT, ONEUSDT, ONTUSDT, OXTUSDT, PAXGUSDT, QTUMUSDT, SOLUSDT, UNIUSDT, VETUSDT, VTHOUSDT, XLMUSDT, XRPUSDT, ZENUSDT

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1h** in 31 of 31 deep-sample files; the other 0 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1h": 31}`
- Most frequent spacing per file (bar grid): `{"1h": 31}` → mixed timeframes: False; median share of diffs equal to the median: 1.0

### 6. Date range
- Across all 31 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2017-01-01 00:00:00+00:00", "median": "2019-11-01 01:00:00+00:00", "max": "2021-06-18 13:00:00+00:00"}`; last ts `{"min": "2025-09-15 02:00:00+00:00", "median": "2026-06-19 00:00:00+00:00", "max": "2026-06-19 00:00:00+00:00"}`

| symbol | first | last | rows | size |
|---|---|---|---|---|
| ADAUSDT | 2019-09-25 12:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 58964 | 1.2 MB |
| ATOMUSDT | 2019-11-01 01:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 58087 | 1006.7 KB |
| BATUSDT | 2019-09-25 12:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 58964 | 813.0 KB |
| BCHUSDT | 2019-09-23 08:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 59012 | 1013.4 KB |
| BNBUSDT | 2019-09-23 08:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 59012 | 1.1 MB |
| BTCUSD | 2017-01-01 00:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 82945 | 1.9 MB |
| BTCUSDT | 2019-09-23 08:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 59012 | 1.4 MB |
| COMPUSDT | 2020-08-11 13:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 51283 | 761.2 KB |
| DOGEUSDT | 2019-10-25 01:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 58255 | 1.5 MB |
| ETCUSDT | 2019-09-25 12:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 58964 | 981.9 KB |
| ETHUSD | 2017-08-16 16:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 77481 | 1.7 MB |
| ETHUSDT | 2019-09-23 08:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 59012 | 1.2 MB |
| FILUSDT | 2021-06-18 13:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 43822 | 613.2 KB |
| KNCUSDT | 2020-07-17 13:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 51878 | 607.3 KB |
| LTCUSD | 2017-06-16 11:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 78950 | 1.6 MB |
| LTCUSDT | 2019-09-23 08:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 59012 | 1.0 MB |
| MKRUSDT | 2020-08-20 13:00:00+00:00 | 2025-09-15 02:00:00+00:00 | 44421 | 670.2 KB |
| NEOUSDT | 2019-11-01 01:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 58087 | 862.3 KB |
| ONEUSDT | 2020-08-27 13:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 50899 | 887.5 KB |
| ONTUSDT | 2020-02-14 02:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 55566 | 732.5 KB |
| OXTUSDT | 2020-09-25 13:00:00+00:00 | 2025-12-12 02:00:00+00:00 | 45669 | 548.2 KB |
| PAXGUSDT | 2020-09-25 13:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 50203 | 562.5 KB |
| QTUMUSDT | 2019-11-15 01:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 57751 | 706.6 KB |
| SOLUSDT | 2020-09-18 13:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 50371 | 999.4 KB |
| UNIUSDT | 2020-09-17 18:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 50390 | 910.3 KB |
| VETUSDT | 2019-11-08 01:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 57919 | 1.3 MB |
| VTHOUSDT | 2020-07-24 13:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 51710 | 875.3 KB |
| XLMUSDT | 2019-09-25 12:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 58964 | 1.0 MB |
| XRPUSDT | 2019-09-23 08:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 37140 | 735.6 KB |
| ZENUSDT | 2020-12-17 14:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 48210 | 690.1 KB |
| ZRXUSDT | 2019-09-25 12:00:00+00:00 | 2026-06-19 00:00:00+00:00 | 58964 | 805.2 KB |

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\crypto\BTCUSDT\1h.parquet`

`{"ts": "Datetime(time_unit='us', time_zone='UTC')", "symbol": "String", "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64", "volume": "Float64"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\crypto\BTCUSDT\1h.parquet`
_parquet: rows rendered from the stored values (Python repr), dtypes listed in schema_

First 5 rows (with header lines):
```
(datetime.datetime(2019, 9, 23, 8, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'BTCUSDT', 9930.13, 9930.13, 9930.13, 9930.13, 0.001)
(datetime.datetime(2019, 9, 23, 13, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'BTCUSDT', 9930.13, 9930.13, 9930.13, 9930.13, 0.0)
(datetime.datetime(2019, 9, 23, 14, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'BTCUSDT', 9930.13, 9930.13, 9930.13, 9930.13, 0.0)
(datetime.datetime(2019, 9, 23, 15, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'BTCUSDT', 9930.13, 9930.13, 9930.13, 9930.13, 0.0)
(datetime.datetime(2019, 9, 23, 16, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'BTCUSDT', 9930.13, 9930.13, 9930.13, 9930.13, 0.0)
```
Last 3 rows:
```
(datetime.datetime(2026, 6, 18, 22, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'BTCUSDT', 62964.19, 62964.19, 62756.76, 62875.88, 0.18804)
(datetime.datetime(2026, 6, 18, 23, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'BTCUSDT', 62876.65, 62984.56, 62769.16, 62984.56, 0.22264)
(datetime.datetime(2026, 6, 19, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), 'BTCUSDT', 62950.26, 63081.08, 62863.68, 62975.36, 0.04937)
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- Stored as `datetime[μs, UTC]` (tz-aware).
- Weekday distribution: `{"Wed": 250379, "Thu": 250308, "Sun": 250176, "Sat": 250152, "Fri": 249980, "Tue": 249965, "Mon": 249957}` → 24/7 incl. weekends; distinct hours per file (min): 24; minute labels: `{"0": 1750917}`
- Bar label: ccxt `fetch_ohlcv` timestamps are bar-open times (exchange convention) → **bar-start** (not verifiable from data alone).
- Largest gap in any sampled file: 21887 h

### 13–14. Adjustment / futures specifics
- Cross-source BTCUSDT: QP (hourly→UTC day) vs MS-CRYPTO-1D (Binance daily): 2462 common days, median close ratio 1.00004, p99 |dev| 0.00329, median volume ratio 0.00262 (volume ratio ≪1 → different, thinner venue).
- Cross-source ETHUSDT: QP (hourly→UTC day) vs MS-CRYPTO-1D (Binance daily): 2462 common days, median close ratio 1.00004, p99 |dev| 0.00407, median volume ratio 0.00202 (volume ratio ≪1 → different, thinner venue).

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 1750917 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 0 |
| null_cells | 0 |
| big_moves | 103 |
| missing_bar_gaps | 141 |
| zero_volume_share_median_file | 0.1312 |
| zero_volume_share_max_file | 0.5519 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 20 |
| files_with_nonpos_price | 0 |
| files_with_high_lt_low | 0 |
| files_in_sample | 31 |

Deep-sample symbols: BTCUSDT, BTCUSD, ETHUSDT, ETHUSD, PAXGUSDT, ADAUSDT, ATOMUSDT, BATUSDT, BCHUSDT, BNBUSDT, COMPUSDT, DOGEUSDT, ETCUSDT, FILUSDT, KNCUSDT, LTCUSD, LTCUSDT, MKRUSDT, NEOUSDT, ONEUSDT, ONTUSDT, OXTUSDT, QTUMUSDT, SOLUSDT, UNIUSDT, VETUSDT, VTHOUSDT, XLMUSDT, XRPUSDT, ZENUSDT, ZRXUSDT

---

## QP-STOOQ-1H — QuantPlatform · Stooq bulk export · US stocks/ETFs · txt

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us` | `**/*.txt` | 12382 | 1.7 GB | `{".txt": 12382}` |

Files per sub-folder: `{"nasdaq etfs": 910, "nasdaq stocks\\1": 2000, "nasdaq stocks\\2": 2000, "nasdaq stocks\\3": 687, "nyse etfs\\1": 2000, "nyse etfs\\2": 839, "nyse stocks\\1": 2000, "nyse stocks\\2": 1645, "nysemkt stocks": 301}`

### 2. Probable source
**Stooq (stooq.com bulk download)**

- Header `<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>` and tickers like `A.US` are Stooq's ASCII export format; folder names `nasdaq stocks/1`, `nyse etfs/2` match Stooq's bulk-zip layout.
- `import_stooq.py:8`: ``PER=60`` is hourly. The timestamps are in Central-European time (Stooq is a
- `import_stooq.py:10`: ``Europe/Warsaw`` (DST-aware) and convert to UTC — the canonical golden-rule
- `import_stooq.py:39`: path: Path, *, source_tz: str = "Europe/Warsaw", per: int = 60
- `import_stooq.py:106`: source_tz: str = "Europe/Warsaw",

### 3–4. Symbols & asset class
- Asset class guess: **US equity / ETF (NASDAQ, NYSE, NYSE MKT)**
- 12382 symbols; first 30: A, AA, AAA, AAAD, AAAU, AACB, AACBR, AACBU, AACG, AACI, AACIU, AACIW, AACO, AACOU, AACOW, AACP, AACPR, AACPU, AACPW, AADR, AADX, AAEQ, AAL, AALG, AAME, AAMI, AAOG, AAOI, AAON, AAOX

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1h** in 43 of 50 deep-sample files; the other 6 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1h": 43, "120min": 2, "1080min": 1, "180min": 1, "1140min": 1, "1200min": 1}`
- Most frequent spacing per file (bar grid): `{"1h": 49}` → mixed timeframes: False; median share of diffs equal to the median: 0.857
- `<PER>` column value (first data row, all files; `null` = header-only file): `{"60": 12343, "null": 39}`
- **Empty files (no data rows):** 39 of 12382; e.g. nasdaq etfs/dvxc.us.txt, nasdaq etfs/sixg.us.txt, nasdaq stocks/1/alts.us.txt, nasdaq stocks/1/aton.us.txt, nasdaq stocks/1/cgct.us.txt, nasdaq stocks/1/cgctw.us.txt, nasdaq stocks/1/chpgu.us.txt, nasdaq stocks/1/craqu.us.txt, nasdaq stocks/2/idiau.us.txt, nasdaq stocks/2/ipod.us.txt, nasdaq stocks/2/jabu.us.txt, nasdaq stocks/2/ntwou.us.txt, nasdaq stocks/2/opi.us.txt, nasdaq stocks/2/sava.us.txt, nasdaq stocks/3/useg.us.txt

### 6. Date range
- Across all 12382 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2024-06-03 16:00:00", "median": "2024-06-03 16:00:00", "max": "2026-06-18 21:00:00"}`; last ts `{"min": "2026-02-06 22:00:00", "median": "2026-06-18 22:00:00", "max": "2026-06-18 22:00:00"}`

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us\nasdaq stocks\1\aapl.us.txt`

`{"<TICKER>": "String", "<PER>": "Int64", "<DATE>": "Int64", "<TIME>": "Int64", "<OPEN>": "Float64", "<HIGH>": "Float64", "<LOW>": "Float64", "<CLOSE>": "Float64", "<VOL>": "Float64", "<OPENINT>": "Int64"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": true}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\us\nasdaq stocks\1\aapl.us.txt`

First 5 rows (with header lines):
```
<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>
AAPL.US,60,20240603,160000,191.419,193.066,191.043,192.631,7163633.308984948,0
AAPL.US,60,20240603,170000,192.631,193.493,192.422,192.461,6677287.7819972,0
AAPL.US,60,20240603,180000,192.451,192.938,192.095,192.441,3911312.9198135,0
AAPL.US,60,20240603,190000,192.432,192.601,191.439,191.773,3687025.5952707,0
AAPL.US,60,20240603,200000,191.773,192.566,191.359,192.124,3318871.142264,0
```
Last 3 rows:
```
AAPL.US,60,20260618,200000,297.13,298.36,297.03,297.56,1847649,0
AAPL.US,60,20260618,210000,297.575,298.0785,297.01,297.7,1805730,0
AAPL.US,60,20260618,220000,297.705,299.24,297.04,297.89,4580077,0
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `<DATE>` = `YYYYMMDD` int, `<TIME>` = `HHMMSS` int, **naive** (no offset).
- Raw wall-clock labels (as stored): `{"15:00": 1579, "16:00": 19974, "17:00": 20275, "18:00": 20167, "19:00": 20071, "20:00": 20027, "21:00": 19956, "22:00": 18796}`
- DST test — raw first/last label per day on normal days: `{"16:00": 18364, "17:00": 768, "18:00": 225, "19:00": 97, "22:00": 67}` / `{"22:00": 18796, "20:00": 349, "21:00": 281, "19:00": 92, "18:00": 69}`; on days when US DST and EU DST disagree (2nd Sun Mar→last Sun Mar, last Sun Oct→1st Sun Nov): `{"15:00": 1579, "16:00": 75, "17:00": 18, "19:00": 10, "18:00": 10}` / `{"21:00": 1650, "20:00": 15, "18:00": 13, "17:00": 8, "16:00": 6}` (days: normal 19789, mismatch 1712). A one-hour shift in the mismatch window means the clock is **European local time (CET/CEST)**, not US time and not UTC.
- Local times that do not exist in Europe/Warsaw (spring-forward): 0
- Bar labels converted to America/New_York — first label per day: `{"10:00": 19943, "11:00": 843, "12:00": 283, "13:00": 146, "16:00": 104}`; last label per day: `{"16:00": 20446, "14:00": 377, "15:00": 298, "13:00": 152, "12:00": 106}`
- All NY-local labels (count across sample): `{"10:00": 19943, "11:00": 20279, "12:00": 20187, "13:00": 20072, "14:00": 20017, "15:00": 19901, "16:00": 20446}`
- Literal UTC probe: bars with UTC time in [08:00,13:30): 0; bars ≥ 20:00 UTC: 27057 (note: 13:00–13:30 UTC is inside RTH-hour-aligned bars in summer, so the NY-local probe below is the meaningful one)
- NY-local probe: bars labelled before 09:00 ET: 0; labelled ≥ 16:00 ET: 20446; ≥ 17:00 ET: 0
- UTC first label per day, NY summer (EDT): `{"14:00": 13230, "15:00": 544, "16:00": 185, "17:00": 89, "20:00": 44}`; NY winter (EST): `{"15:00": 6713, "16:00": 295, "17:00": 64, "18:00": 26, "21:00": 25}` → a 1-hour shift in UTC between seasons means timestamps track the US exchange clock correctly after conversion.
- Bars per NY day: `{"7": 18073, "6": 914, "5": 838, "4": 397, "3": 384}`
- Half-days in sample: `[{"2024-11-29": "5 bars, last label 14:00 ET", "2024-12-24": "5 bars, last label 14:00 ET"}, {"2024-11-29": "5 bars, last label 14:00 ET", "2024-12-24": "5 bars, last label 14:00 ET"}, {"2024-11-29": "5 bars, last label 14:00 ET", "2024-12-24": "5 bars, last label 14:00 ET"}]`
- Bars on NYSE full holidays: 0 (files with any: 0)
- Interpretation: after Warsaw→UTC→NY conversion, labels run 10:00–16:00 ET; label 16:00 ET present and 09:30 absent → labels are **bar-end** (first bar 09:30–10:00 labelled 10:00, last bar 15:00–16:00 labelled 16:00).
- Half-day caveat: on NYSE half-days (close 13:00 ET) the sample shows 5 bars with the last label 14:00 ET (20:00 CET), and in the raw files that last bar carries the day's largest volume (closing auction). A strict bar-end reading would give 4 bars ending 13:00, so how Stooq bins the closing print is not fully determined.
- `<PER>` = `{"60": 12343, "null": 39}` (60 = hourly in Stooq); `<OPENINT>` present but always 0 for stocks (see samples).

### 13–14. Adjustment / futures specifics
Split probes (previous close ÷ open on split date; ≈1 → split-adjusted, ≈factor → unadjusted):

| ticker | split | factor | prev close | open | ratio | verdict |
|---|---|---|---|---|---|---|
| NVDA | 2024-06-10 (prev 2024-06-07) | 10.0 | 120.86 | 120.342 | 1.004 | adjusted |
| CMG | 2024-06-26 (prev 2024-06-25) | 50.0 | 65.6608 | 65.81 | 0.998 | adjusted |
| AVGO | 2024-07-15 (prev 2024-07-12) | 10.0 | 169.529 | 169.443 | 1.001 | adjusted |
| SMCI | 2024-10-01 (prev 2024-09-30) | 10.0 | 41.65 | 41.75 | 0.998 | adjusted |

Cross-source close ratio vs MS-US-1D (Alpaca SIP, adjustment=all), median per year. A ratio drifting away from 1 in older years indicates a different dividend-adjustment basis; flat ≈1 means same basis:

| ticker | common days | close ratio by year | volume ratio by year |
|---|---|---|---|
| AAPL | 513 | `{"2024": 1.0009, "2025": 1.0009, "2026": 1.0009}` | `{"2024": 0.6513, "2025": 0.6603, "2026": 0.5654}` |
| MSFT | 513 | `{"2024": 1.0119, "2025": 1.008, "2026": 1.0022}` | `{"2024": 0.5457, "2025": 0.5672, "2026": 0.6187}` |
| SPY | 513 | `{"2024": 1.0141, "2025": 1.0111, "2026": 1.0027}` | `{"2024": 0.5921, "2025": 0.6426, "2026": 0.7092}` |
| KO | 513 | `{"2024": 1.0513, "2025": 1.0284, "2026": 1.0065}` | `{"2024": 0.7279, "2025": 0.7231, "2026": 0.6873}` |
| XOM | 513 | `{"2024": 1.0594, "2025": 1.0319, "2026": 1.0068}` | `{"2024": 0.6661, "2025": 0.6385, "2026": 0.6202}` |
| JPM | 513 | `{"2024": 1.0373, "2025": 1.0146, "2026": 1.005}` | `{"2024": 0.638, "2025": 0.6161, "2026": 0.6756}` |
| T | 513 | `{"2024": 1.0817, "2025": 1.0436, "2026": 1.0105}` | `{"2024": 0.8387, "2025": 0.807, "2026": 0.8091}` |
| TSLA | 513 | `{"2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2024": 0.7117, "2025": 0.7077, "2026": 0.7621}` |
| NVDA | 513 | `{"2024": 1.0015, "2025": 1.0013, "2026": 1.0012}` | `{"2024": 0.7573, "2025": 0.7349, "2026": 0.663}` |
| AMZN | 513 | `{"2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2024": 0.6744, "2025": 0.6568, "2026": 0.5874}` |
| GOOGL | 513 | `{"2024": 1.0052, "2025": 1.0029, "2026": 1.0007}` | `{"2024": 0.6155, "2025": 0.6125, "2026": 0.5512}` |
| WMT | 513 | `{"2024": 1.0158, "2025": 1.0083, "2026": 1.0022}` | `{"2024": 0.7227, "2025": 0.6976, "2026": 0.53}` |
| CMG | 513 | `{"2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2024": 0.731, "2025": 0.7533, "2026": 0.7685}` |
| AVGO | 513 | `{"2024": 1.0155, "2025": 1.0073, "2026": 1.0019}` | `{"2024": 0.6022, "2025": 0.6185, "2026": 0.6409}` |
| SMCI | 513 | `{"2024": 1.0, "2025": 1.0, "2026": 1.0}` | `{"2024": 0.622, "2025": 0.7646, "2026": 0.7238}` |

Dividend-payer drift (first-year minus last-year ratio, KO/XOM/T/JPM): `[0.0448, 0.0526, 0.0323, 0.0712]` → **split-adjusted only, NOT dividend-adjusted** (older prices sit above the dividend-adjusted SIP series by the accumulated dividends).

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 140845 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 0 |
| null_cells | 0 |
| big_moves | 131 |
| missing_bar_gaps | 326 |
| missing_day_gaps | 66 |
| zero_volume_share_median_file | 0.0 |
| zero_volume_share_max_file | 0.0 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 7 |
| files_with_nonpos_price | 0 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 34878856, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 0, "big_moves": 32441, "missing_bar_gaps": 80731}` |

_Per-file statistics computed on 50 of 12382 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: AAPL, TSLA, NVDA, AMZN, GOOGL, WMT, CMG, AVGO, SMCI, MSFT, SPY, KO, XOM, JPM, T, AADR, GPRF, SCDS, AHCO, BBYY, CECO, DJCO, FLNC, HEPS, KALV, MDXH, NUGY, PODC, SBC, TALKW, VLGEA, AOD, CTJN, FAN, HELO, KAMO, PBJ, SGDM, USEW, ACVT, BHE, COSO, EQNR, GS, KDEF, MTRN, PG, SCE_L, TPL, XXI

---

## QP-REF — QuantPlatform · reference tables (assets, market cap)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\reference` | `**/*.parquet`, `**/*.csv` | 5 | 632.7 KB | `{".csv": 2, ".parquet": 3}` |

Files per sub-folder: `{"assets": 2, "marketcap": 3}`

### 2. Probable source
**Alpaca assets endpoint (asset list) / market-cap snapshot (see downloader)**

- `pull_us_marketcap.py:8`: returns 1h bars in ~200-bar pages and *ignores* ``limit``, so ~6y of hourly
- `pull_us_marketcap.py:52`: """Symbols in descending market-cap order + a label of the ranking source.
- `pull_us_marketcap.py:59`: return marketcap_snapshot.top_symbols(top_n, as_of=as_of), f"nasdaq_snapshot_{day}"

### 3–4. Symbols & asset class
- Asset class guess: **reference data (not prices)**
- 3 symbols; first 30: us_assets_2026-06-22, us_marketcap_2026-06-22, us_marketcap_history

### Tables
| file | rows | schema | as_of values |
|---|---|---|---|
| assets\us_assets_2026-06-22.csv | 6293 | `{"symbol": "String", "name": "String", "exchange": "String", "status": "String", "tradable": "Boolean", "as_of": "String"}` | `["2026-06-22"]` |
| assets\us_assets_2026-06-22.parquet | 6293 | `{"symbol": "String", "name": "String", "exchange": "String", "status": "String", "tradable": "Boolean", "as_of": "Date"}` | `["2026-06-22"]` |
| marketcap\us_marketcap_2026-06-22.csv | 1000 | `{"as_of": "String", "rank": "Int64", "symbol": "String", "name": "String", "market_cap": "Float64", "exchange": "String"}` | `["2026-06-22"]` |
| marketcap\us_marketcap_2026-06-22.parquet | 1000 | `{"as_of": "Date", "rank": "Int32", "symbol": "String", "name": "String", "market_cap": "Float64", "exchange": "String"}` | `["2026-06-22"]` |
| marketcap\us_marketcap_history.parquet | 1000 | `{"as_of": "Date", "rank": "Int32", "symbol": "String", "name": "String", "market_cap": "Float64", "exchange": "String"}` | `["2026-06-22"]` |

Raw sample (`D:\AmerAndish\Projects\Trade\SourceCodes\QuantPlatform\data\reference\assets\us_assets_2026-06-22.csv`), head:
```
symbol,name,exchange,status,tradable,as_of
A,Agilent Technologies Inc.,NYSE,active,true,2026-06-22
AA,Alcoa Corporation,NYSE,active,true,2026-06-22
AABA,"",NASDAQ,inactive,false,2026-06-22
AACB,Artius II Acquisition Inc. Class A Ordinary Shares,NASDAQ,active,true,2026-06-22
AACI,Armada Acquisition Corp. III Class A Ordinary Share,NASDAQ,active,true,2026-06-22
```
tail:
```
ZWS,Zurn Elkay Water Solutions Corporation,NYSE,active,true,2026-06-22
ZYBT,Zhengye Biotechnology Holding Limited Class A Ordinary Shares,NASDAQ,active,true,2026-06-22
ZYME,Zymeworks Inc. Common Stock,NASDAQ,active,true,2026-06-22
```

---

## MS-US-1D — MarketScanner · US equities · daily csv (`us_<TICKER>.csv`)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles` | `us_*.csv` | 6711 | 489.4 MB | `{".csv": 6711}` |

### 2. Probable source
**Alpaca SIP (consolidated tape), adjustment=all**

- MarketScanner candle layout `date,open,high,low,close,volume` (date only).
- `host_download.py:221`: adjustment=Adjustment.ALL, feed=DataFeed.SIP,  # full consolidated tape (clean)
- `host_download_us_pit.py:11`: (delisted ones included; Alpaca's SIP tape keeps much delisted history);
- `download_sip.log:1`: [alpaca] fetching S&P 500 constituents...

### 3–4. Symbols & asset class
- Asset class guess: **US equity / ETF (S&P 500 point-in-time members + small/mid caps)**
- 6711 symbols; first 30: A, AA, AABA, AACB, AACI, AACO, AACP, AADX, AAL, AAME, AAMI, AAOI, AAON, AAP, AAPG, AAPL, AARD, AAUC, AB, ABAT, ABBV, ABC, ABCB, ABCD, ABCL, ABDC, ABEO, ABEV, ABG, ABLV

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1d** in 50 of 50 deep-sample files; the other 0 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1d": 50}`
- Most frequent spacing per file (bar grid): `{"1d": 50}` → mixed timeframes: False; median share of diffs equal to the median: 0.782

### 6. Date range
- Across all 6711 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2016-01-04 00:00:00", "median": "2016-01-04 00:00:00", "max": "2026-06-30 00:00:00"}`; last ts `{"min": "2016-01-29 00:00:00", "median": "2026-06-30 00:00:00", "max": "2026-07-01 00:00:00"}`

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\us_AAPL.csv`

`{"date": "String", "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64", "volume": "Float64"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\us_AAPL.csv`

First 5 rows (with header lines):
```
date,open,high,low,close,volume
2016-01-04,23.09,23.71,22.96,23.71,287741356.0
2016-01-05,23.8,23.82,23.05,23.11,234762144.0
2016-01-06,22.63,23.04,22.48,22.66,284319308.0
2016-01-07,22.21,22.53,21.7,21.71,343985812.0
2016-01-08,22.18,22.3,21.78,21.82,300265168.0
```
Last 3 rows:
```
2026-06-25,287.4,288.8,273.75,275.15,107450336.0
2026-06-26,275.0,285.95,274.21,283.78,261946552.0
2026-06-29,286.73,288.3697,279.85,281.64,52757952.0
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `date` column is `YYYY-MM-DD` text, no time, no zone (session date).
- Weekday distribution (sample): `{"Tue": 20403, "Wed": 20265, "Thu": 19915, "Fri": 19881, "Mon": 18465}`
- Rows on NYSE full-holiday dates `["2020-11-26", "2021-12-24", "2022-06-20", "2023-04-07", "2024-07-04", "2024-12-25", "2025-01-09", "2025-04-18"]`: 0 (files with any: 0)

### 13–14. Adjustment / futures specifics
Split probes (previous close ÷ open on split date; ≈1 → split-adjusted, ≈factor → unadjusted):

| ticker | split | factor | prev close | open | ratio | verdict |
|---|---|---|---|---|---|---|
| AAPL | 2020-08-31 (prev 2020-08-28) | 4.0 | 121.06 | 123.56 | 0.98 | adjusted |
| TSLA | 2020-08-31 (prev 2020-08-28) | 5.0 | 147.56 | 148.2 | 0.996 | adjusted |
| NVDA | 2021-07-20 (prev 2021-07-19) | 4.0 | 18.72 | 18.67 | 1.003 | adjusted |
| AMZN | 2022-06-06 (prev 2022-06-03) | 20.0 | 122.35 | 125.245 | 0.977 | adjusted |
| GOOGL | 2022-07-18 (prev 2022-07-15) | 20.0 | 110.8 | 111.65 | 0.992 | adjusted |
| TSLA | 2022-08-25 (prev 2022-08-24) | 3.0 | 297.1 | 302.36 | 0.983 | adjusted |
| WMT | 2024-02-26 (prev 2024-02-23) | 3.0 | 57.05 | 57.64 | 0.99 | adjusted |
| NVDA | 2024-06-10 (prev 2024-06-07) | 10.0 | 120.68 | 120.16 | 1.004 | adjusted |
| CMG | 2024-06-26 (prev 2024-06-25) | 50.0 | 65.66 | 65.81 | 0.998 | adjusted |
| AVGO | 2024-07-15 (prev 2024-07-12) | 10.0 | 166.93 | 166.86 | 1.0 | adjusted |
| SMCI | 2024-10-01 (prev 2024-09-30) | 10.0 | 41.64 | 41.75 | 0.997 | adjusted |

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 98929 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 0 |
| null_cells | 0 |
| big_moves | 101 |
| missing_bar_gaps | 0 |
| zero_volume_share_median_file | 0.0 |
| zero_volume_share_max_file | 0.8259 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 19 |
| files_with_nonpos_price | 0 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 13278250, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 0, "big_moves": 13556, "missing_bar_gaps": 0}` |

_Per-file statistics computed on 50 of 6711 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: AAPL, TSLA, NVDA, AMZN, GOOGL, WMT, CMG, AVGO, SMCI, MSFT, SPY, KO, XOM, JPM, T, A, AIOS, APF, AVEX, BIO_B, BULZ, CENX, CNXM, CUPR, DMAC, EGOV, EWA, FMC, GEG, GT, HQY, INDO, JOBY, LAW, LVGO, MIR, MWG, NRG, OLMA, PCP, PRG, RCAT, RUN, SHEH, SPGI, TAL, TPIV, UNG, VRSN, WSTN

---

## MS-CRYPTO-1D — MarketScanner · crypto top-100 · daily csv (`crypto_<BASE>_<QUOTE>.csv`, `gold_PAXG_USDT.csv`)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles` | `crypto_*.csv`, `gold_*.csv` | 102 | 6.3 MB | `{".csv": 102}` |

### 2. Probable source
**Binance spot via ccxt (`ccxt_binance` in manifest)**

- `download.log:1`: [crypto] loading Binance markets/tickers...

### 3–4. Symbols & asset class
- Asset class guess: **crypto (spot); PAXG = gold-backed token**
- 101 symbols; first 30: AAVE_USDT, ACT_USDT, ADA_USDT, AGLD_USDT, AIGENSYN_USDT, AI_USDT, ALGO_USDT, ALICE_USDT, ALLO_USDT, ANIME_USDT, APT_USDT, ARB_USDT, AR_USDT, ASTER_USDT, ATM_USDT, ATOM_USDT, AVAX_USDT, BCH_USDT, BFUSD_USDT, BICO_USDT, BNB_USDT, BTC_USDT, CAKE_USDT, CELO_USDT, CHZ_USDT, CRCLB_USDT, DASH_USDT, DOGE_USDT, DOT_USDT, EDEN_USDT

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1d** in 50 of 50 deep-sample files; the other 0 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1d": 50}`
- Most frequent spacing per file (bar grid): `{"1d": 50}` → mixed timeframes: False; median share of diffs equal to the median: 1.0

### 6. Date range
- Across all 102 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2017-08-17 00:00:00", "median": "2023-08-15 00:00:00", "max": "2026-06-18 00:00:00"}`; last ts `{"min": "2026-06-29 00:00:00", "median": "2026-06-29 00:00:00", "max": "2026-06-30 00:00:00"}`

| symbol | first | last | rows | size |
|---|---|---|---|---|
| AAVE_USDT | 2020-10-15 00:00:00 | 2026-06-29 00:00:00 |  | 97.1 KB |
| ACT_USDT | 2024-11-11 00:00:00 | 2026-06-29 00:00:00 |  | 29.9 KB |
| ADA_USDT | 2018-04-17 00:00:00 | 2026-06-29 00:00:00 |  | 152.8 KB |
| AGLD_USDT | 2021-10-05 00:00:00 | 2026-06-29 00:00:00 |  | 76.9 KB |
| AI_USDT | 2024-01-04 00:00:00 | 2026-06-29 00:00:00 |  | 44.0 KB |
| AIGENSYN_USDT | 2026-05-14 00:00:00 | 2026-06-29 00:00:00 |  | 2.6 KB |
| ALGO_USDT | 2019-06-22 00:00:00 | 2026-06-29 00:00:00 |  | 126.6 KB |
| ALICE_USDT | 2021-03-15 00:00:00 | 2026-06-29 00:00:00 |  | 89.5 KB |
| ALLO_USDT | 2025-11-11 00:00:00 | 2026-06-29 00:00:00 |  | 11.4 KB |
| ANIME_USDT | 2025-01-23 00:00:00 | 2026-06-29 00:00:00 |  | 28.1 KB |
| APT_USDT | 2022-10-19 00:00:00 | 2026-06-29 00:00:00 |  | 62.8 KB |
| AR_USDT | 2021-05-14 00:00:00 | 2026-06-29 00:00:00 |  | 81.2 KB |
| ARB_USDT | 2023-03-23 00:00:00 | 2026-06-29 00:00:00 |  | 59.1 KB |
| ASTER_USDT | 2025-10-06 00:00:00 | 2026-06-29 00:00:00 |  | 12.4 KB |
| ATM_USDT | 2020-12-30 00:00:00 | 2026-06-29 00:00:00 |  | 87.6 KB |
| ATOM_USDT | 2019-04-29 00:00:00 | 2026-06-29 00:00:00 |  | 120.8 KB |
| AVAX_USDT | 2020-09-22 00:00:00 | 2026-06-29 00:00:00 |  | 96.4 KB |
| BCH_USDT | 2019-11-28 00:00:00 | 2026-06-29 00:00:00 |  | 112.1 KB |
| BFUSD_USDT | 2025-08-13 00:00:00 | 2026-06-29 00:00:00 |  | 15.5 KB |
| BICO_USDT | 2021-12-09 00:00:00 | 2026-06-29 00:00:00 |  | 80.2 KB |
| BNB_USDT | 2017-11-06 00:00:00 | 2026-06-29 00:00:00 |  | 153.9 KB |
| BTC_USDT | 2017-08-17 00:00:00 | 2026-06-29 00:00:00 |  | 184.4 KB |
| CAKE_USDT | 2021-02-19 00:00:00 | 2026-06-29 00:00:00 |  | 89.0 KB |
| CELO_USDT | 2021-01-05 00:00:00 | 2026-06-29 00:00:00 |  | 93.7 KB |
| CHZ_USDT | 2019-09-06 00:00:00 | 2026-06-29 00:00:00 |  | 131.3 KB |
| CRCLB_USDT | 2026-06-11 00:00:00 | 2026-06-29 00:00:00 |  | 863.0 B |
| DASH_USDT | 2019-03-28 00:00:00 | 2026-06-29 00:00:00 |  | 121.4 KB |
| DOGE_USDT | 2019-07-05 00:00:00 | 2026-06-29 00:00:00 |  | 142.4 KB |
| DOT_USDT | 2020-08-18 00:00:00 | 2026-06-29 00:00:00 |  | 98.5 KB |
| EDEN_USDT | 2025-09-30 00:00:00 | 2026-06-29 00:00:00 |  | 13.5 KB |
| EIGEN_USDT | 2024-10-01 00:00:00 | 2026-06-29 00:00:00 |  | 29.6 KB |
| ENA_USDT | 2024-04-02 00:00:00 | 2026-06-29 00:00:00 |  | 41.0 KB |
| ETH_USDT | 2017-08-17 00:00:00 | 2026-06-29 00:00:00 |  | 170.6 KB |
| FET_USDT | 2019-02-28 00:00:00 | 2026-06-29 00:00:00 |  | 132.5 KB |
| FIL_USDT | 2020-10-15 00:00:00 | 2026-06-29 00:00:00 |  | 95.6 KB |
| G_USDT | 2024-07-19 00:00:00 | 2026-06-29 00:00:00 |  | 38.1 KB |
| GAS_USDT | 2023-03-17 00:00:00 | 2026-06-29 00:00:00 |  | 52.3 KB |
| HBAR_USDT | 2019-09-29 00:00:00 | 2026-06-29 00:00:00 |  | 127.4 KB |
| HEI_USDT | 2025-02-13 00:00:00 | 2026-06-29 00:00:00 |  | 24.4 KB |
| HYPER_USDT | 2025-04-22 00:00:00 | 2026-06-29 00:00:00 |  | 21.3 KB |
| ICP_USDT | 2021-05-11 00:00:00 | 2026-06-29 00:00:00 |  | 85.0 KB |
| ID_USDT | 2023-03-22 00:00:00 | 2026-06-29 00:00:00 |  | 60.1 KB |
| INJ_USDT | 2020-10-21 00:00:00 | 2026-06-29 00:00:00 |  | 93.7 KB |
| JST_USDT | 2020-08-11 00:00:00 | 2026-06-29 00:00:00 |  | 115.0 KB |
| JTO_USDT | 2023-12-07 00:00:00 | 2026-06-29 00:00:00 |  | 42.9 KB |
| KITE_USDT | 2025-11-03 00:00:00 | 2026-06-29 00:00:00 |  | 11.9 KB |
| LINK_USDT | 2019-01-16 00:00:00 | 2026-06-29 00:00:00 |  | 128.1 KB |
| LTC_USDT | 2017-12-13 00:00:00 | 2026-06-29 00:00:00 |  | 147.0 KB |
| MAGIC_USDT | 2022-12-12 00:00:00 | 2026-06-29 00:00:00 |  | 63.3 KB |
| MANTA_USDT | 2024-01-18 00:00:00 | 2026-06-29 00:00:00 |  | 42.2 KB |
| MEGA_USDT | 2026-04-30 00:00:00 | 2026-06-29 00:00:00 |  | 3.3 KB |
| MUB_USDT | 2026-06-11 00:00:00 | 2026-06-29 00:00:00 |  | 1007.0 B |
| NEAR_USDT | 2020-10-14 00:00:00 | 2026-06-29 00:00:00 |  | 95.6 KB |
| NFP_USDT | 2023-12-27 00:00:00 | 2026-06-29 00:00:00 |  | 45.9 KB |
| NIGHT_USDT | 2026-03-11 00:00:00 | 2026-06-29 00:00:00 |  | 6.0 KB |
| ONDO_USDT | 2025-04-11 00:00:00 | 2026-06-29 00:00:00 |  | 21.9 KB |
| ORCA_USDT | 2024-12-06 00:00:00 | 2026-06-29 00:00:00 |  | 25.6 KB |
| ORDI_USDT | 2023-11-07 00:00:00 | 2026-06-29 00:00:00 |  | 43.8 KB |
| PAXG_USDT | 2020-08-28 00:00:00 | 2026-06-29 00:00:00 |  | 106.4 KB |
| PENDLE_USDT | 2023-07-03 00:00:00 | 2026-06-29 00:00:00 |  | 49.7 KB |
| PENGU_USDT | 2024-12-17 00:00:00 | 2026-06-29 00:00:00 |  | 33.0 KB |
| PEPE_USDT | 2023-05-05 00:00:00 | 2026-06-29 00:00:00 |  | 73.1 KB |
| POL_USDT | 2024-09-13 00:00:00 | 2026-06-29 00:00:00 |  | 32.6 KB |
| POWR_USDT | 2021-11-17 00:00:00 | 2026-06-29 00:00:00 |  | 81.9 KB |
| PUMP_USDT | 2025-09-11 00:00:00 | 2026-06-29 00:00:00 |  | 17.4 KB |
| PYTH_USDT | 2024-02-02 00:00:00 | 2026-06-29 00:00:00 |  | 43.5 KB |
| RE_USDT | 2026-06-18 00:00:00 | 2026-06-29 00:00:00 |  | 636.0 B |
| RENDER_USDT | 2024-07-26 00:00:00 | 2026-06-29 00:00:00 |  | 32.0 KB |
| RESOLV_USDT | 2025-06-11 00:00:00 | 2026-06-29 00:00:00 |  | 19.0 KB |
| RLUSD_USDT | 2026-01-22 00:00:00 | 2026-06-29 00:00:00 |  | 7.7 KB |
| S_USDT | 2025-01-16 00:00:00 | 2026-06-29 00:00:00 |  | 26.8 KB |
| SEI_USDT | 2023-08-15 00:00:00 | 2026-06-29 00:00:00 |  | 52.6 KB |
| SHIB_USDT | 2021-05-10 00:00:00 | 2026-06-29 00:00:00 |  | 120.9 KB |
| SNDKB_USDT | 2026-06-11 00:00:00 | 2026-06-29 00:00:00 |  | 1.0 KB |
| SOL_USDT | 2020-08-11 00:00:00 | 2026-06-29 00:00:00 |  | 103.2 KB |
| SPCXB_USDT | 2026-06-12 00:00:00 | 2026-06-29 00:00:00 |  | 931.0 B |
| STG_USDT | 2022-08-19 00:00:00 | 2026-06-29 00:00:00 |  | 68.7 KB |
| SUI_USDT | 2023-05-03 00:00:00 | 2026-06-29 00:00:00 |  | 56.9 KB |
| SYN_USDT | 2023-02-22 00:00:00 | 2026-06-29 00:00:00 |  | 59.3 KB |
| TAO_USDT | 2024-04-11 00:00:00 | 2026-06-29 00:00:00 |  | 37.5 KB |
| TIA_USDT | 2023-10-31 00:00:00 | 2026-06-29 00:00:00 |  | 45.4 KB |
| TON_USDT | 2024-08-08 00:00:00 | 2026-06-29 00:00:00 |  | 31.5 KB |
| TRUMP_USDT | 2025-01-19 00:00:00 | 2026-06-29 00:00:00 |  | 24.1 KB |
| TRX_USDT | 2018-06-11 00:00:00 | 2026-06-29 00:00:00 |  | 157.2 KB |
| TURBO_USDT | 2024-09-16 00:00:00 | 2026-06-29 00:00:00 |  | 38.4 KB |
| U_USDT | 2026-01-13 00:00:00 | 2026-06-29 00:00:00 |  | 8.1 KB |
| UNI_USDT | 2020-09-17 00:00:00 | 2026-06-29 00:00:00 |  | 96.7 KB |
| USD1_USDT | 2025-05-22 00:00:00 | 2026-06-29 00:00:00 |  | 19.9 KB |
| VANA_USDT | 2024-12-16 00:00:00 | 2026-06-29 00:00:00 |  | 25.2 KB |
| WBTC_USDT | 2023-04-28 00:00:00 | 2026-06-29 00:00:00 |  | 64.7 KB |
| WIF_USDT | 2024-03-05 00:00:00 | 2026-06-29 00:00:00 |  | 39.9 KB |
| WLD_USDT | 2023-07-24 00:00:00 | 2026-06-29 00:00:00 |  | 49.4 KB |
| WLFI_USDT | 2025-09-01 00:00:00 | 2026-06-29 00:00:00 |  | 15.1 KB |
| XAUT_USDT | 2026-03-26 00:00:00 | 2026-06-29 00:00:00 |  | 5.0 KB |
| XLM_USDT | 2018-05-31 00:00:00 | 2026-06-29 00:00:00 |  | 150.8 KB |
| XPL_USDT | 2025-09-25 00:00:00 | 2026-06-29 00:00:00 |  | 13.9 KB |
| XRP_USDT | 2018-05-04 00:00:00 | 2026-06-29 00:00:00 |  | 152.7 KB |
| XUSD_USDT | 2025-03-19 00:00:00 | 2026-06-29 00:00:00 |  | 22.4 KB |
| ZEC_USDT | 2019-03-21 00:00:00 | 2026-06-29 00:00:00 |  | 121.7 KB |
| ZRO_USDT | 2024-06-20 00:00:00 | 2026-06-29 00:00:00 |  | 33.6 KB |
| 币安人生_USDT | 2026-01-07 00:00:00 | 2026-06-29 00:00:00 |  | 8.6 KB |
| PAXG_USDT | 2020-08-28 00:00:00 | 2026-06-30 00:00:00 |  | 106.4 KB |

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\crypto_BTC_USDT.csv`

`{"date": "String", "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64", "volume": "Float64"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\crypto_BTC_USDT.csv`

First 5 rows (with header lines):
```
date,open,high,low,close,volume
2017-08-17,4261.48,4485.39,4200.74,4285.08,795.150377
2017-08-18,4285.08,4371.52,3938.77,4108.37,1199.888264
2017-08-19,4108.37,4184.69,3850.0,4139.98,381.309763
2017-08-20,4120.98,4211.08,4032.62,4086.29,467.083022
2017-08-21,4069.13,4119.62,3911.79,4016.0,691.74306
```
Last 3 rows:
```
2026-06-27,60097.27,60941.17,59855.16,60029.0,9587.22916
2026-06-28,60029.01,60545.01,58905.0,59577.01,8907.13796
2026-06-29,59577.01,60780.57,58900.01,60432.75,19284.22468
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `date` text `YYYY-MM-DD`, no time/zone. Binance daily candles open 00:00 UTC → date = UTC day (convention, not verifiable from file).
- Weekday distribution: `{"Mon": 9847, "Sun": 9842, "Sat": 9841, "Fri": 9840, "Thu": 9832, "Wed": 9816, "Tue": 9806}` → 7-day week.

### 13–14. Adjustment / futures specifics

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 68824 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 0 |
| null_cells | 0 |
| big_moves | 221 |
| missing_bar_gaps | 0 |
| zero_volume_share_median_file | 0.0 |
| zero_volume_share_max_file | 0.0 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 39 |
| files_with_nonpos_price | 0 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 140401, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 0, "big_moves": 451, "missing_bar_gaps": 0}` |

_Per-file statistics computed on 50 of 102 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: BTC_USDT, ETH_USDT, PAXG_USDT, AAVE_USDT, ADA_USDT, AI_USDT, ALGO_USDT, ALLO_USDT, APT_USDT, ARB_USDT, ATM_USDT, AVAX_USDT, BFUSD_USDT, CAKE_USDT, CHZ_USDT, DASH_USDT, DOT_USDT, EIGEN_USDT, FET_USDT, G_USDT, HBAR_USDT, HYPER_USDT, INJ_USDT, JTO_USDT, LINK_USDT, MAGIC_USDT, MEGA_USDT, NEAR_USDT, NIGHT_USDT, ORCA_USDT, PENDLE_USDT, PEPE_USDT, PUMP_USDT, RE_USDT, RESOLV_USDT, S_USDT, SHIB_USDT, SOL_USDT, STG_USDT, SYN_USDT, TIA_USDT, TRX_USDT, U_USDT, USD1_USDT, WBTC_USDT, WLD_USDT, XAUT_USDT, XPL_USDT, XUSD_USDT, ZRO_USDT

---

## MS-PIT-CRYPTO-1D — MarketScanner · crypto point-in-time universe (incl. delisted) · daily csv (`pit_<BASE>_<QUOTE>.csv`)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles` | `pit_*.csv` | 601 | 36.0 MB | `{".csv": 601}` |

### 2. Probable source
**Binance spot via ccxt (point-in-time universe incl. delisted)**

- `pit_download.log:2`: 22:13:20 [pit] 601 USDT spot symbols (422 active, 179 delisted)
- `pit_download.log:3`: 22:13:24 [pit] 9/601 A2Z/USDT: 246 bars 2025-07-30..2026-04-01 [delisted]

### 3–4. Symbols & asset class
- Asset class guess: **crypto (spot), includes delisted pairs**
- 601 symbols; first 30: 0G_USDT, 1000CAT_USDT, 1000CHEEMS_USDT, 1000SATS_USDT, 1INCH_USDT, 1MBABYDOGE_USDT, 2Z_USDT, A2Z_USDT, AAVE_USDT, ACA_USDT, ACE_USDT, ACH_USDT, ACM_USDT, ACT_USDT, ACX_USDT, ADA_USDT, ADX_USDT, AERGO_USDT, AEVO_USDT, AGIX_USDT, AGLD_USDT, AIGENSYN_USDT, AION_USDT, AIXBT_USDT, AI_USDT, AKRO_USDT, ALCX_USDT, ALGO_USDT, ALICE_USDT, ALLO_USDT

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1d** in 50 of 50 deep-sample files; the other 0 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1d": 50}`
- Most frequent spacing per file (bar grid): `{"1d": 50}` → mixed timeframes: False; median share of diffs equal to the median: 1.0

### 6. Date range
- Across all 601 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2017-08-17 00:00:00", "median": "2021-12-01 00:00:00", "max": "2026-06-30 00:00:00"}`; last ts `{"min": "2018-10-19 00:00:00", "median": "2026-06-30 00:00:00", "max": "2026-06-30 00:00:00"}`

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\pit_BTC_USDT.csv`

`{"date": "String", "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64", "volume": "Float64"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\pit_BTC_USDT.csv`

First 5 rows (with header lines):
```
date,open,high,low,close,volume
2017-08-17,4261.48,4485.39,4200.74,4285.08,795.150377
2017-08-18,4285.08,4371.52,3938.77,4108.37,1199.888264
2017-08-19,4108.37,4184.69,3850.0,4139.98,381.309763
2017-08-20,4120.98,4211.08,4032.62,4086.29,467.083022
2017-08-21,4069.13,4119.62,3911.79,4016.0,691.74306
```
Last 3 rows:
```
2026-06-28,60029.01,60545.01,58905.0,59577.01,8907.13796
2026-06-29,59577.01,60780.57,58900.01,60260.21,20203.14178
2026-06-30,60260.2,60276.54,58201.0,58447.48,17174.26203
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `date` text `YYYY-MM-DD`, no time/zone. Binance daily candles open 00:00 UTC → date = UTC day (convention, not verifiable from file).
- Weekday distribution: `{"Mon": 8801, "Tue": 8801, "Fri": 8796, "Sun": 8796, "Sat": 8795, "Thu": 8781, "Wed": 8773}` → 7-day week.

### 13–14. Adjustment / futures specifics

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 61543 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 0 |
| null_cells | 0 |
| big_moves | 328 |
| missing_bar_gaps | 1 |
| zero_volume_share_median_file | 0.0 |
| zero_volume_share_max_file | 0.0 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 50 |
| files_with_nonpos_price | 0 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 739747, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 0, "big_moves": 3943, "missing_bar_gaps": 12}` |

_Per-file statistics computed on 50 of 601 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: BTC_USDT, ETH_USDT, 0G_USDT, ACH_USDT, AION_USDT, AMP_USDT, ARK_USDT, AUTO_USDT, BANANAS31_USDT, BERA_USDT, BNT_USDT, BTTC_USDT, CGPT_USDT, COTI_USDT, D_USDT, DODO_USDT, EIGEN_USDT, ESP_USDT, FIRO_USDT, FTT_USDT, GLMR_USDT, HBAR_USDT, HOOK_USDT, IO_USDT, KAITO_USDT, KP3R_USDT, LIT_USDT, LUNC_USDT, MDX_USDT, MITO_USDT, MULTI_USDT, NKN_USDT, OGN_USDT, OPN_USDT, PERP_USDT, POLY_USDT, PYTH_USDT, RE_USDT, RNDR_USDT, SANTOS_USDT, SLF_USDT, SRM_USDT, SUI_USDT, THE_USDT, TROY_USDT, UFT_USDT, VGX_USDT, WAXP_USDT, XEM_USDT, YFII_USDT

---

## MS-IRAN-1D — MarketScanner · Tehran Stock Exchange / Farabourse · daily csv (`iran_<insCode>.csv`)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles` | `iran_*.csv` | 2365 | 103.4 MB | `{".csv": 2365}` |

### 2. Probable source
**TSETMC via pytse (MarketScanner pytse adapter)**

- File names are TSETMC instrument codes (`insCode`, 15–17 digits); `iran_meta.csv` maps them to Persian tickers.
- `pytse_adapter.py:1`: """Tehran Stock Exchange adapter (pytse-client). docs/03.
- `pytse_adapter.py:4`: pytse-client; raises so ingestion falls back. source_ticker should be an insCode.

### 3–4. Symbols & asset class
- Asset class guess: **Iranian equities, funds, sukuk/bonds (TSETMC instruments)**
- 2365 symbols; first 30: 10024128313803797, 10037611053902482, 10055255678920880, 10063040211859748, 10070292368370183, 10114441830266109, 10120557300120078, 10142453198848277, 10145129193828624, 10157407031358922, 10168197471714005, 10171945867136336, 10179978108591088, 10191122735393627, 10236455588057352, 10240063580556346, 10263462800402379, 10293344792627622, 10316175498056378, 10368700486623325, 10384618024725647, 10411249540376641, 10458396610199724, 10495792182142221, 1050751214677134, 10535841469368706, 10539309828675064, 10568944722570445, 10623013976366443, 10654052153538617

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1d** in 34 of 50 deep-sample files; the other 12 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1d": 34, "5760min": 1, "4320min": 2, "2880min": 3, "187200min": 1, "18720min": 1, "11520min": 1, "26640min": 1, "14400min": 1, "9360min": 1}`
- Most frequent spacing per file (bar grid): `{"1d": 42, "18720min": 1, "2880min": 2, "8640min": 1}` → mixed timeframes: True; median share of diffs equal to the median: 0.726

### 6. Date range
- Across all 2365 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2001-03-25 00:00:00", "median": "2021-11-21 00:00:00", "max": "2026-06-30 00:00:00"}`; last ts `{"min": "2002-02-20 00:00:00", "median": "2026-06-29 00:00:00", "max": "2026-06-30 00:00:00"}`

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\iran_10024128313803797.csv`

`{"date": "String", "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64", "volume": "Int64"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketScanner\data\candles\iran_10024128313803797.csv`

First 5 rows (with header lines):
```
date,open,high,low,close,volume
2016-09-21,64.0,64.0,64.0,64.0,19998800
2016-09-24,67.0,67.0,67.0,67.0,12126
2016-09-25,71.0,71.0,71.0,71.0,20772
2016-09-26,74.0,74.0,74.0,74.0,16617
2016-09-27,78.0,78.0,78.0,78.0,53236
```
Last 3 rows:
```
2026-06-27,9190.0,9190.0,8670.0,8960.0,22987589
2026-06-28,8700.0,8700.0,8700.0,8700.0,9470850
2026-06-29,8440.0,8900.0,8440.0,8560.0,24694984
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `date` text `YYYY-MM-DD` (Gregorian), no time/zone.
- Weekday distribution: `{"Mon": 11485, "Tue": 11459, "Sun": 11434, "Wed": 11328, "Sat": 11308, "Thu": 2, "Fri": 2}` → Tehran trading week (Sat–Wed); Thu/Fri rows indicate calendar changes or data artefacts.

### 13–14. Adjustment / futures specifics
- No well-known split probes exist for TSE. Proxy: 14 of 50 sampled files have ≥1 day-to-day close move > 30%, although TSE daily price limits are a few percent → capital increases/dividends appear as raw jumps → **likely unadjusted** (to confirm).

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 57018 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 4797 |
| nonpos_price | 67 |
| null_cells | 0 |
| big_moves | 80 |
| missing_bar_gaps | 1447 |
| zero_volume_share_median_file | 0.0 |
| zero_volume_share_max_file | 0.0163 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 14 |
| files_with_nonpos_price | 1 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 2696951, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 3169, "big_moves": 3784, "missing_bar_gaps": 68443}` |

_Per-file statistics computed on 50 of 2365 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: 10024128313803797, 11183410572675415, 12629673694762396, 13611044044646901, 15282093177363578, 16662877137476564, 18156575395080321, 19471788163911687, 20873934702328320, 22312990497291517, 23388683009944895, 24734871905109354, 25752723009842207, 27218386411183410, 28593434160948209, 30215634246748564, 31379272181300633, 33183654527551177, 3427503698999958, 35507785435505060, 36859999022477632, 38005238879860126, 39547351123710395, 41189775395878190, 42332199752511923, 43622578471330344, 44891482026867833, 45801323230963889, 47168887381720497, 48365538791053765, 49776615757150035, 50949399050647500, 52220424531578944, 53540719015375371, 55254206302462116, 56696444516569719, 58064045425283570, 59266699437480384, 6043384171800349, 61897635367671179, 63257581642957045, 64619251116188373, 65736765815044639, 66682662312253625, 67979306676078989, 6941522258800628, 71051000490303906, 7483280423474368, 8646067353086740, idx_15508900928481581

---

## ME-FUT-15M — MarketEdge · US futures continuous contracts · 15-min txt (`Data Export,@SYM, 15min.txt`)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `D:\AmerAndish\Projects\Trade\SourceCodes\MarketEdge\Data\Futures` | `*.txt` | 65 | 888.9 MB | `{".txt": 65}` |

### 2. Probable source
**TradeStation (or MultiCharts) chart export via 'Data Exporter v3.0' indicator**

- `@` prefix continuous symbols (`@ES`, `@CL`, `@ES.D`) are TradeStation's continuous-contract convention; header fields `$/Big Point`, `S.Start`, `S.End`, `#Ticks/Point` are TradeStation/EasyLanguage terms.
- `futures.py:3`: Our universe is DATED, vendor back-adjusted continuous contracts (roll already
- `futures.py:4`: done; adjustment = back_adjusted). Two consequences enforced elsewhere:

### 3–4. Symbols & asset class
- Asset class guess: **futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto)**
- 65 symbols; first 30: @AD, @BO, @BP, @BTC, @BTM, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC, @KW, @LC, @LH, @M2K

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **15m** in 50 of 50 deep-sample files; the other 0 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"15m": 50}`
- Most frequent spacing per file (bar grid): `{"15m": 50}` → mixed timeframes: False; median share of diffs equal to the median: 0.964

### 6. Date range
- Across all 65 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2006-01-03 19:30:00", "median": "2006-01-05 21:30:00", "max": "2021-12-08 08:00:00"}`; last ts `{"min": "2023-05-19 16:00:00", "median": "2023-11-01 16:00:00", "max": "2023-11-01 17:00:00"}`

| symbol | description | tag | exch | S.Start | S.End | $/pt | tick | first | last | size |
|---|---|---|---|---|---|---|---|---|---|---|
| @AD | Australian Dollar Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 100000 | 0.00005 | 2006-01-03 19:30:00 | 2023-11-01 16:00:00 | 21.6 MB |
| @BO | Soybean Oil Continuous Contract [Dec23] | Dec23 | CBOT | 1900 | 1320 | 600 | 0.01 | 2006-01-08 19:45:00 | 2023-11-01 13:20:00 | 11.9 MB |
| @BP | British Pound Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-01-03 19:30:00 | 2023-11-01 16:00:00 | 19.9 MB |
| @BTC | Bitcoin Futures based on BRR Continuous Contract... | — | CME | 1700 | 1600 | 5 | 5 | 2017-12-19 00:30:00 | 2023-11-01 16:00:00 | 5.8 MB |
| @BTM | Bakkt Bitcoin Monthly Futures Continuous Contrac... | — | ICEUS | 2000 | 1800 | 1 | 2.5 | 2019-09-27 07:15:00 | 2023-08-14 11:45:00 | 2.0 MB |
| @C | Corn Continuous Contract [Dec23] | Dec23 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-01-05 03:15:00 | 2023-11-01 13:20:00 | 13.8 MB |
| @CC | Cocoa Continuous Contract [Mar24] | Mar24 | ICEUS | 445 | 1330 | 10 | 1 | 2006-01-11 09:00:00 | 2023-11-01 13:30:00 | 5.7 MB |
| @CD | Canadian Dollar Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 100000 | 0.00005 | 2006-01-03 19:45:00 | 2023-11-01 16:00:00 | 21.4 MB |
| @CL | Crude Oil Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 1000 | 0.01 | 2006-01-04 03:30:00 | 2023-11-01 17:00:00 | 19.0 MB |
| @CT | Cotton No. 2 Continuous Contract [Mar24] | Mar24 | ICEUS | 2100 | 1420 | 500 | 0.01 | 2006-01-11 12:15:00 | 2023-11-01 14:20:00 | 11.7 MB |
| @DX | U.S. Dollar Index Continuous Contract [Dec23] | Dec23 | ICEUS | 2000 | 1700 | 1000 | 0.005 | 2006-01-11 20:45:00 | 2023-11-01 17:00:00 | 16.4 MB |
| @E7 | E-Mini Euro FX Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-01-03 20:15:00 | 2023-11-01 16:00:00 | 18.7 MB |
| @EC | Euro FX Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-01-03 19:30:00 | 2023-11-01 16:00:00 | 21.8 MB |
| @ED | Eurodollar Continuous Contract [Sep23] | Sep23 | CME | 1700 | 1600 | 2500 | 0.0025 | 2006-01-04 05:30:00 | 2023-05-19 16:00:00 | 17.0 MB |
| @EMD | E-Mini S&P MidCap 400 Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 100 | 0.1 | 2006-01-04 17:15:00 | 2023-11-01 16:00:00 | 14.1 MB |
| @ES | E-mini S&P 500 Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 50 | 0.25 | 2006-01-03 20:00:00 | 2023-11-01 16:00:00 | 21.7 MB |
| @ES.D | E-mini S&P 500 Continuous Contract [Dec23] | Dec23 | CME | 830 | 1515 | 50 | 0.25 | 2006-01-06 13:45:00 | 2023-11-01 15:15:00 | 6.4 MB |
| @ETH | CME Ether Futures Continuous Contract [Nov23] | Nov23 | CME | 1700 | 1600 | 50 | 0.5 | 2021-02-09 17:15:00 | 2023-11-01 16:00:00 | 2.9 MB |
| @FC | Feeder Cattle Continuous Contract [Jan24] | Jan24 | CME | 830 | 1305 | 500 | 0.025 | 2007-02-02 11:15:00 | 2023-11-01 13:05:00 | 3.8 MB |
| @FV | 5 Yr U.S.Treasury Notes Continuous Contract [Dec23] | Dec23 | CBOT | 1700 | 1600 | 1000 | 0.0078125 | 2006-01-03 23:30:00 | 2023-11-01 16:00:00 | 27.3 MB |
| @GC | Gold Continuous Contract [Dec23] | Dec23 | COMEX | 1800 | 1700 | 100 | 0.1 | 2006-01-04 03:15:00 | 2023-11-01 17:00:00 | 19.8 MB |
| @HG | Copper Continuous Contract [Dec23] | Dec23 | COMEX | 1800 | 1700 | 25000 | 0.0005 | 2006-01-04 19:30:00 | 2023-11-01 17:00:00 | 19.1 MB |
| @HO | Heating Oil Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 42000 | 0.0001 | 2006-01-11 07:30:00 | 2023-11-01 17:00:00 | 17.9 MB |
| @J7 | E-Mini Japanese Yen Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-01-17 05:45:00 | 2023-11-01 16:00:00 | 12.9 MB |
| @JY | Japanese Yen Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-01-03 19:30:00 | 2023-11-01 16:00:00 | 21.7 MB |
| @KC | Coffee C Continuous Contract [Mar24] | Mar24 | ICEUS | 415 | 1330 | 375 | 0.05 | 2006-01-11 12:15:00 | 2023-11-01 13:30:00 | 7.2 MB |
| @KW | Hard Red Winter Wheat Continuous Contract [Dec23] | Dec23 | CBOT | 1900 | 1320 | 50 | 0.25 | 2008-05-05 12:30:00 | 2023-11-01 13:20:00 | 10.4 MB |
| @LC | Live Cattle Continuous Contract [Feb24] | Feb24 | CME | 830 | 1305 | 400 | 0.025 | 2006-01-13 11:45:00 | 2023-11-01 13:05:00 | 4.2 MB |
| @LH | Lean Hogs Continuous Contract [Dec23] | Dec23 | CME | 830 | 1305 | 400 | 0.025 | 2006-01-13 10:30:00 | 2023-11-01 13:05:00 | 4.0 MB |
| @M2K | Micro E-mini Russell 2000 Continuous Contract [D... | — | CME | 1700 | 1600 | 5 | 0.1 | 2006-01-03 23:30:00 | 2023-11-01 16:00:00 | 18.1 MB |
| @MBT | Micro Bitcoin Futures Continuous Contract [Nov23] | Nov23 | CME | 1700 | 1600 | 0 | 5 | 2021-05-03 20:30:00 | 2023-11-01 16:00:00 | 2.5 MB |
| @MCL | Micro Crude Oil Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 100 | 0.01 | 2021-07-12 20:30:00 | 2023-11-01 17:00:00 | 2.4 MB |
| @MES | Micro E-mini S&P 500 Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 5 | 0.25 | 2006-01-03 20:00:00 | 2023-11-01 16:00:00 | 21.7 MB |
| @MET | Micro Ether Futures Continuous Contract [Nov23] | Nov23 | CME | 1700 | 1600 | 0 | 0.5 | 2021-12-08 08:00:00 | 2023-11-01 16:00:00 | 1.6 MB |
| @MNQ | Micro E-mini Nasdaq-100 Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 2 | 0.25 | 2006-01-03 20:00:00 | 2023-11-01 16:00:00 | 21.7 MB |
| @MP1 | Mexican Peso Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 500000 | 0.00001 | 2006-01-05 11:45:00 | 2023-11-01 16:00:00 | 17.9 MB |
| @MYM | Micro E-mini Dow Continuous Contract [Dec23] | Dec23 | CBOT | 1700 | 1600 | 0 | 1 | 2006-01-03 22:00:00 | 2023-11-01 16:00:00 | 17.7 MB |
| @NE1 | New Zealand Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 100000 | 0.00005 | 2013-10-02 12:00:00 | 2023-11-01 16:00:00 | 12.1 MB |
| @NG | Natural Gas Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 10000 | 0.001 | 2006-01-04 08:45:00 | 2023-11-01 17:00:00 | 17.9 MB |
| @NK | Nikkei 225 USD Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 5 | 5 | 2006-07-26 03:15:00 | 2023-11-01 16:00:00 | 15.0 MB |
| @NQ | E-Mini NASDAQ-100 Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 20 | 0.25 | 2006-01-03 20:00:00 | 2023-11-01 16:00:00 | 21.7 MB |
| @NQ.D | E-Mini NASDAQ-100 Continuous Contract [Dec23] | Dec23 | CME | 830 | 1515 | 20 | 0.25 | 2006-01-06 13:45:00 | 2023-11-01 15:15:00 | 6.4 MB |
| @O | Oats Continuous Contract [Dec23] | Dec23 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-02-20 23:45:00 | 2023-11-01 13:20:00 | 5.6 MB |
| @OJ | Frozen Concentrated OJ Continuous Contract [Jan24] | Jan24 | ICEUS | 800 | 1400 | 150 | 0.05 | 2006-01-11 13:15:00 | 2023-11-01 14:00:00 | 4.4 MB |
| @PL | Platinum Continuous Contract [Jan24] | Jan24 | NYMEX | 1800 | 1700 | 50 | 0.1 | 2006-01-11 19:00:00 | 2023-11-01 17:00:00 | 16.9 MB |
| @QH | E-mini Heating Oil Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 21000 | 0.001 | 2006-01-23 10:30:00 | 2023-11-01 14:45:00 | 433.9 KB |
| @QM | E-mini Crude Oil Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 500 | 0.025 | 2006-01-03 23:15:00 | 2023-11-01 17:00:00 | 20.1 MB |
| @QN | miNY Natural Gas Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 2500 | 0.005 | 2006-01-04 04:15:00 | 2023-11-01 17:00:00 | 14.9 MB |
| @QU | E-mini Gasoline Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 21000 | 0.001 | 2006-01-24 02:00:00 | 2023-11-01 14:45:00 | 174.0 KB |
| @RB | NYHarborBlendstock RBOB Continuous Contract [Dec23] | Dec23 | NYMEX | 1800 | 1700 | 42000 | 0.0001 | 2006-01-04 23:15:00 | 2023-11-01 17:00:00 | 17.3 MB |
| @RR | Rough Rice Continuous Contract [Jan24] | Jan24 | CBOT | 1900 | 1320 | 2000 | 0.005 | 2006-04-24 23:30:00 | 2023-11-01 13:20:00 | 5.1 MB |
| @RTY | Emini Russell 2000 Idx Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 50 | 0.1 | 2006-01-03 23:30:00 | 2023-11-01 16:00:00 | 18.1 MB |
| @S | Soybeans Continuous Contract [Jan24] | Jan24 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-01-05 01:00:00 | 2023-11-01 13:20:00 | 14.0 MB |
| @SB | Sugar No. 11 Continuous Contract [Mar24] | Mar24 | ICEUS | 330 | 1300 | 1120 | 0.01 | 2006-01-12 11:00:00 | 2023-11-01 13:00:00 | 6.8 MB |
| @SF | Swiss Franc Continuous Contract [Dec23] | Dec23 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-01-03 20:15:00 | 2023-11-01 16:00:00 | 21.1 MB |
| @SI | Silver Continuous Contract [Dec23] | Dec23 | COMEX | 1800 | 1700 | 5000 | 0.005 | 2006-01-04 04:15:00 | 2023-11-01 17:00:00 | 19.4 MB |
| @SM | Soybean Meal Continuous Contract [Dec23] | Dec23 | CBOT | 1900 | 1320 | 100 | 0.1 | 2006-01-09 03:45:00 | 2023-11-01 13:20:00 | 11.8 MB |
| @TU | 2 Year U.S. Treasury Notes Continuous Contract [... | — | CBOT | 1700 | 1600 | 2000 | 0.00390625 | 2006-01-04 04:00:00 | 2023-11-01 16:00:00 | 27.5 MB |
| @TY | 10 Yr U.S. Treasury Notes Continuous Contract [D... | — | CBOT | 1700 | 1600 | 1000 | 0.015625 | 2006-01-03 21:45:00 | 2023-11-01 16:00:00 | 26.0 MB |
| @US | 30 Yr U.S.Treasury Bonds Continuous Contract [De... | — | CBOT | 1700 | 1600 | 1000 | 0.03125 | 2006-01-03 22:00:00 | 2023-11-01 16:00:00 | 24.1 MB |
| @VX | CBOE Volatility Index Continuous Contract [Dec23] | Dec23 | CBOEF | 1700 | 1600 | 1000 | 0.05 | 2010-01-07 15:45:00 | 2023-11-01 16:00:00 | 10.8 MB |
| @VXM | Mini-VIX Futures Continuous Contract [Dec23] | Dec23 | CBOEF | 1700 | 1600 | 100 | 0.01 | 2010-01-07 15:45:00 | 2023-11-01 16:00:00 | 10.4 MB |
| @W | Wheat Continuous Contract [Dec23] | Dec23 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-01-05 21:30:00 | 2023-11-01 13:20:00 | 14.2 MB |
| @YM | E-mini Dow Futures ($5) Continuous Contract [Dec23] | Dec23 | CBOT | 1700 | 1600 | 5 | 1 | 2006-01-03 22:00:00 | 2023-11-01 16:00:00 | 17.8 MB |
| @YM.D | E-mini Dow Futures ($5) Continuous Contract [Dec23] | Dec23 | CBOT | 830 | 1515 | 5 | 1 | 2006-01-06 13:45:00 | 2023-11-01 15:15:00 | 5.3 MB |

### 7. Schema
Representative file: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketEdge\Data\Futures\Data Export,@ES, 15min.txt`

`{"Date": "str (text file; parsed as noted)", "Time": "str (text file; parsed as noted)", "Open": "str (text file; parsed as noted)", "High": "str (text file; parsed as noted)", "Low": "str (text file; parsed as noted)", "Close": "str (text file; parsed as noted)", "Volume": "str (text file; parsed as noted)"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `D:\AmerAndish\Projects\Trade\SourceCodes\MarketEdge\Data\Futures\Data Export,@ES, 15min.txt`

First 5 rows (with header lines):
```
Data Exporter v3.0  ,  2022
 
@ES = E-mini S&P 500 Continuous Contract [Dec23]

Symbol,TimeFrame,Exchange,S.Start,S.End,$/Big Point,Tick Size,$Tick Size,#Ticks/Point,Avg Vol,Avg ATR,Avg $ATR
@ES,15min,CME,1700,1600,50,0.25,12.50,4,6231,1.17,59

Date,Time,Open,High,Low,Close,Volume
01/03/2006,20:00,1299.25,1299.50,1299.25,1299.25,5
01/03/2006,20:15,1299.50,1299.50,1299.25,1299.25,10
01/03/2006,20:30,1299.25,1299.50,1299.25,1299.25,40
01/03/2006,20:45,1299.50,1299.50,1299.25,1299.50,57
01/03/2006,21:00,1299.50,1299.50,1299.25,1299.50,81
```
Last 3 rows:
```
11/01/2023,15:30,4255.25,4256.25,4254.00,4255.00,2192
11/01/2023,15:45,4255.00,4257.50,4254.75,4257.25,2109
11/01/2023,16:00,4257.50,4258.50,4256.75,4258.25,2576
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `Date` = `MM/DD/YYYY`, `Time` = `HH:MM`, **naive**, separate columns.
- Across the sample, bars labelled exactly at header `S.Start`: 0; at `S.Start`+1 bar (15m): 174812; at `S.End`: 172272. S.End present and S.Start (almost) absent → labels are **bar-end** (TradeStation convention).
- @ES first bar of each session, winter (Dec–Feb): `{"Wed 17:15": 221, "Tue 17:15": 219, "Sun 17:15": 217, "Mon 17:15": 217}`; summer (Jun–Aug): `{"Thu 17:15": 237, "Mon 17:15": 237, "Wed 17:15": 237, "Sun 17:15": 234}` → identical wall-clock across DST ⇒ timestamps are **exchange-local time (US/Central for CME, with DST)**, not UTC.
- @ES weekday counts: `{"Mon": 82515, "Tue": 84146, "Wed": 84436, "Thu": 83665, "Fri": 57418, "Sun": 24788}` → Sunday bars are the Globex evening open (17:00 CT Sunday).
- Exchanges in headers: `{"CME": 28, "CBOT": 15, "ICEUS": 7, "NYMEX": 10, "COMEX": 3, "CBOEF": 2}` — ICE/NYBOT softs would be exported in their own local (US/Eastern) time if TradeStation's default 'exchange time' setting was used (to confirm).

### 13–14. Adjustment / futures specifics
- Series type: header contract tags `{"Dec23": 45, "null": 6, "Mar24": 4, "Sep23": 1, "Nov23": 3, "Jan24": 5, "Feb24": 1}`; descriptions say `Continuous Contract` → **continuous series** (one file per root); last timestamp across files: 2023-11-01 17:00:00.
- Bars with low ≤ 0 across sample: 557223 (back-adjusted series can go negative).
- Contracts with bars at price ≤ 0: @CL (575), @CT (25122), @HO (218413), @OJ (301), @QH (750), @QM (576), @RB (217503), @S (37395), @SM (56588). Real prices of these contracts never went ≤ 0 (except WTI crude in April 2020), so this is the signature of **additive back-adjustment**.
- Roll gaps: median share of each contract's 20 largest open-vs-previous-close jumps that fall in a quarterly roll window (5th–16th of Mar/Jun/Sep/Dec ≈ 13% of days): 0.20 → no clustering at roll dates; the largest jumps are weekend/news gaps → roll gaps have been removed (consistent with back-adjusted continuous series).

Tick-grid test (share of closes that are exact multiples of the header tick size; additive back-adjustment keeps prices on the grid, ratio adjustment breaks it) and largest open-vs-previous-close jumps (in multiples of the rolling median bar range; roll gaps would cluster in roll windows):

| symbol | bars ≤ 0 | on-grid first 20k | on-grid last 20k | top-20 jumps in Mar/Jun/Sep/Dec 5–16 | top 2 jumps |
|---|---|---|---|---|---|
| @ES | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2015-07-05 17:15:00", "jump": -29.75, "x_median_range": 23.8, "gap_min": 3180}, {"ts": "2012-01-03 05:15:00", "jump": 21.75, "x_median_range": 21.8, "gap_min": 5160}]` |
| @NQ | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2014-01-02 05:15:00", "jump": -16.5, "x_median_range": 22.0, "gap_min": 2235}, {"ts": "2012-01-03 05:15:00", "jump": 37.75, "x_median_range": 21.6, "gap_min": 5160}]` |
| @CL | 575 | 1.0 | 1.0 | 0.2 | `[{"ts": "2019-09-15 18:15:00", "jump": 6.66, "x_median_range": 51.2, "gap_min": 2955}, {"ts": "2020-03-08 18:15:00", "jump": -8.7, "x_median_range": 41.4, "gap_min": 2955}]` |
| @GC | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2007-11-25 20:45:00", "jump": -2.4, "x_median_range": 48.0, "gap_min": 15}, {"ts": "2006-02-07 14:00:00", "jump": -15.9, "x_median_range": 39.8, "gap_min": 345}]` |
| @ES.D | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2016-06-24 08:45:00", "jump": -74.5, "x_median_range": 27.1, "gap_min": 1050}, {"ts": "2020-02-24 08:45:00", "jump": -107.5, "x_median_range": 25.3, "gap_min": 3930}]` |
| @VX | 0 | 0.02 | 0.397 | 0.35 | `[{"ts": "2020-06-11 15:45:00", "jump": 10.37, "x_median_range": 42.3, "gap_min": 15}, {"ts": "2022-08-10 23:15:00", "jump": -2.23, "x_median_range": 34.3, "gap_min": 15}]` |
| @BTC | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-08 17:15:00", "jump": -905.0, "x_median_range": 60.3, "gap_min": 2955}, {"ts": "2018-06-10 17:15:00", "jump": -545.0, "x_median_range": 54.5, "gap_min": 2955}]` |
| @TY | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2016-08-29 17:15:00", "jump": 0.953125, "x_median_range": 30.5, "gap_min": 75}, {"ts": "2015-06-28 17:15:00", "jump": 1.328125, "x_median_range": 28.3, "gap_min": 2955}]` |
| @EC | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2015-06-28 17:15:00", "jump": -0.0179, "x_median_range": 22.4, "gap_min": 2955}, {"ts": "2017-04-23 17:15:00", "jump": 0.0134, "x_median_range": 22.3, "gap_min": 2955}]` |
| @C | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2010-10-10 19:15:00", "jump": 44.75, "x_median_range": 59.7, "gap_min": 3240}, {"ts": "2012-01-12 09:45:00", "jump": -44.5, "x_median_range": 59.3, "gap_min": 150}]` |
| @AD | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2019-01-02 17:15:00", "jump": -0.0102, "x_median_range": 20.4, "gap_min": 75}, {"ts": "2013-01-02 05:15:00", "jump": 0.0081, "x_median_range": 16.2, "gap_min": 2235}]` |
| @BO | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2008-03-31 09:45:00", "jump": -2.99, "x_median_range": 46.0, "gap_min": 225}, {"ts": "2008-03-31 19:15:00", "jump": -1.78, "x_median_range": 44.5, "gap_min": 360}]` |
| @BP | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2017-06-08 17:15:00", "jump": -0.022, "x_median_range": 31.4, "gap_min": 75}, {"ts": "2019-12-12 17:15:00", "jump": 0.0282, "x_median_range": 31.3, "gap_min": 75}]` |
| @CC | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2007-12-14 08:15:00", "jump": -40.0, "x_median_range": 40.0, "gap_min": 1215}, {"ts": "2008-02-05 08:15:00", "jump": -31.0, "x_median_range": 31.0, "gap_min": 1215}]` |
| @CD | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2020-03-08 17:15:00", "jump": -0.00535, "x_median_range": 13.4, "gap_min": 2955}, {"ts": "2016-04-17 17:15:00", "jump": -0.0078, "x_median_range": 13.0, "gap_min": 2955}]` |
| @CT | 25122 | 1.0 | 1.0 | 0.25 | `[{"ts": "2007-06-14 01:45:00", "jump": 5.55, "x_median_range": 69.4, "gap_min": 685}, {"ts": "2008-03-10 02:45:00", "jump": -3.06, "x_median_range": 68.0, "gap_min": 3630}]` |
| @E7 | 0 | 1.0 | 1.0 | 0.5 | `[{"ts": "2008-12-10 09:30:00", "jump": 0.0031, "x_median_range": 62.0, "gap_min": 15}, {"ts": "2017-04-23 17:15:00", "jump": 0.0165, "x_median_range": 33.0, "gap_min": 2955}]` |
| @ED | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2006-02-21 17:15:00", "jump": -0.22, "x_median_range": 88.0, "gap_min": 75}, {"ts": "2006-02-21 18:15:00", "jump": 0.2175, "x_median_range": 87.0, "gap_min": 30}]` |
| @ETH | 0 | 0.559 | 1.0 | 0.2 | `[{"ts": "2022-06-12 17:15:00", "jump": -210.5, "x_median_range": 30.1, "gap_min": 2955}, {"ts": "2023-01-15 17:15:00", "jump": 102.5, "x_median_range": 29.3, "gap_min": 2955}]` |
| @FC | 0 | 1.0 | 1.0 | 0.0 | `[{"ts": "2008-02-19 09:00:00", "jump": -1.15, "x_median_range": 92.0, "gap_min": 5520}, {"ts": "2008-02-22 10:00:00", "jump": -0.8, "x_median_range": 64.0, "gap_min": 30}]` |
| @FV | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2007-02-27 18:15:00", "jump": 0.5, "x_median_range": 32.0, "gap_min": 675}, {"ts": "2015-06-28 17:15:00", "jump": 0.617188, "x_median_range": 26.3, "gap_min": 2955}]` |
| @HO | 218413 | 1.0 | 1.0 | 0.0 | `[{"ts": "2006-01-22 20:45:00", "jump": 0.0452, "x_median_range": 452.0, "gap_min": 3555}, {"ts": "2006-02-01 15:30:00", "jump": -0.0244, "x_median_range": 244.0, "gap_min": 360}]` |
| @J7 | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2008-10-26 17:15:00", "jump": 0.022, "x_median_range": 440.0, "gap_min": 2985}, {"ts": "2008-10-26 21:00:00", "jump": 0.0082, "x_median_range": 164.0, "gap_min": 45}]` |
| @JY | 0 | 1.0 | 1.0 | 0.4 | `[{"ts": "2019-01-02 17:15:00", "jump": 0.017, "x_median_range": 26.2, "gap_min": 75}, {"ts": "2006-09-10 17:15:00", "jump": 0.0126, "x_median_range": 25.2, "gap_min": 2955}]` |
| @KW | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2022-03-06 19:15:00", "jump": 80.25, "x_median_range": 80.2, "gap_min": 3235}, {"ts": "2010-10-08 09:45:00", "jump": 51.75, "x_median_range": 69.0, "gap_min": 150}]` |
| @LC | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2006-07-24 09:30:00", "jump": -2.15, "x_median_range": 86.0, "gap_min": 4110}, {"ts": "2007-07-27 08:45:00", "jump": 5.35, "x_median_range": 71.3, "gap_min": 1180}]` |
| @M2K | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2019-05-05 17:15:00", "jump": -27.3, "x_median_range": 20.2, "gap_min": 2955}, {"ts": "2012-01-03 05:15:00", "jump": 12.9, "x_median_range": 16.1, "gap_min": 5145}]` |
| @MBT | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2023-08-17 17:15:00", "jump": -1435.0, "x_median_range": 26.1, "gap_min": 75}, {"ts": "2023-01-15 17:15:00", "jump": 1000.0, "x_median_range": 23.5, "gap_min": 2955}]` |
| @MCL | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2023-04-02 18:15:00", "jump": 3.4, "x_median_range": 22.7, "gap_min": 2955}, {"ts": "2023-06-04 18:15:00", "jump": 2.3, "x_median_range": 12.8, "gap_min": 2955}]` |
| @MET | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2023-09-10 19:30:00", "jump": -22.0, "x_median_range": 88.0, "gap_min": 3090}, {"ts": "2023-08-22 17:15:00", "jump": -27.5, "x_median_range": 55.0, "gap_min": 75}]` |
| @MNQ | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2014-01-02 05:15:00", "jump": -16.5, "x_median_range": 22.0, "gap_min": 2235}, {"ts": "2019-05-05 17:15:00", "jump": -123.75, "x_median_range": 22.0, "gap_min": 2955}]` |
| @MP1 | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2008-12-11 06:30:00", "jump": 0.00098, "x_median_range": 32.7, "gap_min": 240}, {"ts": "2006-02-22 06:00:00", "jump": 0.0009, "x_median_range": 30.0, "gap_min": 60}]` |
| @NE1 | 0 | 1.0 | 1.0 | 0.45 | `[{"ts": "2014-07-23 17:15:00", "jump": -0.0089, "x_median_range": 29.7, "gap_min": 75}, {"ts": "2015-09-09 17:15:00", "jump": -0.011, "x_median_range": 27.5, "gap_min": 75}]` |
| @NG | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2006-04-24 15:30:00", "jump": -0.533, "x_median_range": 88.8, "gap_min": 330}, {"ts": "2006-09-25 18:15:00", "jump": 1.269, "x_median_range": 70.5, "gap_min": 75}]` |
| @NQ.D | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2016-06-24 08:45:00", "jump": -170.75, "x_median_range": 23.6, "gap_min": 1050}, {"ts": "2015-08-24 08:45:00", "jump": -259.25, "x_median_range": 20.1, "gap_min": 3930}]` |
| @O | 0 | 1.0 | 1.0 | 0.0 | `[{"ts": "2008-08-12 19:45:00", "jump": -15.0, "x_median_range": 120.0, "gap_min": 390}, {"ts": "2012-06-25 19:15:00", "jump": 24.25, "x_median_range": 97.0, "gap_min": 390}]` |
| @OJ | 301 | 1.0 | 1.0 | 0.05 | `[{"ts": "2008-01-02 10:15:00", "jump": 6.2, "x_median_range": 35.4, "gap_min": 2670}, {"ts": "2007-10-12 10:15:00", "jump": 9.8, "x_median_range": 30.2, "gap_min": 1230}]` |
| @QH | 750 | 1.0 | 1.0 | 0.1 | `[{"ts": "2007-08-10 09:15:00", "jump": -0.03, "x_median_range": 60.0, "gap_min": 1125}, {"ts": "2007-06-08 15:15:00", "jump": -0.023, "x_median_range": 46.0, "gap_min": 15}]` |
| @QM | 576 | 0.0 | 1.0 | 0.2 | `[{"ts": "2019-09-15 18:15:00", "jump": 5.0, "x_median_range": 40.0, "gap_min": 2955}, {"ts": "2020-03-08 18:15:00", "jump": -6.0, "x_median_range": 26.7, "gap_min": 2955}]` |
| @QN | 0 | 0.267 | 1.0 | 0.05 | `[{"ts": "2016-10-25 18:15:00", "jump": -0.38, "x_median_range": 76.0, "gap_min": 75}, {"ts": "2013-10-27 18:15:00", "jump": -0.205, "x_median_range": 41.0, "gap_min": 2955}]` |
| @RB | 217503 | 1.0 | 1.0 | 0.05 | `[{"ts": "2006-06-21 15:30:00", "jump": 0.0506, "x_median_range": 1012.0, "gap_min": 345}, {"ts": "2006-01-30 15:30:00", "jump": 0.0305, "x_median_range": 610.0, "gap_min": 360}]` |
| @RR | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-06-08 19:15:00", "jump": -1.5, "x_median_range": 300.0, "gap_min": 360}, {"ts": "2008-04-17 19:15:00", "jump": 0.81, "x_median_range": 162.0, "gap_min": 390}]` |
| @S | 37395 | 1.0 | 1.0 | 0.05 | `[{"ts": "2009-07-01 09:45:00", "jump": -107.0, "x_median_range": 107.0, "gap_min": 150}, {"ts": "2006-04-02 19:15:00", "jump": -18.25, "x_median_range": 73.0, "gap_min": 3675}]` |
| @SB | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2008-06-24 03:45:00", "jump": 1.12, "x_median_range": 22.4, "gap_min": 885}, {"ts": "2008-02-15 08:15:00", "jump": 0.32, "x_median_range": 21.3, "gap_min": 1170}]` |
| @SF | 0 | 1.0 | 1.0 | 0.45 | `[{"ts": "2006-09-10 17:15:00", "jump": 0.0078, "x_median_range": 26.0, "gap_min": 2955}, {"ts": "2018-12-09 17:15:00", "jump": 0.0103, "x_median_range": 25.8, "gap_min": 2955}]` |
| @SM | 56588 | 1.0 | 1.0 | 0.0 | `[{"ts": "2008-03-31 19:15:00", "jump": -19.3, "x_median_range": 77.2, "gap_min": 360}, {"ts": "2010-10-08 09:45:00", "jump": 18.0, "x_median_range": 36.0, "gap_min": 150}]` |
| @TU | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2015-02-25 18:00:00", "jump": -0.414062, "x_median_range": 53.0, "gap_min": 15}, {"ts": "2015-02-25 17:15:00", "jump": 0.40625, "x_median_range": 52.0, "gap_min": 75}]` |
| @US | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2015-07-05 17:15:00", "jump": 1.75, "x_median_range": 18.7, "gap_min": 3195}, {"ts": "2015-06-28 17:15:00", "jump": 2.0, "x_median_range": 16.0, "gap_min": 2955}]` |
| @W | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2008-02-06 19:15:00", "jump": 24.0, "x_median_range": 192.0, "gap_min": 360}, {"ts": "2008-02-25 19:15:00", "jump": 90.0, "x_median_range": 120.0, "gap_min": 375}]` |
| @YM | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2015-07-05 17:15:00", "jump": -208.0, "x_median_range": 20.8, "gap_min": 3195}, {"ts": "2012-01-03 05:15:00", "jump": 202.0, "x_median_range": 20.2, "gap_min": 5160}]` |

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 14060252 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 557223 |
| null_cells | 0 |
| big_moves | 9923 |
| missing_bar_gaps | 123884 |
| zero_volume_share_median_file | 0.0386 |
| zero_volume_share_max_file | 0.2606 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 10 |
| files_with_nonpos_price | 9 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 18278328, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 724390, "big_moves": 12900, "missing_bar_gaps": 161049}` |

_Per-file statistics computed on 50 of 65 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: @ES, @NQ, @CL, @GC, @ES.D, @VX, @BTC, @TY, @EC, @C, @AD, @BO, @BP, @CC, @CD, @CT, @E7, @ED, @ETH, @FC, @FV, @HO, @J7, @JY, @KW, @LC, @M2K, @MBT, @MCL, @MET, @MNQ, @MP1, @NE1, @NG, @NQ.D, @O, @OJ, @QH, @QM, @QN, @RB, @RR, @S, @SB, @SF, @SM, @TU, @US, @W, @YM

---

## ATM-FUT-1H — Ali Casy-ATM · US futures continuous contracts · hourly (`Data Export,@SYM, 60min.csv`)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07` | `Data Export,*, 60min.csv` | 64 | 263.6 MB | `{".csv": 64}` |

### 2. Probable source
**TradeStation chart export via 'Data Exporter v3.0' indicator (exported 2025-07-09)**

- Same 'Data Exporter v3.0' header block as ME-FUT-15M (`@SYM = <desc> Continuous Contract [Sep25]`, `Symbol,TimeFrame,Exchange,S.Start,S.End,$/Big Point,...`); `@` continuous symbols and the `$/Big Point` / `S.Start` / `S.End` fields are TradeStation/EasyLanguage conventions.
- Each series exists twice, as `.csv` and `.txt` (byte-identity checked in the 'ATM folder file variants' section).

### 3–4. Symbols & asset class
- Asset class guess: **futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto)**
- 64 symbols; first 30: @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC, @KW, @LC, @LH, @M2K, @MBT

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1h** in 50 of 50 deep-sample files; the other 0 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1h": 50}`
- Most frequent spacing per file (bar grid): `{"1h": 50}` → mixed timeframes: False; median share of diffs equal to the median: 0.949

### 6. Date range
- Across all 64 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2006-01-09 03:00:00", "median": "2006-01-18 04:00:00", "max": "2021-12-10 16:00:00"}`; last ts `{"min": "2023-05-19 16:00:00", "median": "2025-07-09 01:00:00", "max": "2025-07-09 02:00:00"}`

| symbol | description | tag | exch | S.Start | S.End | $/pt | tick | first | last | size |
|---|---|---|---|---|---|---|---|---|---|---|
| @AD | Australian Dollar Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 6.0 MB |
| @BO | Soybean Oil Continuous Contract [Dec25] | Dec25 | CBOT | 1900 | 1320 | 600 | 0.01 | 2006-01-18 20:00:00 | 2025-07-09 01:00:00 | 3.8 MB |
| @BP | British Pound Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 5.5 MB |
| @BTC | Bitcoin Futures based on BRR Continuous Contract... | — | CME | 1700 | 1600 | 5 | 5 | 2017-12-22 03:00:00 | 2025-07-09 01:00:00 | 1.9 MB |
| @C | Corn Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-01-16 22:00:00 | 2025-07-09 01:00:00 | 4.2 MB |
| @CC | Cocoa Continuous Contract [Sep25] | Sep25 | ICEUS | 445 | 1330 | 10 | 1 | 2006-02-01 09:45:00 | 2025-07-08 13:30:00 | 1.7 MB |
| @CD | Canadian Dollar Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 6.0 MB |
| @CL | Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 1000 | 0.01 | 2006-01-10 09:00:00 | 2025-07-09 02:00:00 | 5.2 MB |
| @CT | Cotton No. 2 Continuous Contract [Dec25] | Dec25 | ICEUS | 2100 | 1420 | 500 | 0.01 | 2006-02-01 12:00:00 | 2025-07-09 01:00:00 | 3.5 MB |
| @DX | U.S. Dollar Index Continuous Contract [Sep25] | Sep25 | ICEUS | 2000 | 1700 | 1000 | 0.005 | 2006-01-23 22:00:00 | 2025-07-09 01:00:00 | 4.8 MB |
| @E7 | E-Mini Euro FX Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-01-09 04:00:00 | 2025-07-09 01:00:00 | 5.4 MB |
| @EC | Euro FX Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 6.0 MB |
| @ED | Eurodollar Continuous Contract [Sep23] | Sep23 | CME | 1700 | 1600 | 2500 | 0.0025 | 2006-01-09 07:00:00 | 2023-05-19 16:00:00 | 5.0 MB |
| @EMD | E-Mini S&P MidCap 400 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100 | 0.1 | 2006-01-10 19:00:00 | 2025-07-09 01:00:00 | 4.9 MB |
| @ES | E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 50 | 0.25 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 6.1 MB |
| @ES.D | E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 50 | 0.25 | 2006-01-24 12:30:00 | 2025-07-08 15:15:00 | 1.8 MB |
| @ETH | CME Ether Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 50 | 0.5 | 2021-02-14 21:00:00 | 2025-07-09 01:00:00 | 1.2 MB |
| @FC | Feeder Cattle Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 500 | 0.025 | 2007-02-07 09:30:00 | 2025-07-08 13:05:00 | 1.2 MB |
| @FV | 5 Yr U.S.Treasury Notes Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 1000 | 0.0078125 | 2006-01-09 08:00:00 | 2025-07-09 01:00:00 | 7.7 MB |
| @GC | Gold Continuous Contract [Aug25] | Aug25 | COMEX | 1800 | 1700 | 100 | 0.1 | 2006-01-10 14:00:00 | 2025-07-09 02:00:00 | 5.5 MB |
| @HG | Copper Continuous Contract [Sep25] | Sep25 | COMEX | 1800 | 1700 | 25000 | 0.0005 | 2006-01-10 22:00:00 | 2025-07-09 02:00:00 | 5.4 MB |
| @HO | Heating Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 42000 | 0.0001 | 2006-01-18 10:00:00 | 2025-07-09 02:00:00 | 5.5 MB |
| @J7 | E-Mini Japanese Yen Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-01-23 09:00:00 | 2025-07-09 01:00:00 | 4.7 MB |
| @JY | Japanese Yen Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 6.0 MB |
| @KC | Coffee C Continuous Contract [Sep25] | Sep25 | ICEUS | 415 | 1330 | 375 | 0.05 | 2006-02-08 11:15:00 | 2025-07-08 13:30:00 | 2.2 MB |
| @KW | Hard Red Winter Wheat Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2008-05-12 01:00:00 | 2025-07-09 01:00:00 | 3.7 MB |
| @LC | Live Cattle Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 400 | 0.025 | 2006-02-03 10:30:00 | 2025-07-08 13:05:00 | 1.3 MB |
| @LH | Lean Hogs Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 400 | 0.025 | 2006-02-02 12:30:00 | 2025-07-08 13:05:00 | 1.2 MB |
| @M2K | Micro E-mini Russell 2000 Continuous Contract [S... | — | CME | 1700 | 1600 | 5 | 0.1 | 2006-01-09 05:00:00 | 2025-07-09 01:00:00 | 5.2 MB |
| @MBT | Micro Bitcoin Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 0 | 5 | 2021-05-07 03:00:00 | 2025-07-09 01:00:00 | 1.1 MB |
| @MCL | Micro Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 100 | 0.01 | 2021-07-16 04:00:00 | 2025-07-09 02:00:00 | 1.0 MB |
| @MES | Micro E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 5 | 0.25 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 6.1 MB |
| @MES.D | Micro E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 5 | 0.25 | 2006-01-24 12:30:00 | 2025-07-08 15:15:00 | 1.8 MB |
| @MET | Micro Ether Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 0 | 0.5 | 2021-12-10 16:00:00 | 2025-07-09 01:00:00 | 1007.8 KB |
| @MNQ | Micro E-mini Nasdaq-100 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 2 | 0.25 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 6.2 MB |
| @MNQ.D | Micro E-mini Nasdaq-100 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 2 | 0.25 | 2006-01-24 12:30:00 | 2025-07-08 15:15:00 | 1.9 MB |
| @MP1 | Mexican Peso Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 500000 | 0.00001 | 2006-01-12 08:00:00 | 2025-07-09 01:00:00 | 5.5 MB |
| @MYM | Micro E-mini Dow Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 0 | 1 | 2006-01-09 08:00:00 | 2025-07-09 01:00:00 | 5.0 MB |
| @NE1 | New Zealand Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2013-10-07 20:00:00 | 2025-07-09 01:00:00 | 3.6 MB |
| @NG | Natural Gas Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 10000 | 0.001 | 2006-01-10 16:00:00 | 2025-07-09 02:00:00 | 5.2 MB |
| @NK | Nikkei 225 USD Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 5 | 5 | 2006-08-02 12:00:00 | 2025-07-09 01:00:00 | 4.4 MB |
| @NQ | E-Mini NASDAQ-100 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 20 | 0.25 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 6.1 MB |
| @NQ.D | E-Mini NASDAQ-100 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 20 | 0.25 | 2006-01-24 12:30:00 | 2025-07-08 15:15:00 | 1.9 MB |
| @O | Oats Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-03-26 23:00:00 | 2025-07-08 23:00:00 | 2.8 MB |
| @OJ | Frozen Concentrated OJ Continuous Contract [Sep25] | Sep25 | ICEUS | 800 | 1400 | 150 | 0.05 | 2006-02-08 12:00:00 | 2025-07-08 14:00:00 | 1.2 MB |
| @PL | Platinum Continuous Contract [Oct25] | Oct25 | NYMEX | 1800 | 1700 | 50 | 0.1 | 2006-01-18 04:00:00 | 2025-07-09 02:00:00 | 5.1 MB |
| @QM | E-mini Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 500 | 0.025 | 2006-01-09 07:00:00 | 2025-07-09 02:00:00 | 5.5 MB |
| @RB | NYHarborBlendstock RBOB Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 42000 | 0.0001 | 2006-01-11 04:00:00 | 2025-07-09 02:00:00 | 5.4 MB |
| @RR | Rough Rice Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 2000 | 0.005 | 2006-05-15 22:00:00 | 2025-07-08 20:00:00 | 2.3 MB |
| @RTY | Emini Russell 2000 Idx Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 50 | 0.1 | 2006-01-09 05:00:00 | 2025-07-09 01:00:00 | 5.2 MB |
| @RTY.D | Emini Russell 2000 Idx Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 50 | 0.1 | 2006-01-24 12:30:00 | 2025-07-08 15:15:00 | 1.6 MB |
| @S | Soybeans Continuous Contract [Nov25] | Nov25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-01-16 22:00:00 | 2025-07-09 01:00:00 | 4.3 MB |
| @SB | Sugar No. 11 Continuous Contract [Oct25] | Oct25 | ICEUS | 330 | 1300 | 1120 | 0.01 | 2006-02-08 10:30:00 | 2025-07-08 13:00:00 | 2.0 MB |
| @SF | Swiss Franc Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-01-09 03:00:00 | 2025-07-09 01:00:00 | 5.9 MB |
| @SI | Silver Continuous Contract [Sep25] | Sep25 | COMEX | 1800 | 1700 | 5000 | 0.005 | 2006-01-10 15:00:00 | 2025-07-09 02:00:00 | 5.4 MB |
| @SM | Soybean Meal Continuous Contract [Dec25] | Dec25 | CBOT | 1900 | 1320 | 100 | 0.1 | 2006-01-19 23:00:00 | 2025-07-09 01:00:00 | 3.8 MB |
| @TU | 2 Year U.S. Treasury Notes Continuous Contract [... | — | CBOT | 1700 | 1600 | 2000 | 0.00390625 | 2006-01-09 10:00:00 | 2025-07-09 01:00:00 | 8.1 MB |
| @TY | 10 Yr U.S. Treasury Notes Continuous Contract [S... | — | CBOT | 1700 | 1600 | 1000 | 0.015625 | 2006-01-09 07:00:00 | 2025-07-09 01:00:00 | 7.2 MB |
| @US | 30 Yr U.S.Treasury Bonds Continuous Contract [Se... | — | CBOT | 1700 | 1600 | 1000 | 0.03125 | 2006-01-09 08:00:00 | 2025-07-09 01:00:00 | 6.7 MB |
| @VX | CBOE Volatility Index Continuous Contract [Jul25] | Jul25 | CBOEF | 1700 | 1600 | 1000 | 0.05 | 2010-01-25 13:00:00 | 2025-07-09 01:00:00 | 3.3 MB |
| @VXM | Mini-VIX Futures Continuous Contract [Jul25] | Jul25 | CBOEF | 1700 | 1600 | 100 | 0.01 | 2010-01-25 13:00:00 | 2025-07-09 01:00:00 | 3.2 MB |
| @W | Wheat Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-01-17 01:00:00 | 2025-07-09 01:00:00 | 4.4 MB |
| @YM | E-mini Dow Futures ($5) Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 5 | 1 | 2006-01-09 08:00:00 | 2025-07-09 01:00:00 | 5.0 MB |
| @YM.D | E-mini Dow Futures ($5) Continuous Contract [Sep25] | Sep25 | CBOT | 830 | 1515 | 5 | 1 | 2006-01-24 12:30:00 | 2025-07-08 15:15:00 | 1.5 MB |

### 7. Schema
Representative file: `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, 60min.csv`

`{"Date": "str (text file; parsed as noted)", "Time": "str (text file; parsed as noted)", "Open": "str (text file; parsed as noted)", "High": "str (text file; parsed as noted)", "Low": "str (text file; parsed as noted)", "Close": "str (text file; parsed as noted)", "Volume": "str (text file; parsed as noted)"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, 60min.csv`

First 5 rows (with header lines):
```
Data Exporter v3.0  ,  2022
 
@ES = E-mini S&P 500 Continuous Contract [Sep25]

Symbol,TimeFrame,Exchange,S.Start,S.End,$/Big Point,Tick Size,$Tick Size,#Ticks/Point,Avg Vol,Avg ATR,Avg $ATR
@ES,60min,CME,1700,1600,50,0.25,12.50,4,19393,2.08,104

Date,Time,Open,High,Low,Close,Volume
01/09/2006,03:00,1733.50,1734.75,1732.25,1733.00,2982
01/09/2006,04:00,1733.00,1733.50,1732.50,1733.25,1101
01/09/2006,05:00,1733.25,1733.50,1733.00,1733.25,1463
01/09/2006,06:00,1733.25,1733.25,1732.25,1732.50,796
01/09/2006,07:00,1732.75,1733.00,1732.25,1732.75,1165
```
Last 3 rows:
```
07/08/2025,23:00,6267.25,6268.25,6264.25,6264.75,1289
07/09/2025,00:00,6265.00,6270.25,6264.25,6268.25,1551
07/09/2025,01:00,6268.25,6269.00,6263.50,6265.75,1696
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `Date` = `MM/DD/YYYY`, `Time` = `HH:MM`, **naive**, separate columns.
- Across the sample, bars labelled exactly at header `S.Start`: 0; at `S.Start`+1 bar (1h): 221636; at `S.End`: 229866. S.End present and S.Start (almost) absent → labels are **bar-end** (TradeStation convention).
- @ES first bar of each session, winter (Dec–Feb): `{"Wed 18:00": 246, "Mon 18:00": 243, "Tue 18:00": 243, "Thu 18:00": 241}`; summer (Jun–Aug): `{"Mon 18:00": 256, "Thu 18:00": 255, "Wed 18:00": 255, "Sun 18:00": 253}` → identical wall-clock across DST ⇒ timestamps are **exchange-local time (US/Central for CME, with DST)**, not UTC.
- @ES weekday counts: `{"Mon": 22740, "Tue": 23176, "Wed": 23190, "Thu": 23037, "Fri": 16779, "Sun": 6020}` → Sunday bars are the Globex evening open (17:00 CT Sunday).
- Exchanges in headers: `{"CME": 31, "CBOT": 15, "ICEUS": 6, "NYMEX": 7, "COMEX": 3, "CBOEF": 2}` — ICE/NYBOT softs would be exported in their own local (US/Eastern) time if TradeStation's default 'exchange time' setting was used (to confirm).

### 13–14. Adjustment / futures specifics
- Series type: header contract tags `{"Sep25": 37, "Dec25": 3, "null": 5, "Aug25": 10, "Sep23": 1, "Jul25": 5, "Oct25": 2, "Nov25": 1}`; descriptions say `Continuous Contract` → **continuous series** (one file per root); last timestamp across files: 2025-07-09 02:00:00.
- Bars with low ≤ 0 across sample: 176045 (back-adjusted series can go negative).
- Contracts with bars at price ≤ 0: @CL (640), @HO (74994), @RB (59741), @CT (4656), @OJ (3768), @QM (641), @S (10439), @SM (21166). Real prices of these contracts never went ≤ 0 (except WTI crude in April 2020), so this is the signature of **additive back-adjustment**.
- Roll gaps: median share of each contract's 20 largest open-vs-previous-close jumps that fall in a quarterly roll window (5th–16th of Mar/Jun/Sep/Dec ≈ 13% of days): 0.15 → no clustering at roll dates; the largest jumps are weekend/news gaps → roll gaps have been removed (consistent with back-adjusted continuous series).

Tick-grid test (share of closes that are exact multiples of the header tick size; additive back-adjustment keeps prices on the grid, ratio adjustment breaks it) and largest open-vs-previous-close jumps (in multiples of the rolling median bar range; roll gaps would cluster in roll windows):

| symbol | bars ≤ 0 | on-grid first 20k | on-grid last 20k | top-20 jumps in Mar/Jun/Sep/Dec 5–16 | top 2 jumps |
|---|---|---|---|---|---|
| @ES | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2015-06-28 18:00:00", "jump": -32.0, "x_median_range": 10.2, "gap_min": 3000}, {"ts": "2012-01-03 06:00:00", "jump": 21.75, "x_median_range": 8.7, "gap_min": 5160}]` |
| @NQ | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2012-01-03 06:00:00", "jump": 37.75, "x_median_range": 8.6, "gap_min": 5160}, {"ts": "2015-06-28 18:00:00", "jump": -51.25, "x_median_range": 7.2, "gap_min": 3000}]` |
| @CL | 640 | 1.0 | 1.0 | 0.2 | `[{"ts": "2019-09-15 19:00:00", "jump": 6.66, "x_median_range": 23.0, "gap_min": 3000}, {"ts": "2020-03-08 19:00:00", "jump": -8.7, "x_median_range": 19.1, "gap_min": 3000}]` |
| @GC | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2006-02-07 14:00:00", "jump": -15.9, "x_median_range": 17.7, "gap_min": 300}, {"ts": "2006-03-29 14:00:00", "jump": 9.8, "x_median_range": 16.3, "gap_min": 360}]` |
| @VX | 0 | 0.08 | 0.216 | 0.3 | `[{"ts": "2015-08-24 02:00:00", "jump": 3.55, "x_median_range": 19.2, "gap_min": 3480}, {"ts": "2022-08-11 00:00:00", "jump": -2.23, "x_median_range": 14.9, "gap_min": 60}]` |
| @BTC | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2019-10-27 18:00:00", "jump": 1035.0, "x_median_range": 27.6, "gap_min": 3000}, {"ts": "2019-05-12 18:00:00", "jump": 860.0, "x_median_range": 21.5, "gap_min": 3000}]` |
| @TY | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2016-08-29 18:00:00", "jump": 0.953125, "x_median_range": 15.2, "gap_min": 120}, {"ts": "2015-06-28 18:00:00", "jump": 1.328125, "x_median_range": 14.2, "gap_min": 3000}]` |
| @EC | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2017-04-23 18:00:00", "jump": 0.0134, "x_median_range": 12.5, "gap_min": 3000}, {"ts": "2013-03-17 18:00:00", "jump": -0.0149, "x_median_range": 9.3, "gap_min": 3000}]` |
| @C | 0 | 1.0 | 1.0 | 0.0 | `[{"ts": "2006-04-02 20:00:00", "jump": 7.75, "x_median_range": 31.0, "gap_min": 3720}, {"ts": "2007-04-01 20:00:00", "jump": -20.0, "x_median_range": 26.7, "gap_min": 3280}]` |
| @HO | 74994 | 1.0 | 1.0 | 0.1 | `[{"ts": "2006-06-28 16:00:00", "jump": -0.0908, "x_median_range": 45.4, "gap_min": 360}, {"ts": "2006-07-28 17:00:00", "jump": -0.1021, "x_median_range": 40.8, "gap_min": 420}]` |
| @RB | 59741 | 1.0 | 1.0 | 0.1 | `[{"ts": "2006-05-10 16:00:00", "jump": 0.126, "x_median_range": 40.0, "gap_min": 360}, {"ts": "2006-08-10 16:00:00", "jump": -0.117, "x_median_range": 30.0, "gap_min": 360}]` |
| @AD | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2019-01-02 18:00:00", "jump": -0.0102, "x_median_range": 10.2, "gap_min": 120}, {"ts": "2013-09-15 18:00:00", "jump": 0.0097, "x_median_range": 7.5, "gap_min": 3000}]` |
| @BO | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2006-07-18 20:00:00", "jump": -0.55, "x_median_range": 110.0, "gap_min": 840}, {"ts": "2006-07-06 21:00:00", "jump": 0.93, "x_median_range": 93.0, "gap_min": 900}]` |
| @BP | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2019-12-12 18:00:00", "jump": 0.0282, "x_median_range": 23.5, "gap_min": 120}, {"ts": "2017-06-08 18:00:00", "jump": -0.022, "x_median_range": 15.2, "gap_min": 120}]` |
| @CD | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2025-02-02 18:00:00", "jump": -0.0083, "x_median_range": 11.1, "gap_min": 3000}, {"ts": "2013-01-02 06:00:00", "jump": 0.0063, "x_median_range": 7.0, "gap_min": 2280}]` |
| @CT | 4656 | 1.0 | 1.0 | 0.25 | `[{"ts": "2010-12-22 22:00:00", "jump": -6.0, "x_median_range": 37.5, "gap_min": 460}, {"ts": "2007-06-14 02:00:00", "jump": 5.55, "x_median_range": 32.6, "gap_min": 700}]` |
| @DX | 0 | 0.367 | 0.087 | 0.25 | `[{"ts": "2007-06-12 21:00:00", "jump": 0.23, "x_median_range": 92.0, "gap_min": 720}, {"ts": "2006-10-26 07:00:00", "jump": 0.96, "x_median_range": 48.0, "gap_min": 120}]` |
| @ED | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2006-02-21 18:00:00", "jump": -0.22, "x_median_range": 44.0, "gap_min": 120}, {"ts": "2006-02-21 19:00:00", "jump": 0.2175, "x_median_range": 43.5, "gap_min": 60}]` |
| @EMD | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2015-06-28 18:00:00", "jump": -18.3, "x_median_range": 8.1, "gap_min": 3000}, {"ts": "2012-01-03 06:00:00", "jump": 13.6, "x_median_range": 7.6, "gap_min": 5160}]` |
| @ES.D | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2015-08-24 09:30:00", "jump": -101.5, "x_median_range": 15.6, "gap_min": 3975}, {"ts": "2020-02-24 09:30:00", "jump": -107.5, "x_median_range": 13.9, "gap_min": 3975}]` |
| @FC | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2007-09-17 09:30:00", "jump": -0.975, "x_median_range": 78.0, "gap_min": 4200}, {"ts": "2007-05-25 09:30:00", "jump": -0.95, "x_median_range": 76.0, "gap_min": 1380}]` |
| @FV | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2007-02-27 19:00:00", "jump": 0.5, "x_median_range": 16.0, "gap_min": 720}, {"ts": "2015-06-28 18:00:00", "jump": 0.617188, "x_median_range": 13.2, "gap_min": 3000}]` |
| @HG | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2006-10-16 15:00:00", "jump": 0.143, "x_median_range": 23.8, "gap_min": 420}, {"ts": "2006-03-17 14:00:00", "jump": 0.059, "x_median_range": 19.7, "gap_min": 360}]` |
| @JY | 0 | 1.0 | 1.0 | 0.4 | `[{"ts": "2019-01-02 18:00:00", "jump": 0.017, "x_median_range": 13.6, "gap_min": 120}, {"ts": "2006-09-10 18:00:00", "jump": 0.0126, "x_median_range": 11.5, "gap_min": 3000}]` |
| @KC | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2021-07-23 05:15:00", "jump": 10.1, "x_median_range": 7.3, "gap_min": 945}, {"ts": "2007-10-15 09:15:00", "jump": -8.0, "x_median_range": 7.3, "gap_min": 4080}]` |
| @LC | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2007-07-27 09:30:00", "jump": 5.35, "x_median_range": 16.5, "gap_min": 1225}, {"ts": "2006-07-24 09:30:00", "jump": -2.15, "x_median_range": 12.3, "gap_min": 4105}]` |
| @LH | 0 | 0.922 | 1.0 | 0.35 | `[{"ts": "2006-06-19 11:30:00", "jump": 1.4, "x_median_range": 7.5, "gap_min": 60}, {"ts": "2007-06-12 09:30:00", "jump": 1.475, "x_median_range": 7.4, "gap_min": 1225}]` |
| @M2K | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2019-05-05 18:00:00", "jump": -27.3, "x_median_range": 11.4, "gap_min": 3000}, {"ts": "2012-01-03 06:00:00", "jump": 12.9, "x_median_range": 6.8, "gap_min": 5160}]` |
| @MCL | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2023-04-02 19:00:00", "jump": 3.4, "x_median_range": 10.5, "gap_min": 3000}, {"ts": "2025-06-15 19:00:00", "jump": 3.54, "x_median_range": 8.0, "gap_min": 3000}]` |
| @MES | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2015-06-28 18:00:00", "jump": -32.0, "x_median_range": 10.2, "gap_min": 3000}, {"ts": "2012-01-03 06:00:00", "jump": 21.75, "x_median_range": 8.7, "gap_min": 5160}]` |
| @MES.D | 0 | 0.0 | 0.444 | 0.05 | `[{"ts": "2015-08-24 09:30:00", "jump": -101.5, "x_median_range": 15.6, "gap_min": 3975}, {"ts": "2020-02-24 09:30:00", "jump": -107.25, "x_median_range": 14.1, "gap_min": 3975}]` |
| @MNQ | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2019-05-05 18:00:00", "jump": -123.75, "x_median_range": 10.5, "gap_min": 3000}, {"ts": "2012-01-03 06:00:00", "jump": 37.75, "x_median_range": 8.6, "gap_min": 5160}]` |
| @MNQ.D | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2015-08-24 09:30:00", "jump": -259.25, "x_median_range": 13.7, "gap_min": 3975}, {"ts": "2020-02-24 09:30:00", "jump": -355.5, "x_median_range": 11.6, "gap_min": 3975}]` |
| @MP1 | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2025-02-02 18:00:00", "jump": -0.00132, "x_median_range": 13.2, "gap_min": 3000}, {"ts": "2022-07-17 18:00:00", "jump": 0.00117, "x_median_range": 11.7, "gap_min": 3000}]` |
| @NE1 | 0 | 1.0 | 1.0 | 0.45 | `[{"ts": "2014-07-23 18:00:00", "jump": -0.0089, "x_median_range": 11.1, "gap_min": 120}, {"ts": "2015-06-10 18:00:00", "jump": -0.0118, "x_median_range": 9.4, "gap_min": 120}]` |
| @NG | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2006-04-24 16:00:00", "jump": -0.533, "x_median_range": 26.7, "gap_min": 360}, {"ts": "2006-09-25 19:00:00", "jump": 1.269, "x_median_range": 25.1, "gap_min": 120}]` |
| @NK | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2012-01-03 06:00:00", "jump": 165.0, "x_median_range": 16.5, "gap_min": 5160}, {"ts": "2012-01-06 00:00:00", "jump": -135.0, "x_median_range": 13.5, "gap_min": 660}]` |
| @O | 0 | 1.0 | 1.0 | 0.0 | `[{"ts": "2012-07-27 10:00:00", "jump": 7.0, "x_median_range": 56.0, "gap_min": 60}, {"ts": "2020-08-17 09:00:00", "jump": 5.75, "x_median_range": 46.0, "gap_min": 60}]` |
| @OJ | 3768 | 1.0 | 1.0 | 0.3 | `[{"ts": "2006-10-12 11:00:00", "jump": 9.8, "x_median_range": 9.8, "gap_min": 1260}, {"ts": "2007-10-12 11:00:00", "jump": 9.8, "x_median_range": 9.8, "gap_min": 1260}]` |
| @QM | 641 | 0.099 | 1.0 | 0.2 | `[{"ts": "2019-09-15 19:00:00", "jump": 5.0, "x_median_range": 18.2, "gap_min": 3000}, {"ts": "2020-03-08 19:00:00", "jump": -6.0, "x_median_range": 13.3, "gap_min": 3000}]` |
| @RR | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2006-11-01 10:00:00", "jump": 0.675, "x_median_range": 67.5, "gap_min": 1260}, {"ts": "2006-11-01 20:00:00", "jump": 0.44, "x_median_range": 44.0, "gap_min": 420}]` |
| @RTY | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2025-02-02 18:00:00", "jump": -46.4, "x_median_range": 7.9, "gap_min": 3000}, {"ts": "2019-05-05 18:00:00", "jump": -18.7, "x_median_range": 7.8, "gap_min": 3000}]` |
| @S | 10439 | 1.0 | 1.0 | 0.0 | `[{"ts": "2009-07-01 10:00:00", "jump": -107.0, "x_median_range": 35.7, "gap_min": 120}, {"ts": "2006-07-02 20:00:00", "jump": 14.25, "x_median_range": 28.5, "gap_min": 3720}]` |
| @SB | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2008-06-24 04:30:00", "jump": 1.12, "x_median_range": 10.2, "gap_min": 930}, {"ts": "2014-08-04 04:30:00", "jump": 0.55, "x_median_range": 6.9, "gap_min": 3810}]` |
| @SF | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2015-01-15 18:00:00", "jump": -0.0162, "x_median_range": 11.6, "gap_min": 120}, {"ts": "2018-12-09 18:00:00", "jump": 0.0103, "x_median_range": 11.4, "gap_min": 3000}]` |
| @SM | 21166 | 1.0 | 1.0 | 0.2 | `[{"ts": "2006-06-04 20:00:00", "jump": 9.5, "x_median_range": 95.0, "gap_min": 3720}, {"ts": "2006-05-10 20:00:00", "jump": -3.7, "x_median_range": 74.0, "gap_min": 840}]` |
| @TU | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2015-02-25 18:00:00", "jump": 0.40625, "x_median_range": 26.0, "gap_min": 120}, {"ts": "2006-11-28 19:00:00", "jump": 0.21875, "x_median_range": 14.0, "gap_min": 180}]` |
| @US | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2016-08-29 19:00:00", "jump": -1.46875, "x_median_range": 7.8, "gap_min": 60}, {"ts": "2016-08-29 18:00:00", "jump": 1.40625, "x_median_range": 7.5, "gap_min": 120}]` |
| @W | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2006-04-27 22:00:00", "jump": -19.75, "x_median_range": 39.5, "gap_min": 960}, {"ts": "2008-02-25 20:00:00", "jump": 90.0, "x_median_range": 27.7, "gap_min": 420}]` |
| @YM | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2024-07-18 20:00:00", "jump": -587.0, "x_median_range": 12.4, "gap_min": 1200}, {"ts": "2012-01-03 06:00:00", "jump": 202.0, "x_median_range": 9.2, "gap_min": 5160}]` |

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 4378014 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 176045 |
| null_cells | 0 |
| big_moves | 6931 |
| missing_bar_gaps | 18145 |
| zero_volume_share_median_file | 0.0049 |
| zero_volume_share_max_file | 0.1813 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 8 |
| files_with_nonpos_price | 8 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 5603858, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 225338, "big_moves": 8872, "missing_bar_gaps": 23226}` |

_Per-file statistics computed on 50 of 64 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: @ES, @NQ, @CL, @GC, @VX, @BTC, @TY, @EC, @C, @HO, @RB, @AD, @BO, @BP, @CD, @CT, @DX, @ED, @EMD, @ES.D, @FC, @FV, @HG, @JY, @KC, @LC, @LH, @M2K, @MCL, @MES, @MES.D, @MNQ, @MNQ.D, @MP1, @NE1, @NG, @NK, @O, @OJ, @QM, @RR, @RTY, @S, @SB, @SF, @SM, @TU, @US, @W, @YM

---

## ATM-FUT-1440 — Ali Casy-ATM · US futures continuous contracts · 1440-minute (one bar per session) (`Data Export,@SYM, 1440min.csv`)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07` | `Data Export,*, 1440min.csv` | 64 | 14.7 MB | `{".csv": 64}` |

### 2. Probable source
**TradeStation chart export via 'Data Exporter v3.0' indicator (exported 2025-07-09)**

- Same 'Data Exporter v3.0' header block as ME-FUT-15M (`@SYM = <desc> Continuous Contract [Sep25]`, `Symbol,TimeFrame,Exchange,S.Start,S.End,$/Big Point,...`); `@` continuous symbols and the `$/Big Point` / `S.Start` / `S.End` fields are TradeStation/EasyLanguage conventions.
- Each series exists twice, as `.csv` and `.txt` (byte-identity checked in the 'ATM folder file variants' section).

### 3–4. Symbols & asset class
- Asset class guess: **futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto)**
- 64 symbols; first 30: @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC, @KW, @LC, @LH, @M2K, @MBT

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1d** in 50 of 50 deep-sample files; the other 0 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1d": 50}`
- Most frequent spacing per file (bar grid): `{"1d": 50}` → mixed timeframes: False; median share of diffs equal to the median: 0.794

### 6. Date range
- Across all 64 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2006-05-25 16:00:00", "median": "2006-05-30 15:15:00", "max": "2022-04-28 16:00:00"}`; last ts `{"min": "2023-05-19 16:00:00", "median": "2025-07-08 16:00:00", "max": "2025-07-08 17:00:00"}`

| symbol | description | tag | exch | S.Start | S.End | $/pt | tick | first | last | size |
|---|---|---|---|---|---|---|---|---|---|---|
| @AD | Australian Dollar Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 270.2 KB |
| @BO | Soybean Oil Continuous Contract [Dec25] | Dec25 | CBOT | 1900 | 1320 | 600 | 0.01 | 2006-05-31 13:20:00 | 2025-07-08 13:20:00 | 223.2 KB |
| @BP | British Pound Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 251.0 KB |
| @BTC | Bitcoin Futures based on BRR Continuous Contract... | — | CME | 1700 | 1600 | 5 | 5 | 2018-05-11 16:00:00 | 2025-07-08 16:00:00 | 85.5 KB |
| @C | Corn Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 244.5 KB |
| @CC | Cocoa Continuous Contract [Sep25] | Sep25 | ICEUS | 445 | 1330 | 10 | 1 | 2006-05-30 13:30:00 | 2025-07-08 13:30:00 | 207.0 KB |
| @CD | Canadian Dollar Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 270.2 KB |
| @CL | Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 1000 | 0.01 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 238.2 KB |
| @CT | Cotton No. 2 Continuous Contract [Dec25] | Dec25 | ICEUS | 2100 | 1420 | 500 | 0.01 | 2006-05-31 14:20:00 | 2025-07-08 14:20:00 | 221.6 KB |
| @DX | U.S. Dollar Index Continuous Contract [Sep25] | Sep25 | ICEUS | 2000 | 1700 | 1000 | 0.005 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 249.3 KB |
| @E7 | E-Mini Euro FX Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 245.4 KB |
| @EC | Euro FX Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 272.4 KB |
| @ED | Eurodollar Continuous Contract [Sep23] | Sep23 | CME | 1700 | 1600 | 2500 | 0.0025 | 2006-05-25 16:00:00 | 2023-05-19 16:00:00 | 240.8 KB |
| @EMD | E-Mini S&P MidCap 400 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100 | 0.1 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 245.1 KB |
| @ES | E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 50 | 0.25 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 276.3 KB |
| @ES.D | E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 50 | 0.25 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 269.0 KB |
| @ETH | CME Ether Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 50 | 0.5 | 2021-06-29 16:00:00 | 2025-07-08 16:00:00 | 52.1 KB |
| @FC | Feeder Cattle Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 500 | 0.025 | 2007-04-17 13:05:00 | 2025-07-08 13:05:00 | 244.6 KB |
| @FV | 5 Yr U.S.Treasury Notes Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 1000 | 0.0078125 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 347.5 KB |
| @GC | Gold Continuous Contract [Aug25] | Aug25 | COMEX | 1800 | 1700 | 100 | 0.1 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 251.5 KB |
| @HG | Copper Continuous Contract [Sep25] | Sep25 | COMEX | 1800 | 1700 | 25000 | 0.0005 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 249.4 KB |
| @HO | Heating Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 42000 | 0.0001 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 261.1 KB |
| @J7 | E-Mini Japanese Yen Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-05-26 16:00:00 | 2025-07-08 16:00:00 | 240.0 KB |
| @JY | Japanese Yen Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 270.6 KB |
| @KC | Coffee C Continuous Contract [Sep25] | Sep25 | ICEUS | 415 | 1330 | 375 | 0.05 | 2006-05-30 13:30:00 | 2025-07-08 13:30:00 | 236.7 KB |
| @KW | Hard Red Winter Wheat Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2008-09-23 13:20:00 | 2025-07-08 13:20:00 | 218.4 KB |
| @LC | Live Cattle Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 400 | 0.025 | 2006-05-30 13:05:00 | 2025-07-08 13:05:00 | 258.9 KB |
| @LH | Lean Hogs Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 400 | 0.025 | 2006-05-30 13:05:00 | 2025-07-08 13:05:00 | 255.5 KB |
| @M2K | Micro E-mini Russell 2000 Continuous Contract [S... | — | CME | 1700 | 1600 | 5 | 0.1 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 244.7 KB |
| @MBT | Micro Bitcoin Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 0 | 5 | 2021-09-21 16:00:00 | 2025-07-08 16:00:00 | 46.1 KB |
| @MCL | Micro Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 100 | 0.01 | 2021-11-30 17:00:00 | 2025-07-08 17:00:00 | 43.9 KB |
| @MES | Micro E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 5 | 0.25 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 276.0 KB |
| @MES.D | Micro E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 5 | 0.25 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 268.7 KB |
| @MET | Micro Ether Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 0 | 0.5 | 2022-04-28 16:00:00 | 2025-07-08 16:00:00 | 41.7 KB |
| @MNQ | Micro E-mini Nasdaq-100 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 2 | 0.25 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 280.6 KB |
| @MNQ.D | Micro E-mini Nasdaq-100 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 2 | 0.25 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 273.2 KB |
| @MP1 | Mexican Peso Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 500000 | 0.00001 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 269.1 KB |
| @MYM | Micro E-mini Dow Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 0 | 1 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 231.0 KB |
| @NE1 | New Zealand Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2014-02-21 16:00:00 | 2025-07-08 16:00:00 | 159.9 KB |
| @NG | Natural Gas Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 10000 | 0.001 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 241.3 KB |
| @NK | Nikkei 225 USD Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 5 | 5 | 2006-12-12 16:00:00 | 2025-07-08 16:00:00 | 216.3 KB |
| @NQ | E-Mini NASDAQ-100 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 20 | 0.25 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 280.6 KB |
| @NQ.D | E-Mini NASDAQ-100 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 20 | 0.25 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 273.4 KB |
| @O | Oats Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-07-20 13:20:00 | 2025-07-08 13:20:00 | 231.4 KB |
| @OJ | Frozen Concentrated OJ Continuous Contract [Sep25] | Sep25 | ICEUS | 800 | 1400 | 150 | 0.05 | 2006-05-30 14:00:00 | 2025-07-08 14:00:00 | 218.4 KB |
| @PL | Platinum Continuous Contract [Oct25] | Oct25 | NYMEX | 1800 | 1700 | 50 | 0.1 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 242.8 KB |
| @QM | E-mini Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 500 | 0.025 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 250.9 KB |
| @RB | NYHarborBlendstock RBOB Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 42000 | 0.0001 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 258.2 KB |
| @RR | Rough Rice Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 2000 | 0.005 | 2006-09-01 13:20:00 | 2025-07-08 13:20:00 | 230.7 KB |
| @RTY | Emini Russell 2000 Idx Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 50 | 0.1 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 245.2 KB |
| @RTY.D | Emini Russell 2000 Idx Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 50 | 0.1 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 238.8 KB |
| @S | Soybeans Continuous Contract [Nov25] | Nov25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 248.7 KB |
| @SB | Sugar No. 11 Continuous Contract [Oct25] | Oct25 | ICEUS | 330 | 1300 | 1120 | 0.01 | 2006-05-30 13:00:00 | 2025-07-08 13:00:00 | 221.2 KB |
| @SF | Swiss Franc Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-05-25 16:00:00 | 2025-07-08 16:00:00 | 269.0 KB |
| @SI | Silver Continuous Contract [Sep25] | Sep25 | COMEX | 1800 | 1700 | 5000 | 0.005 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 249.7 KB |
| @SM | Soybean Meal Continuous Contract [Dec25] | Dec25 | CBOT | 1900 | 1320 | 100 | 0.1 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 225.8 KB |
| @TU | 2 Year U.S. Treasury Notes Continuous Contract [... | — | CBOT | 1700 | 1600 | 2000 | 0.00390625 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 366.5 KB |
| @TY | 10 Yr U.S. Treasury Notes Continuous Contract [S... | — | CBOT | 1700 | 1600 | 1000 | 0.015625 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 327.7 KB |
| @US | 30 Yr U.S.Treasury Bonds Continuous Contract [Se... | — | CBOT | 1700 | 1600 | 1000 | 0.03125 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 306.9 KB |
| @VX | CBOE Volatility Index Continuous Contract [Jul25] | Jul25 | CBOEF | 1700 | 1600 | 1000 | 0.05 | 2010-05-28 16:00:00 | 2025-07-08 16:00:00 | 189.1 KB |
| @VXM | Mini-VIX Futures Continuous Contract [Jul25] | Jul25 | CBOEF | 1700 | 1600 | 100 | 0.01 | 2010-05-28 16:00:00 | 2025-07-08 16:00:00 | 186.9 KB |
| @W | Wheat Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 255.4 KB |
| @YM | E-mini Dow Futures ($5) Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 5 | 1 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 231.3 KB |
| @YM.D | E-mini Dow Futures ($5) Continuous Contract [Sep25] | Sep25 | CBOT | 830 | 1515 | 5 | 1 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 225.6 KB |

### 7. Schema
Representative file: `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, 1440min.csv`

`{"Date": "str (text file; parsed as noted)", "Time": "str (text file; parsed as noted)", "Open": "str (text file; parsed as noted)", "High": "str (text file; parsed as noted)", "Low": "str (text file; parsed as noted)", "Close": "str (text file; parsed as noted)", "Volume": "str (text file; parsed as noted)"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, 1440min.csv`

First 5 rows (with header lines):
```
Data Exporter v3.0  ,  2022
 
@ES = E-mini S&P 500 Continuous Contract [Sep25]

Symbol,TimeFrame,Exchange,S.Start,S.End,$/Big Point,Tick Size,$Tick Size,#Ticks/Point,Avg Vol,Avg ATR,Avg $ATR
@ES,1440min,CME,1700,1600,50,0.25,12.50,4,453142,12.28,614

Date,Time,Open,High,Low,Close,Volume
05/25/2006,16:00,1693.75,1709.00,1689.50,1708.00,599305
05/26/2006,16:00,1707.00,1715.00,1705.75,1714.25,377306
05/29/2006,16:00,1714.00,1715.00,1711.50,1711.75,3753
05/30/2006,16:00,1711.50,1713.50,1691.00,1691.75,460630
05/31/2006,16:00,1692.25,1705.00,1687.75,1704.75,624566
```
Last 3 rows:
```
07/04/2025,16:00,6320.75,6322.75,6276.50,6283.50,58757
07/07/2025,16:00,6307.75,6315.00,6246.25,6263.25,586961
07/08/2025,16:00,6262.50,6289.00,6254.50,6271.75,519616
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `Date` = `MM/DD/YYYY`, `Time` = `HH:MM`, **naive**, separate columns.
- Across the sample, bars labelled exactly at header `S.Start`: 0; at `S.Start`+1 bar (1d): 0; at `S.End`: 233430. S.End present and S.Start (almost) absent → labels are **bar-end** (TradeStation convention).
- @ES first bar of each session, winter (Dec–Feb): `{"Mon 16:00": 233, "Tue 16:00": 12, "Wed 16:00": 6, "Thu 16:00": 6}`; summer (Jun–Aug): `{"Mon 16:00": 256}` → identical wall-clock across DST ⇒ timestamps are **exchange-local time (US/Central for CME, with DST)**, not UTC.
- @ES weekday counts: `{"Mon": 986, "Tue": 992, "Wed": 991, "Thu": 994, "Fri": 977}` → Sunday bars are the Globex evening open (17:00 CT Sunday).
- Exchanges in headers: `{"CME": 31, "CBOT": 15, "ICEUS": 6, "NYMEX": 7, "COMEX": 3, "CBOEF": 2}` — ICE/NYBOT softs would be exported in their own local (US/Eastern) time if TradeStation's default 'exchange time' setting was used (to confirm).

### 13–14. Adjustment / futures specifics
- Series type: header contract tags `{"Sep25": 37, "Dec25": 3, "null": 5, "Aug25": 10, "Sep23": 1, "Jul25": 5, "Oct25": 2, "Nov25": 1}`; descriptions say `Continuous Contract` → **continuous series** (one file per root); last timestamp across files: 2025-07-08 17:00:00.
- Bars with low ≤ 0 across sample: 9224 (back-adjusted series can go negative).
- Contracts with bars at price ≤ 0: @CL (33), @HO (3411), @RB (2779), @CT (307), @OJ (664), @QM (33), @S (630), @SM (1367). Real prices of these contracts never went ≤ 0 (except WTI crude in April 2020), so this is the signature of **additive back-adjustment**.
- Roll gaps: median share of each contract's 20 largest open-vs-previous-close jumps that fall in a quarterly roll window (5th–16th of Mar/Jun/Sep/Dec ≈ 13% of days): 0.20 → no clustering at roll dates; the largest jumps are weekend/news gaps → roll gaps have been removed (consistent with back-adjusted continuous series).

Tick-grid test (share of closes that are exact multiples of the header tick size; additive back-adjustment keeps prices on the grid, ratio adjustment breaks it) and largest open-vs-previous-close jumps (in multiples of the rolling median bar range; roll gaps would cluster in roll windows):

| symbol | bars ≤ 0 | on-grid first 20k | on-grid last 20k | top-20 jumps in Mar/Jun/Sep/Dec 5–16 | top 2 jumps |
|---|---|---|---|---|---|
| @ES | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-02 16:00:00", "jump": -88.0, "x_median_range": 3.7, "gap_min": 4320}, {"ts": "2020-03-30 16:00:00", "jump": -61.0, "x_median_range": 2.2, "gap_min": 4320}]` |
| @NQ | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2020-03-02 16:00:00", "jump": -198.75, "x_median_range": 2.3, "gap_min": 4320}, {"ts": "2020-03-09 16:00:00", "jump": -132.75, "x_median_range": 1.5, "gap_min": 4320}]` |
| @CL | 33 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-09 17:00:00", "jump": -8.7, "x_median_range": 6.5, "gap_min": 4320}, {"ts": "2019-09-16 17:00:00", "jump": 6.66, "x_median_range": 4.1, "gap_min": 4320}]` |
| @GC | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-16 17:00:00", "jump": 34.9, "x_median_range": 2.3, "gap_min": 4320}, {"ts": "2022-02-28 17:00:00", "jump": 30.9, "x_median_range": 1.6, "gap_min": 4320}]` |
| @VX | 0 | 0.124 | 0.124 | 0.25 | `[{"ts": "2015-08-24 16:00:00", "jump": 3.55, "x_median_range": 5.0, "gap_min": 4320}, {"ts": "2020-03-02 16:00:00", "jump": 2.95, "x_median_range": 4.1, "gap_min": 4320}]` |
| @BTC | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2021-01-04 16:00:00", "jump": 4185.0, "x_median_range": 7.1, "gap_min": 5760}, {"ts": "2019-05-20 16:00:00", "jump": 900.0, "x_median_range": 6.9, "gap_min": 4320}]` |
| @TY | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-16 16:00:00", "jump": 2.078125, "x_median_range": 3.9, "gap_min": 4320}, {"ts": "2015-06-29 16:00:00", "jump": 1.328125, "x_median_range": 2.1, "gap_min": 4320}]` |
| @EC | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2017-04-24 16:00:00", "jump": 0.0134, "x_median_range": 1.8, "gap_min": 4320}, {"ts": "2022-02-28 16:00:00", "jump": -0.01115, "x_median_range": 1.7, "gap_min": 4320}]` |
| @C | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2010-10-11 13:20:00", "jump": 44.75, "x_median_range": 4.5, "gap_min": 4320}, {"ts": "2011-04-01 13:20:00", "jump": 38.5, "x_median_range": 2.5, "gap_min": 1440}]` |
| @HO | 3411 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-09 17:00:00", "jump": -0.1637, "x_median_range": 4.0, "gap_min": 4320}, {"ts": "2019-09-16 17:00:00", "jump": 0.1108, "x_median_range": 2.5, "gap_min": 4320}]` |
| @RB | 2779 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-09 17:00:00", "jump": -0.1603, "x_median_range": 3.6, "gap_min": 4320}, {"ts": "2015-08-28 17:00:00", "jump": 0.1288, "x_median_range": 2.4, "gap_min": 1440}]` |
| @AD | 0 | 1.0 | 1.0 | 0.4 | `[{"ts": "2008-10-13 16:00:00", "jump": 0.0307, "x_median_range": 2.6, "gap_min": 4320}, {"ts": "2020-03-16 16:00:00", "jump": 0.0088, "x_median_range": 2.1, "gap_min": 4320}]` |
| @BO | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2008-03-10 13:20:00", "jump": -2.0, "x_median_range": 2.4, "gap_min": 4320}, {"ts": "2013-01-02 13:20:00", "jump": 1.82, "x_median_range": 2.1, "gap_min": 2880}]` |
| @BP | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2019-12-13 16:00:00", "jump": 0.0282, "x_median_range": 3.3, "gap_min": 1440}, {"ts": "2017-06-09 16:00:00", "jump": -0.022, "x_median_range": 2.6, "gap_min": 1440}]` |
| @CD | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2025-02-03 16:00:00", "jump": -0.0083, "x_median_range": 2.4, "gap_min": 4320}, {"ts": "2020-03-09 16:00:00", "jump": -0.00535, "x_median_range": 2.1, "gap_min": 4320}]` |
| @CT | 307 | 1.0 | 1.0 | 0.2 | `[{"ts": "2007-06-14 14:20:00", "jump": 5.55, "x_median_range": 6.4, "gap_min": 1440}, {"ts": "2007-06-15 14:20:00", "jump": -5.14, "x_median_range": 5.9, "gap_min": 1440}]` |
| @DX | 0 | 0.214 | 0.214 | 0.15 | `[{"ts": "2006-12-11 17:00:00", "jump": 0.55, "x_median_range": 2.4, "gap_min": 4320}, {"ts": "2007-01-12 17:00:00", "jump": 0.51, "x_median_range": 2.3, "gap_min": 1440}]` |
| @ED | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-16 16:00:00", "jump": 0.155, "x_median_range": 6.2, "gap_min": 4320}, {"ts": "2020-03-02 16:00:00", "jump": 0.115, "x_median_range": 5.7, "gap_min": 4320}]` |
| @EMD | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2020-03-16 16:00:00", "jump": -69.8, "x_median_range": 3.3, "gap_min": 4320}, {"ts": "2020-03-23 16:00:00", "jump": -44.7, "x_median_range": 2.0, "gap_min": 4320}]` |
| @ES.D | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2020-03-09 15:15:00", "jump": -201.75, "x_median_range": 10.8, "gap_min": 4320}, {"ts": "2020-03-16 15:15:00", "jump": -183.75, "x_median_range": 9.2, "gap_min": 4320}]` |
| @FC | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-24 13:05:00", "jump": 6.75, "x_median_range": 3.6, "gap_min": 1440}, {"ts": "2020-03-12 13:05:00", "jump": -5.45, "x_median_range": 3.0, "gap_min": 1440}]` |
| @FV | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-16 16:00:00", "jump": 1.515625, "x_median_range": 5.1, "gap_min": 4320}, {"ts": "2020-03-09 16:00:00", "jump": 0.5625, "x_median_range": 1.9, "gap_min": 4320}]` |
| @HG | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2010-03-01 17:00:00", "jump": 0.0915, "x_median_range": 1.1, "gap_min": 4320}, {"ts": "2018-12-03 17:00:00", "jump": 0.058, "x_median_range": 1.0, "gap_min": 4320}]` |
| @JY | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2019-01-03 16:00:00", "jump": 0.017, "x_median_range": 3.6, "gap_min": 1440}, {"ts": "2020-03-16 16:00:00", "jump": 0.0093, "x_median_range": 2.3, "gap_min": 4320}]` |
| @KC | 0 | 1.0 | 1.0 | 0.0 | `[{"ts": "2007-10-15 13:30:00", "jump": -8.0, "x_median_range": 3.8, "gap_min": 4320}, {"ts": "2007-10-01 13:30:00", "jump": 5.8, "x_median_range": 2.8, "gap_min": 4320}]` |
| @LC | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2007-07-27 13:05:00", "jump": 5.35, "x_median_range": 5.9, "gap_min": 1440}, {"ts": "2020-03-25 13:05:00", "jump": 4.5, "x_median_range": 3.6, "gap_min": 1440}]` |
| @LH | 0 | 0.948 | 0.948 | 0.2 | `[{"ts": "2014-03-31 13:05:00", "jump": -3.025, "x_median_range": 3.0, "gap_min": 4320}, {"ts": "2014-03-05 13:05:00", "jump": 2.7, "x_median_range": 3.0, "gap_min": 1440}]` |
| @M2K | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2019-05-06 16:00:00", "jump": -27.3, "x_median_range": 1.2, "gap_min": 4320}, {"ts": "2025-04-07 16:00:00", "jump": -48.1, "x_median_range": 1.2, "gap_min": 4320}]` |
| @MCL | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2025-06-23 17:00:00", "jump": 3.91, "x_median_range": 2.1, "gap_min": 4320}, {"ts": "2025-06-16 17:00:00", "jump": 3.54, "x_median_range": 2.0, "gap_min": 4320}]` |
| @MES | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-02 16:00:00", "jump": -84.75, "x_median_range": 3.4, "gap_min": 4320}, {"ts": "2020-03-30 16:00:00", "jump": -54.0, "x_median_range": 1.9, "gap_min": 4320}]` |
| @MES.D | 0 | 0.265 | 0.265 | 0.35 | `[{"ts": "2020-03-09 15:15:00", "jump": -191.25, "x_median_range": 10.2, "gap_min": 4320}, {"ts": "2020-03-16 15:15:00", "jump": -184.0, "x_median_range": 9.3, "gap_min": 4320}]` |
| @MNQ | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2020-03-02 16:00:00", "jump": -171.25, "x_median_range": 1.9, "gap_min": 4320}, {"ts": "2019-05-06 16:00:00", "jump": -123.75, "x_median_range": 1.3, "gap_min": 4320}]` |
| @MNQ.D | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2020-03-16 15:15:00", "jump": -521.25, "x_median_range": 6.9, "gap_min": 4320}, {"ts": "2020-03-09 15:15:00", "jump": -483.25, "x_median_range": 6.6, "gap_min": 4320}]` |
| @MP1 | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-16 16:00:00", "jump": 0.00104, "x_median_range": 2.7, "gap_min": 4320}, {"ts": "2020-03-09 16:00:00", "jump": -0.00095, "x_median_range": 2.6, "gap_min": 4320}]` |
| @NE1 | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2014-07-24 16:00:00", "jump": -0.0089, "x_median_range": 1.7, "gap_min": 1440}, {"ts": "2017-05-11 16:00:00", "jump": -0.0086, "x_median_range": 1.5, "gap_min": 1440}]` |
| @NG | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2018-11-19 17:00:00", "jump": 0.235, "x_median_range": 3.8, "gap_min": 4320}, {"ts": "2018-11-26 17:00:00", "jump": -0.242, "x_median_range": 3.5, "gap_min": 4320}]` |
| @NK | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2008-10-24 16:00:00", "jump": -790.0, "x_median_range": 2.9, "gap_min": 1440}, {"ts": "2008-10-13 16:00:00", "jump": 695.0, "x_median_range": 2.8, "gap_min": 4320}]` |
| @O | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2012-06-26 13:20:00", "jump": 24.25, "x_median_range": 2.9, "gap_min": 1440}, {"ts": "2010-06-15 13:20:00", "jump": 15.0, "x_median_range": 2.7, "gap_min": 1440}]` |
| @OJ | 664 | 1.0 | 1.0 | 0.25 | `[{"ts": "2007-10-12 14:00:00", "jump": 9.8, "x_median_range": 3.6, "gap_min": 1440}, {"ts": "2008-09-09 14:00:00", "jump": -9.05, "x_median_range": 3.1, "gap_min": 1440}]` |
| @QM | 33 | 0.378 | 0.378 | 0.25 | `[{"ts": "2020-03-09 17:00:00", "jump": -6.0, "x_median_range": 4.5, "gap_min": 4320}, {"ts": "2019-09-16 17:00:00", "jump": 5.0, "x_median_range": 3.1, "gap_min": 4320}]` |
| @RR | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2020-06-08 13:20:00", "jump": -1.5, "x_median_range": 5.6, "gap_min": 4320}, {"ts": "2020-06-09 13:20:00", "jump": -1.5, "x_median_range": 5.6, "gap_min": 1440}]` |
| @RTY | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-02 16:00:00", "jump": -39.8, "x_median_range": 2.1, "gap_min": 4320}, {"ts": "2020-03-09 16:00:00", "jump": -25.1, "x_median_range": 1.3, "gap_min": 4320}]` |
| @S | 630 | 1.0 | 1.0 | 0.1 | `[{"ts": "2009-06-30 13:20:00", "jump": 96.5, "x_median_range": 3.6, "gap_min": 1440}, {"ts": "2010-10-11 13:20:00", "jump": 38.0, "x_median_range": 2.5, "gap_min": 4320}]` |
| @SB | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2008-06-24 13:00:00", "jump": 1.12, "x_median_range": 2.8, "gap_min": 1440}, {"ts": "2008-01-17 13:00:00", "jump": 0.42, "x_median_range": 2.8, "gap_min": 1440}]` |
| @SF | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2015-01-16 16:00:00", "jump": -0.0162, "x_median_range": 2.1, "gap_min": 1440}, {"ts": "2018-12-10 16:00:00", "jump": 0.0103, "x_median_range": 1.9, "gap_min": 4320}]` |
| @SM | 1367 | 1.0 | 1.0 | 0.1 | `[{"ts": "2008-04-01 13:20:00", "jump": -19.3, "x_median_range": 2.2, "gap_min": 1440}, {"ts": "2010-10-11 13:20:00", "jump": 12.0, "x_median_range": 2.2, "gap_min": 4320}]` |
| @TU | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-16 16:00:00", "jump": 0.445312, "x_median_range": 4.7, "gap_min": 4320}, {"ts": "2015-02-26 16:00:00", "jump": 0.40625, "x_median_range": 4.3, "gap_min": 1440}]` |
| @US | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-16 16:00:00", "jump": 3.09375, "x_median_range": 2.4, "gap_min": 4320}, {"ts": "2020-03-09 16:00:00", "jump": 2.25, "x_median_range": 1.9, "gap_min": 4320}]` |
| @W | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2022-03-07 13:20:00", "jump": 85.0, "x_median_range": 4.0, "gap_min": 4320}, {"ts": "2022-03-04 13:20:00", "jump": 75.0, "x_median_range": 3.5, "gap_min": 1440}]` |
| @YM | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-02 16:00:00", "jump": -495.0, "x_median_range": 2.1, "gap_min": 4320}, {"ts": "2020-03-09 16:00:00", "jump": -423.0, "x_median_range": 1.7, "gap_min": 4320}]` |

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 233438 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 0 |
| nonpos_price | 9224 |
| null_cells | 0 |
| big_moves | 1823 |
| missing_bar_gaps | 0 |
| zero_volume_share_median_file | 0.0 |
| zero_volume_share_max_file | 0.0911 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 9 |
| files_with_nonpos_price | 8 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 298801, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 11807, "big_moves": 2333, "missing_bar_gaps": 0}` |

_Per-file statistics computed on 50 of 64 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: @ES, @NQ, @CL, @GC, @VX, @BTC, @TY, @EC, @C, @HO, @RB, @AD, @BO, @BP, @CD, @CT, @DX, @ED, @EMD, @ES.D, @FC, @FV, @HG, @JY, @KC, @LC, @LH, @M2K, @MCL, @MES, @MES.D, @MNQ, @MNQ.D, @MP1, @NE1, @NG, @NK, @O, @OJ, @QM, @RR, @RTY, @S, @SB, @SF, @SM, @TU, @US, @W, @YM

---

## ATM-FUT-DAILY — Ali Casy-ATM · US futures continuous contracts · daily (`Data Export,@SYM, Daily.csv`)

### 1. Location & pattern
| root | pattern | files | total size | extensions |
|---|---|---|---|---|
| `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07` | `Data Export,*, Daily.csv` | 64 | 14.9 MB | `{".csv": 64}` |

### 2. Probable source
**TradeStation chart export via 'Data Exporter v3.0' indicator (exported 2025-07-09)**

- Same 'Data Exporter v3.0' header block as ME-FUT-15M (`@SYM = <desc> Continuous Contract [Sep25]`, `Symbol,TimeFrame,Exchange,S.Start,S.End,$/Big Point,...`); `@` continuous symbols and the `$/Big Point` / `S.Start` / `S.End` fields are TradeStation/EasyLanguage conventions.
- Each series exists twice, as `.csv` and `.txt` (byte-identity checked in the 'ATM folder file variants' section).

### 3–4. Symbols & asset class
- Asset class guess: **futures (equity index, rates, FX, energy, metals, ags, softs, VIX, crypto)**
- 64 symbols; first 30: @AD, @BO, @BP, @BTC, @C, @CC, @CD, @CL, @CT, @DX, @E7, @EC, @ED, @EMD, @ES, @ES.D, @ETH, @FC, @FV, @GC, @HG, @HO, @J7, @JY, @KC, @KW, @LC, @LH, @M2K, @MBT

### 5. Timeframe
- Dominant timeframe (median diff of consecutive timestamps, per file): **1d** in 50 of 50 deep-sample files; the other 0 files are sparse (illiquid symbols with missing bars, so the median gap exceeds the bar size): `{"1d": 50}`
- Most frequent spacing per file (bar grid): `{"1d": 50}` → mixed timeframes: False; median share of diffs equal to the median: 0.784

### 6. Date range
- Across all 64 files (light pass: head/tail lines or parquet min/max): first ts `{"min": "2006-05-30 13:00:00", "median": "2006-05-30 16:00:00", "max": "2022-10-13 16:00:00"}`; last ts `{"min": "2023-05-19 16:00:00", "median": "2025-07-08 16:00:00", "max": "2025-07-08 17:00:00"}`

| symbol | description | tag | exch | S.Start | S.End | $/pt | tick | first | last | size |
|---|---|---|---|---|---|---|---|---|---|---|
| @AD | Australian Dollar Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 265.5 KB |
| @BO | Soybean Oil Continuous Contract [Dec25] | Dec25 | CBOT | 1900 | 1320 | 600 | 0.01 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 224.5 KB |
| @BP | British Pound Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 247.1 KB |
| @BTC | Bitcoin Futures based on BRR Continuous Contract... | — | CME | 1700 | 1600 | 5 | 5 | 2018-05-07 16:00:00 | 2025-07-08 16:00:00 | 83.9 KB |
| @C | Corn Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 248.1 KB |
| @CC | Cocoa Continuous Contract [Sep25] | Sep25 | ICEUS | 445 | 1330 | 10 | 1 | 2006-05-30 13:30:00 | 2025-07-08 13:30:00 | 211.3 KB |
| @CD | Canadian Dollar Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 264.5 KB |
| @CL | Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 1000 | 0.01 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 234.6 KB |
| @CT | Cotton No. 2 Continuous Contract [Dec25] | Dec25 | ICEUS | 2100 | 1420 | 500 | 0.01 | 2006-05-30 14:20:00 | 2025-07-08 14:20:00 | 225.4 KB |
| @DX | U.S. Dollar Index Continuous Contract [Sep25] | Sep25 | ICEUS | 2000 | 1700 | 1000 | 0.005 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 246.5 KB |
| @E7 | E-Mini Euro FX Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 240.8 KB |
| @EC | Euro FX Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 268.3 KB |
| @ED | Eurodollar Continuous Contract [Sep23] | Sep23 | CME | 1700 | 1600 | 2500 | 0.0025 | 2006-05-30 16:00:00 | 2023-05-19 16:00:00 | 238.1 KB |
| @EMD | E-Mini S&P MidCap 400 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100 | 0.1 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 242.0 KB |
| @ES | E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 50 | 0.25 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 272.8 KB |
| @ES.D | E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 50 | 0.25 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 272.8 KB |
| @ETH | CME Ether Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 50 | 0.5 | 2021-07-01 16:00:00 | 2025-07-08 16:00:00 | 50.7 KB |
| @FC | Feeder Cattle Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 500 | 0.025 | 2007-04-17 13:05:00 | 2025-07-08 13:05:00 | 247.0 KB |
| @FV | 5 Yr U.S.Treasury Notes Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 1000 | 0.0078125 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 341.3 KB |
| @GC | Gold Continuous Contract [Aug25] | Aug25 | COMEX | 1800 | 1700 | 100 | 0.1 | 2006-05-31 17:00:00 | 2025-07-08 17:00:00 | 248.8 KB |
| @HG | Copper Continuous Contract [Sep25] | Sep25 | COMEX | 1800 | 1700 | 25000 | 0.0005 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 244.9 KB |
| @HO | Heating Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 42000 | 0.0001 | 2006-05-31 17:00:00 | 2025-07-08 17:00:00 | 257.6 KB |
| @J7 | E-Mini Japanese Yen Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 62500 | 0.0001 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 236.0 KB |
| @JY | Japanese Yen Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 266.9 KB |
| @KC | Coffee C Continuous Contract [Sep25] | Sep25 | ICEUS | 415 | 1330 | 375 | 0.05 | 2006-05-30 13:30:00 | 2025-07-08 13:30:00 | 241.5 KB |
| @KW | Hard Red Winter Wheat Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2008-09-23 13:20:00 | 2025-07-08 13:20:00 | 221.3 KB |
| @LC | Live Cattle Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 400 | 0.025 | 2006-05-30 13:05:00 | 2025-07-08 13:05:00 | 263.3 KB |
| @LH | Lean Hogs Continuous Contract [Aug25] | Aug25 | CME | 830 | 1305 | 400 | 0.025 | 2006-05-30 13:05:00 | 2025-07-08 13:05:00 | 260.0 KB |
| @M2K | Micro E-mini Russell 2000 Continuous Contract [S... | — | CME | 1700 | 1600 | 5 | 0.1 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 242.1 KB |
| @MBT | Micro Bitcoin Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 0 | 5 | 2021-09-23 16:00:00 | 2025-07-08 16:00:00 | 45.0 KB |
| @MCL | Micro Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 100 | 0.01 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 233.9 KB |
| @MES | Micro E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 5 | 0.25 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 272.0 KB |
| @MES.D | Micro E-mini S&P 500 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 5 | 0.25 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 272.0 KB |
| @MET | Micro Ether Futures Continuous Contract [Jul25] | Jul25 | CME | 1700 | 1600 | 0 | 0.5 | 2022-10-13 16:00:00 | 2025-07-08 16:00:00 | 34.9 KB |
| @MNQ | Micro E-mini Nasdaq-100 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 2 | 0.25 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 275.3 KB |
| @MNQ.D | Micro E-mini Nasdaq-100 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 2 | 0.25 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 275.3 KB |
| @MP1 | Mexican Peso Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 500000 | 0.00001 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 263.9 KB |
| @MYM | Micro E-mini Dow Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 0 | 1 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 228.6 KB |
| @NE1 | New Zealand Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 100000 | 0.00005 | 2014-05-06 16:00:00 | 2025-07-08 16:00:00 | 154.1 KB |
| @NG | Natural Gas Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 10000 | 0.001 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 239.4 KB |
| @NK | Nikkei 225 USD Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 5 | 5 | 2006-12-13 16:00:00 | 2025-07-08 16:00:00 | 213.3 KB |
| @NQ | E-Mini NASDAQ-100 Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 20 | 0.25 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 274.5 KB |
| @NQ.D | E-Mini NASDAQ-100 Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 20 | 0.25 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 274.5 KB |
| @O | Oats Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-05-31 13:20:00 | 2025-07-08 13:20:00 | 235.1 KB |
| @OJ | Frozen Concentrated OJ Continuous Contract [Sep25] | Sep25 | ICEUS | 800 | 1400 | 150 | 0.05 | 2006-05-30 14:00:00 | 2025-07-08 14:00:00 | 221.0 KB |
| @PL | Platinum Continuous Contract [Oct25] | Oct25 | NYMEX | 1800 | 1700 | 50 | 0.1 | 2006-05-31 17:00:00 | 2025-07-08 17:00:00 | 240.3 KB |
| @QM | E-mini Crude Oil Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 500 | 0.025 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 247.6 KB |
| @RB | NYHarborBlendstock RBOB Continuous Contract [Aug25] | Aug25 | NYMEX | 1800 | 1700 | 42000 | 0.0001 | 2006-05-31 17:00:00 | 2025-07-08 17:00:00 | 255.2 KB |
| @RR | Rough Rice Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 2000 | 0.005 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 236.0 KB |
| @RTY | Emini Russell 2000 Idx Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 50 | 0.1 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 243.1 KB |
| @RTY.D | Emini Russell 2000 Idx Continuous Contract [Sep25] | Sep25 | CME | 830 | 1515 | 50 | 0.1 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 241.9 KB |
| @S | Soybeans Continuous Contract [Nov25] | Nov25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 251.5 KB |
| @SB | Sugar No. 11 Continuous Contract [Oct25] | Oct25 | ICEUS | 330 | 1300 | 1120 | 0.01 | 2006-05-30 13:00:00 | 2025-07-08 13:00:00 | 223.7 KB |
| @SF | Swiss Franc Continuous Contract [Sep25] | Sep25 | CME | 1700 | 1600 | 125000 | 0.00005 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 263.9 KB |
| @SI | Silver Continuous Contract [Sep25] | Sep25 | COMEX | 1800 | 1700 | 5000 | 0.005 | 2006-05-30 17:00:00 | 2025-07-08 17:00:00 | 245.0 KB |
| @SM | Soybean Meal Continuous Contract [Dec25] | Dec25 | CBOT | 1900 | 1320 | 100 | 0.1 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 227.4 KB |
| @TU | 2 Year U.S. Treasury Notes Continuous Contract [... | — | CBOT | 1700 | 1600 | 2000 | 0.00390625 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 360.5 KB |
| @TY | 10 Yr U.S. Treasury Notes Continuous Contract [S... | — | CBOT | 1700 | 1600 | 1000 | 0.015625 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 323.7 KB |
| @US | 30 Yr U.S.Treasury Bonds Continuous Contract [Se... | — | CBOT | 1700 | 1600 | 1000 | 0.03125 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 301.1 KB |
| @VX | CBOE Volatility Index Continuous Contract [Jul25] | Jul25 | CBOEF | 1700 | 1600 | 1000 | 0.05 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 238.0 KB |
| @VXM | Mini-VIX Futures Continuous Contract [Jul25] | Jul25 | CBOEF | 1700 | 1600 | 100 | 0.01 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 236.0 KB |
| @W | Wheat Continuous Contract [Sep25] | Sep25 | CBOT | 1900 | 1320 | 50 | 0.25 | 2006-05-30 13:20:00 | 2025-07-08 13:20:00 | 256.5 KB |
| @YM | E-mini Dow Futures ($5) Continuous Contract [Sep25] | Sep25 | CBOT | 1700 | 1600 | 5 | 1 | 2006-05-30 16:00:00 | 2025-07-08 16:00:00 | 229.3 KB |
| @YM.D | E-mini Dow Futures ($5) Continuous Contract [Sep25] | Sep25 | CBOT | 830 | 1515 | 5 | 1 | 2006-05-30 15:15:00 | 2025-07-08 15:15:00 | 229.5 KB |

### 7. Schema
Representative file: `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, Daily.csv`

`{"Date": "str (text file; parsed as noted)", "Time": "str (text file; parsed as noted)", "Open": "str (text file; parsed as noted)", "High": "str (text file; parsed as noted)", "Low": "str (text file; parsed as noted)", "Close": "str (text file; parsed as noted)", "Volume": "str (text file; parsed as noted)"}`

Column presence: `{"open": true, "high": true, "low": true, "close": true, "vol": true, "vwap": false, "trade": false, "bid": false, "ask": false, "spread": false, "openint": false}`

### 8. Raw samples (verbatim)
File: `F:\AmerAndish\Projects\Trade\Ali Casy-ATM\Historical Data - 2025-07-07\Data Export,@ES, Daily.csv`

First 5 rows (with header lines):
```
Data Exporter v3.0  ,  2022
 
@ES = E-mini S&P 500 Continuous Contract [Sep25]

Symbol,TimeFrame,Exchange,S.Start,S.End,$/Big Point,Tick Size,$Tick Size,#Ticks/Point,Avg Vol,Avg ATR,Avg $ATR
@ES,Daily,CME,1700,1600,50,0.25,12.50,4,937953,12.61,630

Date,Time,Open,High,Low,Close,Volume
05/30/2006,16:00,1714.00,1715.00,1691.00,1691.75,1047920
05/31/2006,16:00,1692.25,1705.00,1687.75,1703.75,1229566
06/01/2006,16:00,1704.75,1719.50,1698.00,1717.50,1058355
06/02/2006,16:00,1717.50,1725.75,1713.00,1720.00,1108009
06/05/2006,16:00,1719.50,1720.25,1697.50,1701.25,1170669
```
Last 3 rows:
```
07/03/2025,16:00,6276.50,6333.25,6270.50,6324.25,750998
07/07/2025,16:00,6307.75,6315.00,6246.25,6276.00,1193522
07/08/2025,16:00,6262.50,6289.00,6254.50,6272.00,1073914
```

### 9–12. Timestamp format, timezone, session, weekend, price type
- `Date` = `MM/DD/YYYY`, `Time` = `HH:MM`, **naive**, separate columns.
- Across the sample, bars labelled exactly at header `S.Start`: 0; at `S.Start`+1 bar (1d): 0; at `S.End`: 235012. S.End present and S.Start (almost) absent → labels are **bar-end** (TradeStation convention).
- @ES first bar of each session, winter (Dec–Feb): `{"Mon 16:00": 196, "Tue 16:00": 49, "Thu 16:00": 7, "Wed 16:00": 6}`; summer (Jun–Aug): `{"Mon 16:00": 249, "Tue 16:00": 9, "Thu 16:00": 4, "Fri 16:00": 4}` → identical wall-clock across DST ⇒ timestamps are **exchange-local time (US/Central for CME, with DST)**, not UTC.
- @ES weekday counts: `{"Mon": 904, "Tue": 989, "Wed": 986, "Thu": 970, "Fri": 970}` → Sunday bars are the Globex evening open (17:00 CT Sunday).
- Exchanges in headers: `{"CME": 31, "CBOT": 15, "ICEUS": 6, "NYMEX": 7, "COMEX": 3, "CBOEF": 2}` — ICE/NYBOT softs would be exported in their own local (US/Eastern) time if TradeStation's default 'exchange time' setting was used (to confirm).

### 13–14. Adjustment / futures specifics
- Series type: header contract tags `{"Sep25": 37, "Dec25": 3, "null": 5, "Aug25": 10, "Sep23": 1, "Jul25": 5, "Oct25": 2, "Nov25": 1}`; descriptions say `Continuous Contract` → **continuous series** (one file per root); last timestamp across files: 2025-07-08 17:00:00.
- Bars with low ≤ 0 across sample: 9134 (back-adjusted series can go negative).
- Contracts with bars at price ≤ 0: @CL (33), @HO (3338), @RB (2722), @CT (308), @MCL (33), @OJ (664), @QM (33), @S (634), @SM (1369). Real prices of these contracts never went ≤ 0 (except WTI crude in April 2020), so this is the signature of **additive back-adjustment**.
- Roll gaps: median share of each contract's 20 largest open-vs-previous-close jumps that fall in a quarterly roll window (5th–16th of Mar/Jun/Sep/Dec ≈ 13% of days): 0.17 → no clustering at roll dates; the largest jumps are weekend/news gaps → roll gaps have been removed (consistent with back-adjusted continuous series).

Tick-grid test (share of closes that are exact multiples of the header tick size; additive back-adjustment keeps prices on the grid, ratio adjustment breaks it) and largest open-vs-previous-close jumps (in multiples of the rolling median bar range; roll gaps would cluster in roll windows):

| symbol | bars ≤ 0 | on-grid first 20k | on-grid last 20k | top-20 jumps in Mar/Jun/Sep/Dec 5–16 | top 2 jumps |
|---|---|---|---|---|---|
| @ES | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-23 16:00:00", "jump": -68.25, "x_median_range": 2.5, "gap_min": 4320}, {"ts": "2020-03-30 16:00:00", "jump": -65.0, "x_median_range": 2.3, "gap_min": 4320}]` |
| @NQ | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2025-04-03 16:00:00", "jump": -738.0, "x_median_range": 1.9, "gap_min": 1440}, {"ts": "2020-03-23 16:00:00", "jump": -171.0, "x_median_range": 1.7, "gap_min": 4320}]` |
| @CL | 33 | 1.0 | 1.0 | 0.35 | `[{"ts": "2020-03-09 17:00:00", "jump": -8.41, "x_median_range": 6.2, "gap_min": 4320}, {"ts": "2019-09-16 17:00:00", "jump": 6.63, "x_median_range": 4.1, "gap_min": 4320}]` |
| @GC | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2020-03-16 17:00:00", "jump": 47.1, "x_median_range": 3.0, "gap_min": 4320}, {"ts": "2007-02-28 17:00:00", "jump": -17.8, "x_median_range": 2.4, "gap_min": 1440}]` |
| @VX | 0 | 0.09 | 0.09 | 0.15 | `[{"ts": "2014-04-07 16:00:00", "jump": -8.05, "x_median_range": 14.6, "gap_min": 4320}, {"ts": "2014-03-17 16:00:00", "jump": -5.0, "x_median_range": 9.1, "gap_min": 4320}]` |
| @BTC | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2019-05-20 16:00:00", "jump": 895.0, "x_median_range": 6.9, "gap_min": 4320}, {"ts": "2021-01-04 16:00:00", "jump": 4020.0, "x_median_range": 6.6, "gap_min": 5760}]` |
| @TY | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2020-03-16 16:00:00", "jump": 1.984375, "x_median_range": 3.7, "gap_min": 4320}, {"ts": "2015-06-29 16:00:00", "jump": 1.296875, "x_median_range": 2.0, "gap_min": 4320}]` |
| @EC | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2017-04-24 16:00:00", "jump": 0.0169, "x_median_range": 2.2, "gap_min": 4320}, {"ts": "2020-03-16 16:00:00", "jump": 0.00895, "x_median_range": 1.9, "gap_min": 4320}]` |
| @C | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2010-10-11 13:20:00", "jump": 45.0, "x_median_range": 4.5, "gap_min": 4320}, {"ts": "2007-01-16 13:20:00", "jump": 20.0, "x_median_range": 2.5, "gap_min": 5760}]` |
| @HO | 3338 | 1.0 | 1.0 | 0.35 | `[{"ts": "2020-03-09 17:00:00", "jump": -0.1572, "x_median_range": 3.7, "gap_min": 4320}, {"ts": "2025-06-23 17:00:00", "jump": 0.1344, "x_median_range": 2.4, "gap_min": 4320}]` |
| @RB | 2722 | 1.0 | 1.0 | 0.35 | `[{"ts": "2020-03-09 17:00:00", "jump": -0.1566, "x_median_range": 3.5, "gap_min": 4320}, {"ts": "2017-08-28 17:00:00", "jump": 0.0935, "x_median_range": 2.4, "gap_min": 4320}]` |
| @AD | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2020-03-16 16:00:00", "jump": 0.0127, "x_median_range": 3.1, "gap_min": 4320}, {"ts": "2011-08-10 16:00:00", "jump": 0.031, "x_median_range": 2.7, "gap_min": 1440}]` |
| @BO | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2008-02-28 13:20:00", "jump": 1.98, "x_median_range": 2.3, "gap_min": 1440}, {"ts": "2008-03-10 13:20:00", "jump": -2.0, "x_median_range": 2.2, "gap_min": 4320}]` |
| @BP | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2019-12-13 16:00:00", "jump": 0.0305, "x_median_range": 3.5, "gap_min": 1440}, {"ts": "2017-06-09 16:00:00", "jump": -0.0202, "x_median_range": 2.3, "gap_min": 1440}]` |
| @CD | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-16 16:00:00", "jump": 0.00775, "x_median_range": 2.8, "gap_min": 4320}, {"ts": "2025-02-03 16:00:00", "jump": -0.0095, "x_median_range": 2.7, "gap_min": 4320}]` |
| @CT | 308 | 1.0 | 1.0 | 0.1 | `[{"ts": "2008-03-04 14:20:00", "jump": 4.0, "x_median_range": 4.4, "gap_min": 1440}, {"ts": "2008-01-14 14:20:00", "jump": 3.0, "x_median_range": 3.5, "gap_min": 4320}]` |
| @DX | 0 | 0.197 | 0.197 | 0.15 | `[{"ts": "2007-08-06 17:00:00", "jump": -0.68, "x_median_range": 3.3, "gap_min": 4320}, {"ts": "2008-03-11 17:00:00", "jump": 1.295, "x_median_range": 2.7, "gap_min": 1440}]` |
| @ED | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2007-08-24 16:00:00", "jump": -0.42, "x_median_range": 21.0, "gap_min": 1440}, {"ts": "2020-03-16 16:00:00", "jump": 0.16, "x_median_range": 6.4, "gap_min": 4320}]` |
| @EMD | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-16 16:00:00", "jump": -77.3, "x_median_range": 3.6, "gap_min": 4320}, {"ts": "2020-03-23 16:00:00", "jump": -62.9, "x_median_range": 2.7, "gap_min": 4320}]` |
| @ES.D | 0 | 0.999 | 0.999 | 0.35 | `[{"ts": "2020-03-09 15:15:00", "jump": -202.0, "x_median_range": 10.8, "gap_min": 4320}, {"ts": "2020-03-16 15:15:00", "jump": -182.5, "x_median_range": 9.2, "gap_min": 4320}]` |
| @FC | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-24 13:05:00", "jump": 6.75, "x_median_range": 3.6, "gap_min": 1440}, {"ts": "2020-03-09 13:05:00", "jump": -4.5, "x_median_range": 2.5, "gap_min": 4320}]` |
| @FV | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2020-03-16 16:00:00", "jump": 1.5, "x_median_range": 5.1, "gap_min": 4320}, {"ts": "2018-05-29 16:00:00", "jump": 0.554688, "x_median_range": 2.3, "gap_min": 5760}]` |
| @HG | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2025-04-10 17:00:00", "jump": 0.274, "x_median_range": 3.0, "gap_min": 1440}, {"ts": "2025-02-26 17:00:00", "jump": 0.18, "x_median_range": 2.2, "gap_min": 1440}]` |
| @JY | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2019-01-03 16:00:00", "jump": 0.0193, "x_median_range": 4.0, "gap_min": 1440}, {"ts": "2020-03-16 16:00:00", "jump": 0.01125, "x_median_range": 2.8, "gap_min": 4320}]` |
| @KC | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2007-10-15 13:30:00", "jump": -10.05, "x_median_range": 4.8, "gap_min": 4320}, {"ts": "2021-07-23 13:30:00", "jump": 11.45, "x_median_range": 2.8, "gap_min": 1440}]` |
| @LC | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2020-03-25 13:05:00", "jump": 4.5, "x_median_range": 3.6, "gap_min": 1440}, {"ts": "2020-03-16 13:05:00", "jump": -4.5, "x_median_range": 3.6, "gap_min": 4320}]` |
| @LH | 0 | 0.948 | 0.948 | 0.15 | `[{"ts": "2020-04-06 13:05:00", "jump": -4.5, "x_median_range": 2.7, "gap_min": 4320}, {"ts": "2020-04-02 13:05:00", "jump": -4.5, "x_median_range": 2.7, "gap_min": 1440}]` |
| @M2K | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2015-08-24 16:00:00", "jump": -51.3, "x_median_range": 3.1, "gap_min": 4320}, {"ts": "2025-04-03 16:00:00", "jump": -91.2, "x_median_range": 2.1, "gap_min": 1440}]` |
| @MCL | 33 | 1.0 | 1.0 | 0.3 | `[{"ts": "2020-03-09 17:00:00", "jump": -8.41, "x_median_range": 6.1, "gap_min": 4320}, {"ts": "2019-09-16 17:00:00", "jump": 6.63, "x_median_range": 4.1, "gap_min": 4320}]` |
| @MES | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2020-03-23 16:00:00", "jump": -68.0, "x_median_range": 2.5, "gap_min": 4320}, {"ts": "2020-03-30 16:00:00", "jump": -59.0, "x_median_range": 2.0, "gap_min": 4320}]` |
| @MES.D | 0 | 0.265 | 0.265 | 0.35 | `[{"ts": "2020-03-09 15:15:00", "jump": -191.0, "x_median_range": 10.2, "gap_min": 4320}, {"ts": "2020-03-16 15:15:00", "jump": -182.5, "x_median_range": 9.2, "gap_min": 4320}]` |
| @MNQ | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2025-04-03 16:00:00", "jump": -734.5, "x_median_range": 1.9, "gap_min": 1440}, {"ts": "2009-11-27 16:00:00", "jump": -41.75, "x_median_range": 1.5, "gap_min": 2880}]` |
| @MNQ.D | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2020-03-16 15:15:00", "jump": -519.5, "x_median_range": 6.8, "gap_min": 4320}, {"ts": "2020-03-09 15:15:00", "jump": -481.25, "x_median_range": 6.5, "gap_min": 4320}]` |
| @MP1 | 0 | 1.0 | 1.0 | 0.35 | `[{"ts": "2011-08-10 16:00:00", "jump": 0.0026, "x_median_range": 3.9, "gap_min": 1440}, {"ts": "2019-06-10 16:00:00", "jump": 0.0015, "x_median_range": 3.5, "gap_min": 4320}]` |
| @NE1 | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2025-05-23 16:00:00", "jump": -0.59055, "x_median_range": 109.4, "gap_min": 1440}, {"ts": "2025-01-21 16:00:00", "jump": 0.00865, "x_median_range": 1.7, "gap_min": 5760}]` |
| @NG | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2018-11-19 17:00:00", "jump": 0.353, "x_median_range": 5.7, "gap_min": 4320}, {"ts": "2018-11-26 17:00:00", "jump": -0.241, "x_median_range": 3.6, "gap_min": 4320}]` |
| @NK | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2008-10-13 16:00:00", "jump": 695.0, "x_median_range": 2.7, "gap_min": 4320}, {"ts": "2009-11-27 16:00:00", "jump": -345.0, "x_median_range": 2.3, "gap_min": 2880}]` |
| @O | 0 | 1.0 | 1.0 | 0.1 | `[{"ts": "2012-06-26 13:20:00", "jump": 22.75, "x_median_range": 2.7, "gap_min": 1440}, {"ts": "2012-06-25 13:20:00", "jump": 12.5, "x_median_range": 1.5, "gap_min": 4320}]` |
| @OJ | 664 | 1.0 | 1.0 | 0.15 | `[{"ts": "2007-10-12 14:00:00", "jump": 10.0, "x_median_range": 3.3, "gap_min": 1440}, {"ts": "2007-02-26 14:00:00", "jump": -7.85, "x_median_range": 2.9, "gap_min": 4320}]` |
| @QM | 33 | 0.388 | 0.388 | 0.25 | `[{"ts": "2020-03-09 17:00:00", "jump": -5.725, "x_median_range": 4.2, "gap_min": 4320}, {"ts": "2007-10-11 17:00:00", "jump": -6.15, "x_median_range": 3.6, "gap_min": 1440}]` |
| @RR | 0 | 1.0 | 1.0 | 0.3 | `[{"ts": "2020-06-08 13:20:00", "jump": -1.5, "x_median_range": 5.6, "gap_min": 4320}, {"ts": "2020-06-09 13:20:00", "jump": -1.5, "x_median_range": 5.6, "gap_min": 1440}]` |
| @RTY | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2015-08-24 16:00:00", "jump": -51.3, "x_median_range": 3.1, "gap_min": 4320}, {"ts": "2025-04-03 16:00:00", "jump": -92.1, "x_median_range": 2.1, "gap_min": 1440}]` |
| @S | 634 | 1.0 | 1.0 | 0.1 | `[{"ts": "2018-04-06 13:20:00", "jump": -28.25, "x_median_range": 2.4, "gap_min": 1440}, {"ts": "2008-03-18 13:20:00", "jump": -48.25, "x_median_range": 1.9, "gap_min": 1440}]` |
| @SB | 0 | 1.0 | 1.0 | 0.05 | `[{"ts": "2008-06-24 13:00:00", "jump": 1.24, "x_median_range": 3.0, "gap_min": 1440}, {"ts": "2008-01-17 13:00:00", "jump": 0.42, "x_median_range": 2.8, "gap_min": 1440}]` |
| @SF | 0 | 1.0 | 1.0 | 0.25 | `[{"ts": "2015-01-16 16:00:00", "jump": 0.0291, "x_median_range": 3.8, "gap_min": 1440}, {"ts": "2015-01-20 16:00:00", "jump": -0.0289, "x_median_range": 3.8, "gap_min": 5760}]` |
| @SM | 1369 | 1.0 | 1.0 | 0.05 | `[{"ts": "2007-07-20 13:20:00", "jump": 10.0, "x_median_range": 2.1, "gap_min": 1440}, {"ts": "2010-10-11 13:20:00", "jump": 9.8, "x_median_range": 1.8, "gap_min": 4320}]` |
| @TU | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-16 16:00:00", "jump": 0.433594, "x_median_range": 4.4, "gap_min": 4320}, {"ts": "2018-05-29 16:00:00", "jump": 0.28125, "x_median_range": 3.6, "gap_min": 5760}]` |
| @US | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2020-03-16 16:00:00", "jump": 2.90625, "x_median_range": 2.2, "gap_min": 4320}, {"ts": "2020-03-23 16:00:00", "jump": 2.625, "x_median_range": 1.8, "gap_min": 4320}]` |
| @W | 0 | 1.0 | 1.0 | 0.15 | `[{"ts": "2022-03-07 13:20:00", "jump": 85.0, "x_median_range": 4.0, "gap_min": 4320}, {"ts": "2022-03-04 13:20:00", "jump": 75.0, "x_median_range": 3.5, "gap_min": 1440}]` |
| @YM | 0 | 1.0 | 1.0 | 0.2 | `[{"ts": "2020-03-23 16:00:00", "jump": -536.0, "x_median_range": 1.9, "gap_min": 4320}, {"ts": "2020-03-09 16:00:00", "jump": -433.0, "x_median_range": 1.7, "gap_min": 4320}]` |

### 15. Quality quick-scan (deep sample)
| metric | value |
|---|---|
| rows | 235012 |
| dup_ts | 0 |
| non_monotonic | 0 |
| high_lt_low | 0 |
| ohlc_outside_range | 1 |
| nonpos_price | 9134 |
| null_cells | 0 |
| big_moves | 1819 |
| missing_bar_gaps | 0 |
| zero_volume_share_median_file | 0.0002 |
| zero_volume_share_max_file | 0.0067 |
| files_with_any_dup_ts | 0 |
| files_with_big_moves | 10 |
| files_with_nonpos_price | 9 |
| files_with_high_lt_low | 0 |
| files_in_sample | 50 |
| extrapolated_to_all_files | `{"rows": 300815, "dup_ts": 0, "high_lt_low": 0, "nonpos_price": 11692, "big_moves": 2328, "missing_bar_gaps": 0}` |

_Per-file statistics computed on 50 of 64 files (task limit 50); `extrapolated_to_all_files` scales sample totals by file count and is an estimate._

Deep-sample symbols: @ES, @NQ, @CL, @GC, @VX, @BTC, @TY, @EC, @C, @HO, @RB, @AD, @BO, @BP, @CD, @CT, @DX, @ED, @EMD, @ES.D, @FC, @FV, @HG, @JY, @KC, @LC, @LH, @M2K, @MCL, @MES, @MES.D, @MNQ, @MNQ.D, @MP1, @NE1, @NG, @NK, @O, @OJ, @QM, @RR, @RTY, @S, @SB, @SF, @SM, @TU, @US, @W, @YM

---

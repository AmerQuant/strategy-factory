# configs/pipeline

Pipeline run configurations (`sfac run --config configs/pipeline/<name>.yaml`):
universe, timeframes, stages to run and their parameters (`sample_h1.yaml`, `mvp_daily.yaml`, T10a).

`sfac config resolve <file>` fills the two resolved sections and prints the run `config_hash`:

- `data_snapshots` — the catalog reference snapshot of every (symbol, timeframe);
- `cost_inputs` (T10b) — the content hash of each symbol's resolved cost profile, the SHA-256
  of the broker spec behind the Moneta profiles (D-340), `configs/data/fx_conversion.yaml`
  (pairs and pegs, D-307) and the conversion pairs' snapshot hashes (D-316).

A config may carry an `engine:` section with the T08 settings (`initial_capital`, `notional`,
`disaster_stop_atr`, `atr_length` D-343, `futures_contracts`, `parity_qty_step` D-347); it is
validated by the same model as `configs/engine/default.yaml`, and it is part of `config_hash`
together with `intrabar_mode`. A parity run (`intrabar_mode: tradingview`) without
`engine.parity_qty_step` is refused (D-347).

`executor.yaml` (T10b, F-0.3.7) holds the execution budget: workers, Numba threads per worker
(D-334) and the grid chunk budget `max_grid_bytes` (D-331). It is not part of `config_hash`:
it decides how fast a run is, never what it computes.

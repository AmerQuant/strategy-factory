# configs/gates

Declarative gate definitions (thresholds and decision numbers) evaluated by
`strategy_factory.gates`. No threshold lives in code; defaults are defined in the config
models and documented in the spec. `default.yaml`: stages 1-3 (MVP) and 1-S, 4-7 (used from P1), T10a.

**Metric names (D-309, T10b):** every `metric:` in this folder must be registered in
`strategy_factory.metrics.names`. `load_gate_config` validates the base stages and every
override against that registry, so an unknown name is an error when the file loads, not a
criterion that fails silently with `metric_missing`.

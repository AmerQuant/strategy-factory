# configs/parity

One file per TradingView parity reference (T11, D-348). Each holds the exported file names,
**every** Strategy Property of the Pine script (`pine:`), the engine inputs a parity run needs
(`engine:` — `parity_qty_step` D-347 and the Pine `atr_length` D-343) and the `BacktestSpec`
that reproduces the strategy.

Every `pine` field is **required**: a parity result whose settings are unknown proves nothing.
Costs come from the `pine` block alone (**D-362**) — never from a Moneta profile — and the
broker volume step and minimum never apply (D-347).

The two files here are **templates**: their `pine` values are placeholders and `strategy` is
empty until the user supplies the Pine sources and Strategy Properties (D-361). They are
validated by the tests for shape, not used for a run.

# ADR-001: Custom Numba backtest engine; vectorbt only as test oracle

- **Status:** Accepted
- **Date:** 2026-09-19

## Decision

موتور اختصاصی Numba؛ vectorbt فقط اوراکل تست

_English:_ Custom backtest engine in NumPy/Numba; open-source vectorbt is used only as a test oracle.

_Source: design document v1.0, §14 (decision log); rationale in §2._

## Update (2026-09-20, D-346)

The custom Numba engine stands. The **test oracle is not vectorbt**: it fails at import with the
plotly version this project resolves, and making it work would pin `plotly<6` against ADR-008.
The oracle is a naive pure-Python reference engine (`tests/oracle/naive_engine.py`, D-330) and
the external check is the TradingView parity test (T11, F-0.3.8).

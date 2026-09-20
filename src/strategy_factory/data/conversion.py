"""Quote-currency -> USD conversion series (D-307, D-316, D-328).

``configs/data/fx_conversion.yaml`` maps a quote currency to its conversion pair (or a fixed
peg). The conversion series of a traded symbol is an **auxiliary input**: it is read through
:class:`~strategy_factory.data.split.DataAccess` (development runs) or together with the
traded candidate's one-shot holdout access (:meth:`SplitManager.open_holdout_with_conversion`),
always over the traded symbol's own window and never beyond its end; the conversion pair's
own holdout is not consumed (D-316).

Alignment to the traded bars ``ts`` (bar starts, µs UTC), no look-ahead:

* ``fx_close[t]``: the close of the pair bar starting at ``t`` (the same bar, D-307); if that
  bar is missing, the close of the last pair bar that started before ``t``;
* ``fx_open[t]`` (sizing at the fill, D-328): the open of the pair bar starting at ``t``; if
  that bar is missing, the close of the last pair bar that started before ``t``.

A traded bar before the first pair bar is an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from strategy_factory.core.errors import ConfigError, DataError

DEFAULT_FX_CONFIG = Path("configs") / "data" / "fx_conversion.yaml"
F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PairRule(_Frozen):
    pair: str = Field(min_length=6)
    invert: bool


class FxConversionConfig(_Frozen):
    pairs: dict[str, PairRule]
    pegs: dict[str, float] = Field(default_factory=dict)

    def pair_for(self, quote_ccy: str) -> PairRule | None:
        return self.pairs.get(quote_ccy)


def load_fx_config(path: Path | None = None) -> FxConversionConfig:
    target = path if path is not None else DEFAULT_FX_CONFIG
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        cfg = FxConversionConfig.model_validate(data)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read FX conversion config: {exc}", config_path=target) from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid FX conversion config: {exc}", config_path=target) from exc
    if any(v <= 0 for v in cfg.pegs.values()):
        raise ConfigError("pegs must be positive", config_path=target)
    return cfg


@dataclass(frozen=True)
class ConversionArrays:
    """USD per unit of quote currency at each traded bar."""

    fx_open: F64
    fx_close: F64
    quote_ccy: str
    source: str  # "USD", the pair symbol, or "peg:<value>"
    peg: bool = False


def usd(n: int) -> ConversionArrays:
    one = np.ones(n)
    return ConversionArrays(one, one.copy(), "USD", "USD")


def align_pair(
    traded_ts: I64, pair_ts: I64, pair_open: F64, pair_close: F64, invert: bool
) -> tuple[F64, F64]:
    """``(fx_open, fx_close)`` aligned to ``traded_ts`` (see the module docstring)."""
    t = np.asarray(traded_ts, dtype=np.int64)
    p = np.asarray(pair_ts, dtype=np.int64)
    po = np.asarray(pair_open, dtype=np.float64)
    pc = np.asarray(pair_close, dtype=np.float64)
    if p.size == 0 or t.size == 0:
        raise DataError("empty conversion series")
    if np.any(np.diff(p) <= 0):
        raise DataError("conversion pair timestamps must be strictly increasing")
    last_le = np.searchsorted(p, t, side="right") - 1  # pair bar starting at or before t
    if np.any(last_le < 0):
        raise DataError("traded bars start before the first conversion-pair bar")
    same = p[last_le] == t
    fx_close = pc[last_le]
    # same bar: its open; missing bar: last_le started before t, its close is known at t
    fx_open = np.where(same, po[last_le], pc[last_le])
    if invert:
        return 1.0 / fx_open, 1.0 / fx_close
    return fx_open.astype(np.float64), fx_close.astype(np.float64)


def conversion_for(
    quote_ccy: str,
    traded_ts: I64,
    cfg: FxConversionConfig,
    pair_bars: dict[str, Any] | None = None,
) -> ConversionArrays:
    """Conversion arrays of a traded symbol quoted in ``quote_ccy``.

    ``pair_bars`` (``ts`` µs, ``open``, ``close``, optional ``window_us``) must come from
    :meth:`DataAccess.conversion_bars` or the holdout access (D-316); traded bars outside
    ``window_us`` are refused.
    """
    n = int(np.asarray(traded_ts).shape[0])
    if quote_ccy == "USD":
        return usd(n)
    if quote_ccy in cfg.pegs:
        rate = 1.0 / cfg.pegs[quote_ccy]
        return ConversionArrays(
            np.full(n, rate), np.full(n, rate), quote_ccy, f"peg:{cfg.pegs[quote_ccy]:g}", True
        )
    rule = cfg.pair_for(quote_ccy)
    if rule is None:
        raise ConfigError(f"no conversion rule for quote currency {quote_ccy}")
    if pair_bars is None:
        raise DataError(f"{quote_ccy}: conversion pair {rule.pair} bars are required")
    if "window_us" in pair_bars:
        lo, hi = (int(x) for x in np.asarray(pair_bars["window_us"]))
        t = np.asarray(traded_ts, dtype=np.int64)
        if t.size and (int(t[0]) < lo or int(t[-1]) > hi):
            raise DataError(
                f"traded bars beyond the conversion window of {rule.pair} (D-316): the window "
                "is the traded segment and may not be extended"
            )
    fo, fc = align_pair(
        np.asarray(traded_ts, dtype=np.int64),
        np.asarray(pair_bars["ts"], dtype=np.int64),
        np.asarray(pair_bars["open"], dtype=np.float64),
        np.asarray(pair_bars["close"], dtype=np.float64),
        rule.invert,
    )
    return ConversionArrays(fo, fc, quote_ccy, rule.pair)

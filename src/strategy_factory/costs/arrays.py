"""Per-bar cost arrays for the engine (F-0.2.1, F-0.2.3, F-0.2.4).

Inputs are NumPy arrays (``ts`` = int64 microseconds UTC, bar start; ``open``; ``close``;
optionally ``spread``). Prices for ``bps`` / ``pip`` amounts are converted with the bar's
**open**, the base price of fills at the open (design section 6).

* ``half_spread[n]`` = full spread / 2 (fixed, or the profile's value for the bar's UTC hour);
* ``slippage_fixed[n]`` and ``slippage_atr_frac``: slippage = fixed + frac x ATR(signal bar);
* ``swap_long_per_notional_day[n]``, ``swap_short_per_notional_day[n]``: credit per unit of
  notional per day at the bar's close (negative = charge). The engine multiplies them by the
  mark-to-market notional ``|qty| x close[j]`` of the rollover bar (D-312);
* ``rollover_mask[n]``: the bar ``[ts, ts + timeframe)`` contains a rollover instant
  (rollover time local, on the profile's rollover weekdays, DST-aware);
* ``triple_mask[n]``: that rollover is the triple day.

``stress`` multiplies half-spread and slippage (fixed and ATR fraction); commission and swap
are unchanged.

**Commission for the engine (T08).** :func:`commission_kernel` has a Numba-compatible
signature (scalars only)::

    commission_kernel(code: int, p0: float, p1: float, p2: float,
                      qty: float, price: float) -> float

    code 0 none                               -> 0
    code 1 percent   p0 = rate                -> rate * |qty| * price
    code 2 per_share p0 = per share, p1 = min, p2 = max (inf = none)
                                               -> clip(p0 * |qty|, p1, p2)
    code 3 per_lot   p0 = lot size, p1 = amount per lot and side
                                               -> |qty| / p0 * p1
    code 4 per_order p0 = amount per order (side)  -> p0          (D-319, appended)

Codes are only ever appended. The result is in ``CostArrays.commission_ccy``; the engine
converts it to USD only when that is the quote currency (``commission_in_quote``, D-328).
T08 moves the kernel into ``engine/`` under ``@njit(cache=True)`` (the engine may not import
``costs``) and passes ``CostArrays.commission_params`` as four scalars.

**Sizing (D-313, D-315).** :func:`size_lots` floors the order to the profile's volume step
(in lots) and reports a skip below the minimum volume; T08 copies the same arithmetic.

**Oracle (D-312).** :func:`round_trip_cost` charges swap on the mark-to-market notional of
every rollover bar held; T08's engine must equal it.
"""

from __future__ import annotations

import datetime as dt
import math
import zoneinfo
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from strategy_factory.core.errors import ConfigError, DataError
from strategy_factory.costs.profile import (
    WEEKDAY_NUMBER,
    Amount,
    CommissionNone,
    CommissionPercent,
    CommissionPerOrder,
    CommissionPerShare,
    CostProfile,
    RolloverRules,
    SpreadBrokerScaled,
    SpreadFixed,
    SpreadFromData,
    SpreadHourly,
    SwapAnnualRate,
    SwapCurrencyPerLot,
    SwapNone,
    SwapPoints,
)

F64 = npt.NDArray[np.float64]
BOOL = npt.NDArray[np.bool_]
I64 = npt.NDArray[np.int64]
Side = Literal["entry", "exit"]
US_PER_HOUR = 3_600_000_000
TF_MICROS: dict[str, int] = {
    "1m": 60_000_000,
    "5m": 300_000_000,
    "15m": 900_000_000,
    "1H": US_PER_HOUR,
    "4H": 4 * US_PER_HOUR,
    "1D": 24 * US_PER_HOUR,
}


def commission_kernel(
    code: int, p0: float, p1: float, p2: float, qty: float, price: float
) -> float:
    """Commission of one order (see the module docstring); Numba-compatible."""
    q = abs(qty)
    if code == 1:
        return p0 * q * price
    if code == 2:
        fee = p0 * q
        if fee < p1:
            fee = p1
        if fee > p2:
            fee = p2
        return fee
    if code == 3:
        return q / p0 * p1
    if code == 4:
        return p0
    return 0.0


def commission_params(profile: CostProfile) -> tuple[int, float, float, float]:
    c = profile.commission
    if isinstance(c, CommissionNone):
        return 0, 0.0, 0.0, 0.0
    if isinstance(c, CommissionPercent):
        return 1, c.rate, 0.0, 0.0
    if isinstance(c, CommissionPerShare):
        cap = math.inf if c.max_per_order is None else c.max_per_order
        return 2, c.per_share, c.min_per_order, cap
    if isinstance(c, CommissionPerOrder):
        return 4, c.amount, 0.0, 0.0
    return 3, c.lot_size, c.per_lot_per_side, 0.0


@dataclass(frozen=True)
class CostArrays:
    half_spread: F64
    slippage_fixed: F64
    slippage_atr_frac: float
    swap_long_per_notional_day: F64
    swap_short_per_notional_day: F64
    rollover_mask: BOOL
    triple_mask: BOOL
    commission_params: tuple[int, float, float, float]
    profile_name: str
    profile_status: str
    stress: float
    commission_ccy: str = "USD"
    quote_ccy: str = "USD"
    contract_size: float = 1.0
    volume_step: float = 1.0
    min_volume: float = 1.0
    volume_step_assumed: bool = True
    to_verify: tuple[str, ...] = ()

    @property
    def placeholder(self) -> bool:
        """True when the costs come from a placeholder profile (results must show a flag)."""
        return self.profile_status == "placeholder"

    @property
    def commission_in_quote(self) -> bool:
        """The commission is in the quote currency (converted to USD by the engine)."""
        return self.commission_ccy != "USD" and self.commission_ccy == self.quote_ccy

    def commission(self, qty: float, price: float, side: Side = "entry") -> float:
        """Commission of one order; both sides use the same model (``side`` is informative)."""
        del side
        return commission_kernel(*self.commission_params, qty, price)


def _amount(a: Amount, ref_price: F64, pip_size: float | None) -> F64:
    if a.unit == "bps":
        return a.value * 1e-4 * ref_price
    if a.unit == "pip":
        if pip_size is None:
            raise ConfigError("pip amount without pip_size")
        return np.full(ref_price.shape, a.value * pip_size)
    return np.full(ref_price.shape, a.value)


def utc_hours(ts_us: I64) -> I64:
    return (ts_us // US_PER_HOUR) % 24


@dataclass(frozen=True)
class HourlySpread:
    full_spread: F64  # 24 values (price units), UTC hour of the bar start
    counts: I64  # data points per hour
    fallback_hours: tuple[int, ...]


def hourly_spread_table(
    ts_us: I64, spread: F64, scale: float, fallback: float | None
) -> HourlySpread:
    """Median ``spread`` per UTC hour x ``scale``; ``fallback`` (price units) for empty hours."""
    hours = utc_hours(ts_us)
    ok = np.isfinite(spread)
    table = np.empty(24)
    counts = np.zeros(24, dtype=np.int64)
    missing: list[int] = []
    for h in range(24):
        vals = spread[(hours == h) & ok]
        counts[h] = vals.size
        if vals.size:
            table[h] = float(np.median(vals)) * scale
        elif fallback is not None:
            table[h] = fallback
            missing.append(h)
        else:
            raise DataError(f"no spread data for UTC hour {h} and no fallback in the profile")
    return HourlySpread(table, counts, tuple(missing))


def broker_scaled_table(
    ts_us: I64, spread: F64, broker_spread: float
) -> tuple[HourlySpread, float]:
    """Hourly median shape scaled so its bar-weighted mean equals ``broker_spread`` (D-523).

    The weights are the bars per UTC hour; hours without data get ``broker_spread``.
    Returns the table and the scale factor.
    """
    raw = hourly_spread_table(ts_us, spread, 1.0, math.nan)
    has = raw.counts > 0
    weighted = float(np.sum(raw.full_spread[has] * raw.counts[has]))
    if not has.any() or weighted <= 0:
        raise DataError("no positive spread data to scale to the broker spread")
    scale = broker_spread * float(raw.counts.sum()) / weighted
    table = np.where(has, raw.full_spread * scale, broker_spread)
    return HourlySpread(table, raw.counts, raw.fallback_hours), scale


def resolve_from_data(
    profile: CostProfile, dev_bars: Mapping[str, npt.NDArray[Any]]
) -> tuple[CostProfile, HourlySpread]:
    """Turn a ``from_data`` or ``broker_scaled`` spread into an ``hourly_profile`` (price units).

    ``dev_bars`` **must be the development segment** (``DataAccess.arrays``): the table is
    a statistic of the data, so it may not see the holdout (D-340).
    """
    sp = profile.spread
    if isinstance(sp, SpreadBrokerScaled):
        return _resolve_broker_scaled(profile, sp, dev_bars)
    if not isinstance(sp, SpreadFromData):
        raise ConfigError(f"profile {profile.name!r} does not use a from_data spread")
    if "spread" not in dev_bars:
        raise DataError(f"profile {profile.name!r} needs a snapshot with a 'spread' column")
    fb = None
    if sp.fallback is not None:
        fb = float(_amount(sp.fallback, np.ones(1), profile.pip_size)[0])
    table = hourly_spread_table(
        np.asarray(dev_bars["ts"], dtype=np.int64),
        np.asarray(dev_bars["spread"], dtype=np.float64),
        sp.scale,
        fb,
    )
    note = (
        f"{profile.source_note} [spread: median per UTC hour x {sp.scale:g} over "
        f"{int(table.counts.sum())} development bars; fallback hours {list(table.fallback_hours)}]"
    ).strip()
    resolved = profile.model_copy(
        update={
            "spread": SpreadHourly(hourly=tuple(float(v) for v in table.full_spread)),
            "source_note": note,
        }
    )
    return resolved, table


def _resolve_broker_scaled(
    profile: CostProfile, sp: SpreadBrokerScaled, dev_bars: Mapping[str, npt.NDArray[Any]]
) -> tuple[CostProfile, HourlySpread]:
    if "spread" not in dev_bars:
        table = HourlySpread(
            np.full(24, sp.broker_spread), np.zeros(24, np.int64), tuple(range(24))
        )
        note = f"{profile.source_note} [spread: broker spread, fixed (no spread data)]".strip()
        fixed = SpreadFixed(fixed=Amount(value=sp.broker_spread))
        return profile.model_copy(update={"spread": fixed, "source_note": note}), table
    table, scale = broker_scaled_table(
        np.asarray(dev_bars["ts"], dtype=np.int64),
        np.asarray(dev_bars["spread"], dtype=np.float64),
        sp.broker_spread,
    )
    note = (
        f"{profile.source_note} [spread: hourly median shape x {scale:.6g} so the mean over "
        f"{int(table.counts.sum())} development bars = broker {sp.broker_spread:g}; "
        f"broker spread in hours {list(table.fallback_hours)}]"
    ).strip()
    hourly = SpreadHourly(hourly=tuple(float(v) for v in table.full_spread))
    return profile.model_copy(update={"spread": hourly, "source_note": note}), table


def rollover_instants(first_us: int, last_us: int, swap: RolloverRules) -> tuple[I64, BOOL]:
    """Rollover instants (µs UTC) covering ``[first, last]`` and whether each is triple."""
    tz = zoneinfo.ZoneInfo(swap.rollover_tz)
    at = dt.time.fromisoformat(swap.rollover_time_local)
    days = {WEEKDAY_NUMBER[d] for d in swap.rollover_weekdays}
    triple = WEEKDAY_NUMBER[swap.triple_weekday]
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
    day = (epoch + dt.timedelta(microseconds=first_us)).date() - dt.timedelta(days=2)
    end = (epoch + dt.timedelta(microseconds=last_us)).date() + dt.timedelta(days=2)
    inst: list[int] = []
    trip: list[bool] = []
    while day <= end:
        if day.isoweekday() in days:
            t = dt.datetime.combine(day, at, tzinfo=tz).astimezone(dt.UTC)
            inst.append((t - epoch) // dt.timedelta(microseconds=1))
            trip.append(day.isoweekday() == triple)
        day += dt.timedelta(days=1)
    return np.array(inst, dtype=np.int64), np.array(trip, dtype=np.bool_)


def build_cost_arrays(
    bars: Mapping[str, npt.NDArray[Any]],
    profile: CostProfile,
    stress: float = 1.0,
    *,
    timeframe: str,
) -> CostArrays:
    """Per-bar cost arrays of ``bars`` under ``profile`` (see the module docstring)."""
    if stress <= 0:
        raise ConfigError("stress multiplier must be positive")
    if timeframe not in TF_MICROS:
        raise ConfigError(f"unknown timeframe {timeframe!r}")
    ccy = profile.commission.currency
    if ccy not in ("USD", profile.quote_ccy):
        raise ConfigError(
            f"profile {profile.name!r}: commission currency {ccy} is neither USD nor the quote "
            f"currency {profile.quote_ccy} (no conversion rule, D-328)"
        )
    ts = np.asarray(bars["ts"], dtype=np.int64)
    ref = np.asarray(bars["open"], dtype=np.float64)
    n = ts.size

    sp = profile.spread
    if isinstance(sp, SpreadFromData | SpreadBrokerScaled):
        raise ConfigError(
            f"profile {profile.name!r}: resolve the {sp.mode} spread on development bars "
            "first (resolve_from_data)"
        )
    if isinstance(sp, SpreadFixed):
        full = _amount(sp.fixed, ref, profile.pip_size)
    else:
        assert isinstance(sp, SpreadHourly)
        per_hour = np.asarray(sp.hourly, dtype=np.float64)[utc_hours(ts)]
        if sp.unit == "bps":
            full = per_hour * 1e-4 * ref
        elif sp.unit == "pip":
            assert profile.pip_size is not None
            full = per_hour * profile.pip_size
        else:
            full = per_hour
    half_spread = full / 2.0 * stress
    slippage_fixed = _amount(profile.slippage.fixed, ref, profile.pip_size) * stress

    sw = profile.swap
    zeros = np.zeros(n)
    mask = np.zeros(n, dtype=np.bool_)
    triple = np.zeros(n, dtype=np.bool_)
    if isinstance(sw, SwapNone) or n == 0:
        long_, short_ = zeros, zeros.copy()
    else:
        if isinstance(sw, SwapAnnualRate):
            long_ = np.full(n, sw.long / sw.day_count)
            short_ = np.full(n, sw.short / sw.day_count)
        elif isinstance(sw, SwapPoints):
            close = np.asarray(bars["close"], dtype=np.float64)
            long_ = sw.long * sw.point_size / close
            short_ = sw.short * sw.point_size / close
        else:
            assert isinstance(sw, SwapCurrencyPerLot)
            lot_value = profile.contract_size * np.asarray(bars["close"], dtype=np.float64)
            long_, short_ = sw.long / lot_value, sw.short / lot_value
        inst, trip = rollover_instants(int(ts[0]), int(ts[-1]), sw)
        idx = np.searchsorted(inst, ts, side="left")
        inside = idx < inst.size
        nxt = np.where(inside, inst[np.minimum(idx, inst.size - 1)], 0)
        mask = inside & (nxt < ts + TF_MICROS[timeframe])
        triple = mask & trip[np.minimum(idx, inst.size - 1)]

    return CostArrays(
        half_spread=half_spread,
        slippage_fixed=slippage_fixed,
        slippage_atr_frac=profile.slippage.atr_fraction * stress,
        swap_long_per_notional_day=long_,
        swap_short_per_notional_day=short_,
        rollover_mask=mask,
        triple_mask=triple,
        commission_params=commission_params(profile),
        profile_name=profile.name,
        profile_status=profile.status,
        stress=stress,
        commission_ccy=profile.commission.currency,
        quote_ccy=profile.quote_ccy,
        contract_size=profile.contract_size,
        volume_step=profile.volume_step,
        min_volume=profile.min_volume,
        volume_step_assumed=profile.volume_step_assumed,
        to_verify=profile.to_verify,
    )


STEP_REL_TOL = 1e-9  # float guard for exact multiples of the volume step (not a decision)


@dataclass(frozen=True)
class SizedOrder:
    lots: float  # floored to the volume step
    qty: float  # instrument units = lots x contract size
    skipped_min_volume: bool  # lots below the minimum volume: not traded (D-313)


def size_lots(
    notional_usd: float,
    entry_price_usd: float,
    contract_size: float,
    volume_step: float,
    min_volume: float,
) -> SizedOrder:
    """D-315: lots = floor((notional / (entry price x contract size)) / step) x step."""
    steps = notional_usd / (entry_price_usd * contract_size) / volume_step
    n = math.floor(steps * (1.0 + STEP_REL_TOL))
    lots = n * volume_step
    min_steps = math.ceil(min_volume / volume_step * (1.0 - STEP_REL_TOL))
    return SizedOrder(lots, lots * contract_size, skipped_min_volume=n < min_steps)


def round_trip_cost(
    arrays: CostArrays,
    entry_idx: int,
    exit_idx: int,
    qty: float,
    direction: int,
    entry_price: float,
    exit_price: float,
    atr_signal_entry: float,
    atr_signal_exit: float,
    *,
    close: F64,
    fx_close: F64 | None = None,
) -> dict[str, float]:
    """Reference cost breakdown of one trade in USD (fills at the opens of entry/exit bars).

    ``qty`` is in instrument units (lots x contract size). Spread and slippage are charged on
    both fills and converted with ``fx_close`` of the fill bar (D-307); commission on both
    orders, converted only when it is in the quote currency. Swap (D-312): on every rollover
    bar held (``entry_idx <= j < exit_idx``) on the mark-to-market notional
    ``|qty| x close[j]``, converted with ``fx_close[j]``, x3 on the triple day. Returns
    positive costs (a swap credit is a negative cost).
    """
    q = abs(qty)
    px = np.asarray(close, dtype=np.float64)
    fx = np.ones(px.shape) if fx_close is None else np.asarray(fx_close, dtype=np.float64)
    fe, fxx = float(fx[entry_idx]), float(fx[exit_idx])
    spread = (arrays.half_spread[entry_idx] * fe + arrays.half_spread[exit_idx] * fxx) * q
    slip = (
        (arrays.slippage_fixed[entry_idx] + arrays.slippage_atr_frac * atr_signal_entry) * fe
        + (arrays.slippage_fixed[exit_idx] + arrays.slippage_atr_frac * atr_signal_exit) * fxx
    ) * q
    ce = arrays.commission(q, entry_price, "entry")
    cx = arrays.commission(q, exit_price, "exit")
    comm = ce * fe + cx * fxx if arrays.commission_in_quote else ce + cx
    held = slice(entry_idx, exit_idx)
    rate = (
        arrays.swap_long_per_notional_day[held]
        if direction > 0
        else arrays.swap_short_per_notional_day[held]
    )
    days = np.where(arrays.triple_mask[held], 3.0, 1.0) * arrays.rollover_mask[held]
    notional = q * px[held] * fx[held]
    swap_credit = float(np.sum(rate * days * notional))
    total = spread + slip + comm - swap_credit
    return {
        "spread": float(spread),
        "slippage": float(slip),
        "commission": float(comm),
        "swap": float(-swap_credit),
        "total": float(total),
    }


def cost_breakdown_shares(costs: Mapping[str, float]) -> dict[str, float]:
    """Each component's share of the total cost (D-525); a swap credit counts as 0 cost."""
    parts = {k: max(float(costs[k]), 0.0) for k in ("spread", "slippage", "commission", "swap")}
    total = sum(parts.values())
    return {k: (v / total if total > 0 else 0.0) for k, v in parts.items()}

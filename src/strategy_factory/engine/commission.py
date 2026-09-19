"""Commission of one order for the engine (T06/T06b signature; codes are only appended).

Same codes as ``costs.arrays.commission_kernel`` (a test pins them equal; the engine may not
import ``costs``)::

    0 none -> 0 · 1 percent p0=rate -> rate*|qty|*price
    2 per_share p0, p1=min, p2=max -> clip(p0*|qty|, p1, p2)
    3 per_lot p0=lot size, p1=amount per lot and side -> |qty|/p0*p1
    4 per_order p0=amount per order (side) -> p0            (D-319)
"""

from __future__ import annotations

from numba import njit


@njit(cache=True)
def commission_kernel(code, p0, p1, p2, qty, price):
    """Commission of one order (codes of ``costs.arrays.commission_kernel``, incl. code 4)."""
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

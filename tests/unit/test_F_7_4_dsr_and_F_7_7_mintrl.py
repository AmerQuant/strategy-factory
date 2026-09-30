"""F-7.4 (the Deflated Sharpe Ratio) and F-7.7 (the Minimum Track Record Length), T16.

Reference values from the papers, verified against their text (docs/tasks/T16_plan.md §6):

* Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio", "A numerical example": annualized
  SR 2.5 over T = 1,250 daily observations (250 a year), N = 100, V[SR] = 0.5 annualized,
  skewness -3, kurtosis 10 -> SR_0 = 0.1132 (per observation), DSR = 0.9004; N = 46 -> 0.9505;
  Normal returns cross 0.95 at N = 88.
* Bailey & Lopez de Prado (2012), "The Sharpe Ratio Efficient Frontier", section 5 and appendix
  A.3: MinTRL = 59.895 months (monthly SR 2/sqrt(12) against 1/sqrt(12), skewness -0.72,
  kurtosis 5.78, 95 %); daily Normal 2.73 years, weekly 2.83, monthly 3.24.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from strategy_factory.stats.dsr import (
    deflated_sharpe,
    expected_max_sharpe,
    min_track_record_length,
    probabilistic_sharpe,
)

YEAR = 250
SR = 2.5 / math.sqrt(YEAR)
V = 0.5 / YEAR


def test_F_7_4_the_papers_numerical_example() -> None:
    r = deflated_sharpe(
        SR, n_obs=1250, skewness=-3, kurtosis=10, n_effective=100, sharpe_variance=V
    )
    assert round(r.sr0, 4) == 0.1132
    assert round(r.probability, 4) == 0.9004


def test_F_7_4_fewer_trials_and_normal_returns_as_the_paper_states() -> None:
    at_46 = deflated_sharpe(SR, 1250, -3, 10, n_effective=46, sharpe_variance=V)
    assert round(at_46.probability, 4) == 0.9505
    normal_88 = deflated_sharpe(SR, 1250, 0, 3, n_effective=88, sharpe_variance=V)
    normal_89 = deflated_sharpe(SR, 1250, 0, 3, n_effective=89, sharpe_variance=V)
    assert normal_88.probability >= 0.95 > normal_89.probability


def test_F_7_4_one_trial_deflates_nothing_and_nan_stays_nan() -> None:
    assert expected_max_sharpe(1, V) == 0.0
    r = deflated_sharpe(SR, 1250, 0, 3, n_effective=1, sharpe_variance=V)
    assert r.probability == pytest.approx(probabilistic_sharpe(SR, 0.0, 1250, 0, 3))
    assert math.isnan(deflated_sharpe(math.nan, 1250, 0, 3, 100, V).probability)
    assert math.isnan(expected_max_sharpe(math.nan, V))


@given(st.floats(2, 1e5), st.floats(1e-6, 1.0))
def test_F_7_4_more_trials_never_lower_the_bar(n: float, var: float) -> None:
    assert expected_max_sharpe(n * 1.5, var) >= expected_max_sharpe(n, var)


def test_F_7_7_the_papers_hedge_fund_example_and_its_psr() -> None:
    r = min_track_record_length(2 / 12**0.5, 1 / 12**0.5, 0.95, -0.72, 5.78)
    assert round(r.min_track_record, 3) == 59.895
    assert round(probabilistic_sharpe(2 / 12**0.5, 1 / 12**0.5, 59.895, -0.72, 5.78), 4) == 0.95


@pytest.mark.parametrize(("per_year", "years"), [(252, 2.73), (52, 2.83), (12, 3.24)])
def test_F_7_7_normal_returns_at_three_frequencies(per_year: int, years: float) -> None:
    r = min_track_record_length(2 / per_year**0.5, 1 / per_year**0.5, 0.95, 0.0, 3.0)
    assert round(r.min_track_record / per_year, 2) == years


def test_F_7_7_no_track_record_is_long_enough_below_the_target() -> None:
    assert min_track_record_length(0.05, 0.05, 0.95, 0, 3).min_track_record == math.inf
    with pytest.raises(ValueError):
        min_track_record_length(0.1, 0.0, 1.0, 0, 3)


@given(st.floats(0.01, 0.5), st.floats(0.001, 0.5))
def test_F_7_7_a_higher_sharpe_needs_a_shorter_record(sharpe: float, step: float) -> None:
    low = min_track_record_length(sharpe, 0.0, 0.95, 0.0, 3.0).min_track_record
    high = min_track_record_length(sharpe + step, 0.0, 0.95, 0.0, 3.0).min_track_record
    assert high <= low

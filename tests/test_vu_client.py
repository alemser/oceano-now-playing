"""Tests for VUClient ballistics helpers."""

import math
from vu_client import _smooth, _update_peak, _PEAK_HOLD


# ── _smooth ────────────────────────────────────────────────────────────────

def test_smooth_attack_moves_toward_target():
    """Level below target should move up using attack tau."""
    result = _smooth(0.0, 1.0, dt=0.050)   # exactly 1× attack tau
    # alpha = 1 - exp(-1) ≈ 0.632
    assert abs(result - (1.0 - math.exp(-1.0))) < 1e-6


def test_smooth_decay_moves_toward_zero():
    """Level above target should decay using decay tau."""
    result = _smooth(1.0, 0.0, dt=0.300)   # exactly 1× decay tau
    # alpha = 1 - exp(-1) ≈ 0.632; result ≈ 1 - 0.632 = 0.368
    assert abs(result - math.exp(-1.0)) < 1e-6


def test_smooth_zero_dt_returns_current():
    """Zero elapsed time should not change the level."""
    assert _smooth(0.5, 1.0, dt=0.0) == 0.5


def test_smooth_large_dt_reaches_target():
    """A very long elapsed time should converge to the target."""
    result = _smooth(0.0, 0.8, dt=100.0)
    assert abs(result - 0.8) < 1e-6


def test_smooth_already_at_target():
    """No movement when current == target."""
    assert _smooth(0.5, 0.5, dt=0.1) == 0.5


# ── _update_peak ──────────────────────────────────────────────────────────

def test_update_peak_new_high_replaces_peak():
    """A value higher than the current peak should become the new peak."""
    peak, peak_at = _update_peak(value=0.9, peak=0.5, peak_at=0.0, now=1.0)
    assert peak == 0.9
    assert peak_at == 1.0


def test_update_peak_hold_does_not_drop_before_timeout():
    """Peak should be held while within the hold window."""
    peak, peak_at = _update_peak(value=0.2, peak=0.9, peak_at=0.0, now=_PEAK_HOLD - 0.1)
    assert peak == 0.9   # still held
    assert peak_at == 0.0


def test_update_peak_drops_after_hold_timeout():
    """Peak should drop to the current value after hold expires."""
    now = _PEAK_HOLD + 0.01
    peak, peak_at = _update_peak(value=0.2, peak=0.9, peak_at=0.0, now=now)
    assert peak == 0.2
    assert peak_at == now


def test_update_peak_equal_value_refreshes_timestamp():
    """Reaching the same peak level should refresh the hold timer."""
    peak, peak_at = _update_peak(value=0.9, peak=0.9, peak_at=0.0, now=5.0)
    assert peak == 0.9
    assert peak_at == 5.0

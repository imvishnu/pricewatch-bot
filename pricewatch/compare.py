"""Pure price-comparison logic. No I/O.

Rules:
- Baseline = median of snapshots in the trailing 90 days.
- Require at least MIN_SNAPSHOTS snapshots before any alert (we accumulate
  our own history; there is no external history source).
- Alert when (baseline - current) / baseline * 100 >= threshold_pct.
- De-dupe: suppress a repeat alert unless the new price is strictly lower
  than the last alerted price.

Median (not min or all-time) is used so inflated MRP listings and one-off
spikes don't distort the baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

MIN_SNAPSHOTS = 10
BASELINE_WINDOW_DAYS = 90


@dataclass(frozen=True)
class Decision:
    should_alert: bool
    baseline: float | None
    drop_pct: float | None
    reason: str


def compute_baseline(prices: list[float]) -> float | None:
    """Median of trailing-window prices; None if below the snapshot minimum.

    Callers pass prices already filtered to the trailing 90 days
    (db.recent_prices does the time filtering in SQL).
    """
    if len(prices) < MIN_SNAPSHOTS:
        return None
    return float(median(prices))


def evaluate(
    current_price: float,
    window_prices: list[float],
    threshold_pct: float,
    last_alerted_price: float | None = None,
) -> Decision:
    """Decide whether to alert for the current price.

    window_prices: snapshots within the trailing 90 days (including today's).
    last_alerted_price: price at which we last alerted this tracking, or None.
    """
    baseline = compute_baseline(window_prices)
    if baseline is None:
        return Decision(False, None, None,
                        f"insufficient history ({len(window_prices)}/{MIN_SNAPSHOTS} snapshots)")
    if baseline <= 0:
        return Decision(False, baseline, None, "non-positive baseline")

    drop_pct = (baseline - current_price) / baseline * 100.0
    if drop_pct < threshold_pct:
        return Decision(False, baseline, drop_pct,
                        f"drop {drop_pct:.1f}% below threshold {threshold_pct:.0f}%")

    # De-dupe: only re-alert on a strictly lower price than the last alert.
    if last_alerted_price is not None and current_price >= last_alerted_price:
        return Decision(False, baseline, drop_pct,
                        f"already alerted at {last_alerted_price:.2f}")

    return Decision(True, baseline, drop_pct, "threshold met")

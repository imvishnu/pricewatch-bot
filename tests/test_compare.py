from pricewatch.compare import MIN_SNAPSHOTS, compute_baseline, evaluate


def test_no_alert_below_min_snapshots():
    prices = [1000.0] * (MIN_SNAPSHOTS - 1)
    d = evaluate(current_price=100.0, window_prices=prices, threshold_pct=50)
    assert not d.should_alert
    assert d.baseline is None
    assert "insufficient history" in d.reason


def test_baseline_is_median():
    # Median resists an inflated-MRP spike
    prices = [1000.0] * 10 + [99999.0]
    assert compute_baseline(prices) == 1000.0


def test_alert_at_threshold():
    prices = [1000.0] * 12
    d = evaluate(current_price=500.0, window_prices=prices, threshold_pct=50)
    assert d.should_alert
    assert d.baseline == 1000.0
    assert d.drop_pct == 50.0


def test_no_alert_below_threshold():
    prices = [1000.0] * 12
    d = evaluate(current_price=600.0, window_prices=prices, threshold_pct=50)
    assert not d.should_alert
    assert d.drop_pct == 40.0


def test_dedupe_same_price_suppressed():
    prices = [1000.0] * 12
    d = evaluate(current_price=400.0, window_prices=prices, threshold_pct=50,
                 last_alerted_price=400.0)
    assert not d.should_alert
    assert "already alerted" in d.reason


def test_dedupe_higher_price_suppressed():
    prices = [1000.0] * 12
    d = evaluate(current_price=450.0, window_prices=prices, threshold_pct=50,
                 last_alerted_price=400.0)
    assert not d.should_alert


def test_dedupe_strictly_lower_price_alerts_again():
    prices = [1000.0] * 12
    d = evaluate(current_price=399.99, window_prices=prices, threshold_pct=50,
                 last_alerted_price=400.0)
    assert d.should_alert


def test_zero_baseline_no_crash():
    prices = [0.0] * 12
    d = evaluate(current_price=0.0, window_prices=prices, threshold_pct=50)
    assert not d.should_alert

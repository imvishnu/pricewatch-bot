from pricewatch.asin import clamp_threshold, extract_asin, is_short_link


def test_dp_url():
    assert extract_asin(
        "https://www.amazon.in/Some-Product-Name/dp/B0ABCD1234/ref=sr_1_1"
    ) == "B0ABCD1234"


def test_dp_url_with_query():
    assert extract_asin("https://www.amazon.in/dp/B0ABCD1234?th=1") == "B0ABCD1234"


def test_gp_product_url():
    assert extract_asin(
        "https://www.amazon.in/gp/product/B09XYZW123"
    ) == "B09XYZW123"


def test_bare_asin():
    assert extract_asin("B0ABCD1234") == "B0ABCD1234"


def test_bare_asin_lowercase():
    assert extract_asin("b0abcd1234") == "B0ABCD1234"


def test_plain_word_not_asin():
    # 10 letters but no digit — not treated as an ASIN
    assert extract_asin("ELECTRONIC") is None


def test_garbage():
    assert extract_asin("https://www.amazon.in/gp/help/customer") is None
    assert extract_asin("hello") is None


def test_short_link_detection():
    assert is_short_link("https://amzn.in/d/1a2B3cD")
    assert is_short_link("amzn.in/d/1a2B3cD")
    assert not is_short_link("https://www.amazon.in/dp/B0ABCD1234")
    # short link itself doesn't contain the ASIN
    assert extract_asin("https://amzn.in/d/1a2B3cD") is None


def test_clamp_threshold():
    assert clamp_threshold(50) == 50
    assert clamp_threshold(0) == 1
    assert clamp_threshold(-5) == 1
    assert clamp_threshold(99) == 95
    assert clamp_threshold(95) == 95
    assert clamp_threshold(1) == 1

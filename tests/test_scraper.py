import pytest

from pricewatch.sources.scraper import ScraperError, parse_price_text, parse_product_page

PRODUCT_HTML = """
<html><head><title>Some Phone : Amazon.in</title></head><body>
<div id="wayfinding-breadcrumbs_feature_div">
  <a href="/electronics">Electronics</a> <a href="/phones">Phones</a>
</div>
<span id="productTitle">  Some Phone 128GB (Black)  </span>
<span class="a-price"><span class="a-offscreen">₹1,29,900.00</span></span>
</body></html>
"""

LEGACY_HTML = """
<html><body>
<span id="productTitle">Old Layout Item</span>
<span id="priceblock_ourprice">₹499</span>
</body></html>
"""

CAPTCHA_HTML = """
<html><head><title>Robot Check</title></head>
<body>Type the characters you see in this image.</body></html>
"""

NO_PRICE_HTML = "<html><body><span id='productTitle'>Unavailable Item</span></body></html>"


def test_parse_price_text():
    assert parse_price_text("₹1,29,900.00") == 129900.0
    assert parse_price_text("₹499") == 499.0
    assert parse_price_text(" 2,345.50 ") == 2345.5


def test_parse_price_text_garbage():
    with pytest.raises(ScraperError):
        parse_price_text("Currently unavailable")


def test_parse_product_page():
    r = parse_product_page(PRODUCT_HTML, "B0ABCD1234")
    assert r.price == 129900.0
    assert r.currency == "INR"
    assert r.title == "Some Phone 128GB (Black)"
    assert r.category == "electronics"
    assert r.asin == "B0ABCD1234"


def test_selector_fallback_legacy_layout():
    r = parse_product_page(LEGACY_HTML, "B0ABCD1234")
    assert r.price == 499.0
    assert r.category == ""


def test_captcha_detected():
    with pytest.raises(ScraperError, match="bot-blocked"):
        parse_product_page(CAPTCHA_HTML, "B0ABCD1234")


def test_missing_price():
    with pytest.raises(ScraperError, match="no price"):
        parse_product_page(NO_PRICE_HTML, "B0ABCD1234")

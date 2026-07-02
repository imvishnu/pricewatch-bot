import pytest

from pricewatch.asin import is_wishlist_link
from pricewatch.sources.scraper import ScraperError, parse_wishlist_page

WISHLIST_HTML = """
<html><head><title>Amazon.in</title></head><body>
<span id="profile-list-name">Diwali shopping</span>
<ul>
  <li data-itemid="I1"><a href="/Some-Item/dp/B0AAAA1111/ref=x">Item 1</a></li>
  <li data-itemid="I2"><a href="/other"></a><a href="/dp/B0BBBB2222?x=1">Item 2</a></li>
  <li data-itemid="I3"><a href="/Some-Item/dp/B0AAAA1111">duplicate</a></li>
</ul>
</body></html>
"""

EMPTY_HTML = "<html><body><h1>Private list</h1><p>nothing here</p></body></html>"

CAPTCHA_HTML = "<html><head><title>Robot Check</title></head><body></body></html>"


def test_is_wishlist_link():
    assert is_wishlist_link("https://www.amazon.in/hz/wishlist/ls/ABC123XYZ?ref=x")
    assert is_wishlist_link("https://www.amazon.in/registry/wishlist/ABC123")
    assert not is_wishlist_link("https://www.amazon.in/dp/B0ABCD1234")
    assert not is_wishlist_link("B0ABCD1234")


def test_parse_wishlist_dedup_and_order():
    name, asins = parse_wishlist_page(WISHLIST_HTML)
    assert name == "Diwali shopping"
    assert asins == ["B0AAAA1111", "B0BBBB2222"]


def test_parse_wishlist_empty_raises():
    with pytest.raises(ScraperError, match="no items"):
        parse_wishlist_page(EMPTY_HTML)


def test_parse_wishlist_captcha_raises():
    with pytest.raises(ScraperError, match="bot-blocked"):
        parse_wishlist_page(CAPTCHA_HTML)

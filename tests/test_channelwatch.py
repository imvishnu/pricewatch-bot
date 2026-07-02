import asyncio

from pricewatch.channelwatch import extract_deal_asin, format_deal


def test_extracts_asin_from_post_text():
    text = ("🔥 iPhone 15 at lowest ever!\n"
            "Buy: https://www.amazon.in/Apple-iPhone-15/dp/B0CHX1W1XY?tag=deal-21\n"
            "Hurry!")
    assert asyncio.run(extract_deal_asin(text)) == "B0CHX1W1XY"


def test_ignores_non_amazon_links():
    text = "Great deal https://flipkart.com/xyz and https://example.com/dp/nothing"
    assert asyncio.run(extract_deal_asin(text)) is None


def test_no_links():
    assert asyncio.run(extract_deal_asin("plain text, no links")) is None
    assert asyncio.run(extract_deal_asin("")) is None


def test_format_deal():
    out = format_deal("Some Phone", "B0CHX1W1XY", 59900.0, "electronics",
                      "https://www.amazon.in/dp/B0CHX1W1XY")
    assert "electronics" in out
    assert "₹59,900.00" in out
    assert "https://www.amazon.in/dp/B0CHX1W1XY" in out

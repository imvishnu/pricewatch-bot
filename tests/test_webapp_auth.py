import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from pricewatch.webapp import validate_init_data

BOT_TOKEN = "12345:TEST_TOKEN"


def make_init_data(user_id=42, auth_date=None, token=BOT_TOKEN):
    pairs = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAE1",
        "user": json.dumps({"id": user_id, "first_name": "T"}),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def test_valid_init_data():
    user = validate_init_data(make_init_data(), BOT_TOKEN)
    assert user["id"] == 42


def test_tampered_hash_rejected():
    data = make_init_data() + "x"
    with pytest.raises(ValueError, match="bad signature"):
        validate_init_data(data, BOT_TOKEN)


def test_wrong_token_rejected():
    data = make_init_data(token="999:OTHER")
    with pytest.raises(ValueError, match="bad signature"):
        validate_init_data(data, BOT_TOKEN)


def test_expired_rejected():
    data = make_init_data(auth_date=int(time.time()) - 100000)
    with pytest.raises(ValueError, match="expired"):
        validate_init_data(data, BOT_TOKEN)


def test_missing_hash_rejected():
    with pytest.raises(ValueError, match="missing hash"):
        validate_init_data("auth_date=1", BOT_TOKEN)

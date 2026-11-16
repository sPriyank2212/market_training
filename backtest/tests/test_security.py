import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import dhan_client as dc
from dhan_client import DhanClient, ForbiddenEndpointError, TokenExpiredError, assert_url_allowed, mask_token

ALLOWED = ["/charts/"]


@pytest.mark.parametrize("url", [
    "https://api.dhan.co/v2/orders",
    "https://api.dhan.co/v2/orders/12345",
    "https://api.dhan.co/v2/super/orders",
    "https://api.dhan.co/v2/charts/orders",
    "https://api.dhan.co/v2/ORDERS",
])
def test_orders_urls_blocked(url):
    with pytest.raises(ForbiddenEndpointError):
        assert_url_allowed(url, ALLOWED)


@pytest.mark.parametrize("url", [
    "https://api.dhan.co/v2/positions",
    "https://api.dhan.co/v2/funds",
    "https://api.dhan.co/v2/marketfeed/ltp",
])
def test_non_allowlisted_blocked(url):
    with pytest.raises(ForbiddenEndpointError):
        assert_url_allowed(url, ALLOWED)


def test_charts_allowed():
    assert_url_allowed("https://api.dhan.co/v2/charts/intraday", ALLOWED)


def test_orders_blocked_before_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network was called")
    monkeypatch.setattr(dc.requests, "post", boom)
    monkeypatch.setenv("DHAN_CLIENT_ID", "x")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "y")
    with pytest.raises(ForbiddenEndpointError):
        DhanClient().post("/orders", {})


def test_token_masked_in_repr(monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "1000000001")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "abcdEFGH1234567890WXYZ")
    r = repr(DhanClient())
    assert "abcdEFGH1234567890WXYZ" not in r
    assert mask_token("abcdEFGH1234567890WXYZ") in r


def test_401_prints_exact_message(monkeypatch, capsys):
    class R:
        status_code = 401
    monkeypatch.setattr(dc.requests, "post", lambda *a, **k: R())
    monkeypatch.setenv("DHAN_CLIENT_ID", "x")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "y")
    with pytest.raises(TokenExpiredError):
        DhanClient().post("/charts/intraday", {})
    assert capsys.readouterr().out.strip() == "Token expired — generate a new one at web.dhan.co → DhanHQ Trading APIs."

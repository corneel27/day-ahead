"""Tibber failures must be actionable and must never save partial price data."""

import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from dao.lib import da_prices
from dao.lib.da_prices import DaPrices

START = dt.datetime(2026, 11, 11, tzinfo=dt.UTC)


@pytest.fixture
def prices():
    config = SimpleNamespace(
        interval="1hour",
        tibber=SimpleNamespace(
            api_token=Mock(resolve=Mock(return_value="test-token")), api_url=None
        ),
    )
    return DaPrices(config, Mock())


@pytest.fixture
def fetch(monkeypatch):
    response = requests.Response()
    response.status_code = 200
    response._content = b""
    response.url = "https://api.tibber.com/v1-beta/gql"
    post = Mock(return_value=response)
    monkeypatch.setattr(da_prices, "post", post)
    return post


def payload(today=None, tomorrow=None, history=None):
    subscription = {
        "priceInfo": {"today": today or [], "tomorrow": tomorrow or []},
        "priceInfoRange": {"nodes": history or []},
    }
    return {"data": {"viewer": {"homes": [{"currentSubscription": subscription}]}}}


def set_payload(fetch, data):
    fetch.return_value._content = json.dumps(data).encode()


def assert_failure(prices, message):
    with pytest.raises(RuntimeError, match=message):
        prices.get_prices("tibber", START, START + dt.timedelta(days=1))
    prices.db_da.savedata.assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_http_failure_is_reported_before_json_parsing(prices, fetch, status):
    fetch.return_value.status_code = status
    fetch.return_value._content = b"<html>upstream error</html>"
    assert_failure(prices, f"Tibber price request failed \\(HTTP {status}\\)")


@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError])
def test_transport_failure(prices, fetch, exception):
    fetch.side_effect = exception("request failed")
    assert_failure(prices, f"Tibber price request failed \\({exception.__name__}\\)")


@pytest.mark.parametrize("body", [b"", b" \n\t"])
def test_empty_response(prices, fetch, body):
    fetch.return_value._content = body
    assert_failure(prices, "Tibber returned an empty price response")


@pytest.mark.parametrize("body", [b"<html>unavailable</html>", b'{"data":', b"not JSON"])
def test_invalid_json(prices, fetch, body):
    fetch.return_value._content = body
    assert_failure(prices, "Tibber returned invalid JSON for prices")


@pytest.mark.parametrize("data", [None, [], "unexpected", 42])
def test_invalid_json_root(prices, fetch, data):
    set_payload(fetch, data)
    assert_failure(prices, "Tibber returned an invalid price response")


@pytest.mark.parametrize("with_data", [False, True])
def test_graphql_errors(prices, fetch, with_data):
    data = payload() if with_data else {"data": None}
    data["errors"] = [{"message": "subscription error"}]
    set_payload(fetch, data)
    assert_failure(prices, "Tibber returned GraphQL errors fetching prices")


@pytest.mark.parametrize("data", [
    {}, {"data": None}, {"data": {"viewer": {"homes": []}}},
    {"data": {"viewer": {"homes": [{"currentSubscription": None}]}}},
])
def test_missing_subscription_or_price_data(prices, fetch, data):
    set_payload(fetch, data)
    assert_failure(prices, "Tibber price response is missing subscription or price data")


@pytest.mark.parametrize("nodes", [None, {}, "unexpected"])
def test_invalid_price_list(prices, fetch, nodes):
    data = payload()
    data["data"]["viewer"]["homes"][0]["currentSubscription"]["priceInfo"]["today"] = nodes
    set_payload(fetch, data)
    assert_failure(prices, "Tibber price response contains invalid price lists")


def test_no_prices(prices, fetch):
    set_payload(fetch, payload())
    assert_failure(prices, "Tibber returned no prices")


@pytest.mark.parametrize("node", [
    None, {}, {"startsAt": "invalid", "energy": 0.1},
    {"startsAt": "2026-11-11T01:00:00.000+00:00", "energy": None},
    {"startsAt": "2026-11-11T01:00:00.000+00:00", "energy": "NaN"},
])
def test_invalid_entry_does_not_save_partial_prices(prices, fetch, node):
    good = {"startsAt": "2026-11-11T00:00:00.000+00:00", "energy": 0.1}
    set_payload(fetch, payload(today=[good, node]))
    assert_failure(prices, "Tibber price response contains an invalid price entry")


@pytest.mark.parametrize("interval, resolution", [("1hour", "HOURLY"), ("15min", "QUARTER_HOURLY")])
def test_valid_prices_are_saved(prices, fetch, interval, resolution):
    prices.interval = interval
    today = {"startsAt": "2026-11-11T00:00:00.000+00:00", "energy": -0.1}
    history = {"startsAt": "2026-11-10T23:00:00.000+00:00", "energy": 0.2}
    set_payload(fetch, payload(today=[today], history=[history]))
    prices.get_prices("tibber", START, START + dt.timedelta(days=1))
    saved = prices.db_da.savedata.call_args.args[0]
    assert saved.to_dict("records") == [
        {"time": int(START.timestamp()), "code": "da", "value": -0.1},
        {"time": int(START.timestamp()) - 3600, "code": "da", "value": 0.2},
    ]
    fetch.assert_called_once()
    assert fetch.call_args.kwargs["timeout"] == 30
    assert f"resolution: {resolution}" in json.loads(fetch.call_args.kwargs["data"])["query"]

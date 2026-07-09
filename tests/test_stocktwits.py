from src.data_sources import stocktwits


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_trending_symbols_filters_out_crypto_forex(monkeypatch):
    payload = {
        "symbols": [
            {"symbol": "AAPL"},
            {"symbol": "XRP.X"},
            {"symbol": "BTC.X"},
            {"symbol": "GME"},
        ]
    }
    monkeypatch.setattr(
        stocktwits.requests, "get", lambda *a, **k: _FakeResponse(payload)
    )
    result = stocktwits.fetch_trending_symbols()
    assert result == {"AAPL", "GME"}
    assert "XRP.X" not in result
    assert "BTC.X" not in result

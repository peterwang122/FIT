import httpx

from app.tasks import collector


class _FakeRedis:
    def __init__(self):
        self.owner = None
        self.deleted = []

    def set(self, key, owner, nx=False, ex=None):
        self.owner = owner
        return True

    def get(self, key):
        return self.owner

    def delete(self, key):
        self.deleted.append(key)


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.request = httpx.Request("POST", "http://test.local/collect")

    @property
    def is_error(self):
        return self.status_code >= 400

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, endpoint, json):
        self.calls.append((endpoint, json))
        return self.responses.pop(0)


def test_daily_collection_retries_transient_upstream_5xx(monkeypatch):
    fake_redis = _FakeRedis()
    fake_client = _FakeClient(
        [
            _FakeResponse(500, text='{"status":"FAILED"}'),
            _FakeResponse(200, {"status": "SUCCESS", "result": "ok"}),
        ]
    )
    sleeps = []

    monkeypatch.setattr(collector, "redis_client", fake_redis)
    monkeypatch.setattr(collector.httpx, "Client", lambda **_kwargs: fake_client)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(collector.settings, "stock_temp_daily_task_max_retries", 3)
    monkeypatch.setattr(collector.settings, "collector_task_retry_backoff_seconds", 1)

    result = collector.run_daily_collection_request(
        collector_key="index_qvix_daily",
        endpoint="/collect-index-qvix-daily",
        request_id="request-1",
    )

    assert result["status"] == "ok"
    assert result["upstream_status"] == "SUCCESS"
    assert fake_client.calls == [
        ("/collect-index-qvix-daily", {}),
        ("/collect-index-qvix-daily", {}),
    ]
    assert sleeps == [1]
    assert fake_redis.deleted == ["daily-temp:lock:index_qvix_daily"]


def test_forex_collection_posts_single_symbol_and_retries_5xx(monkeypatch):
    fake_redis = _FakeRedis()
    fake_client = _FakeClient(
        [
            _FakeResponse(502, text='{"status":"FAILED"}'),
            _FakeResponse(
                200,
                {
                    "status": "SUCCESS",
                    "symbol_code": "USDCNH",
                    "rows_fetched": 5,
                    "upserted_rows": 5,
                },
            ),
        ]
    )
    sleeps = []

    monkeypatch.setattr(collector, "redis_client", fake_redis)
    monkeypatch.setattr(collector.httpx, "Client", lambda **_kwargs: fake_client)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(collector.settings, "stock_temp_task_max_retries", 3)
    monkeypatch.setattr(collector.settings, "collector_task_retry_backoff_seconds", 1)

    result = collector.run_forex_collection_request(symbol_code="usdcnh", request_id="request-1")

    assert result["status"] == "ok"
    assert result["symbol_code"] == "USDCNH"
    assert result["upstream_status"] == "SUCCESS"
    assert fake_client.calls == [
        ("/collect-forex", {"symbol_code": "USDCNH"}),
        ("/collect-forex", {"symbol_code": "USDCNH"}),
    ]
    assert sleeps == [1]
    assert fake_redis.deleted == ["forex-temp:lock:USDCNH"]

import httpx

from app.tasks import collector


class _FakeRedis:
    def __init__(self):
        self.owner = None
        self.deleted = []
        self.expire_seconds = None

    def set(self, key, owner, nx=False, ex=None):
        self.owner = owner
        self.expire_seconds = ex
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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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


def test_daily_collection_retries_after_stock_temp_disconnect(monkeypatch):
    fake_redis = _FakeRedis()
    fake_client = _FakeClient(
        [
            httpx.RemoteProtocolError(
                "server disconnected",
                request=httpx.Request("POST", "http://test.local/collect"),
            ),
            _FakeResponse(200, {"status": "SUCCESS", "result": "resumed"}),
        ]
    )
    sleeps = []

    monkeypatch.setattr(collector, "redis_client", fake_redis)
    monkeypatch.setattr(collector.httpx, "Client", lambda **_kwargs: fake_client)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(collector.settings, "stock_temp_daily_task_max_retries", 3)
    monkeypatch.setattr(collector.settings, "collector_task_retry_backoff_seconds", 2)

    result = collector.run_daily_collection_request(
        collector_key="stock_exchange_official_daily",
        endpoint="/collect-stock-exchange-official-daily",
        request_id="request-2",
        payload={"target_date": "2026-07-13"},
    )

    assert result["status"] == "ok"
    assert result["upstream_response"]["result"] == "resumed"
    assert fake_client.calls == [
        ("/collect-stock-exchange-official-daily", {"target_date": "2026-07-13"}),
        ("/collect-stock-exchange-official-daily", {"target_date": "2026-07-13"}),
    ]
    assert sleeps == [2]
    assert fake_redis.deleted == ["daily-temp:lock:stock_exchange_official_daily"]


def test_douyin_daily_retries_transient_authentication_failure(monkeypatch):
    fake_redis = _FakeRedis()
    fake_client = _FakeClient(
        [
            _FakeResponse(
                500,
                text='{"status":"FAILED","error":"抖音登录已失效，请运行 python run.py douyin login"}',
            ),
            _FakeResponse(
                200,
                {
                    "status": "SUCCESS",
                    "result": {"status": "NO_UPDATE"},
                },
            ),
        ]
    )
    sleeps = []

    monkeypatch.setattr(collector, "redis_client", fake_redis)
    monkeypatch.setattr(collector.httpx, "Client", lambda **_kwargs: fake_client)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(collector.settings, "stock_temp_daily_task_max_retries", 3)
    monkeypatch.setattr(collector.settings, "collector_task_retry_backoff_seconds", 2)

    result = collector.run_daily_collection_request(
        collector_key="douyin_coze_emotion_daily",
        endpoint="/collect-douyin-coze-emotion-daily",
        payload={"target_date": "2026-07-17"},
    )

    assert result["status"] == "ok"
    assert fake_client.calls == [
        ("/collect-douyin-coze-emotion-daily", {"target_date": "2026-07-17"}),
        ("/collect-douyin-coze-emotion-daily", {"target_date": "2026-07-17"}),
    ]
    assert sleeps == [2]
    assert fake_redis.deleted == ["daily-temp:lock:douyin_coze_emotion_daily"]


def test_douyin_daily_does_not_retry_non_authentication_failure(monkeypatch):
    fake_redis = _FakeRedis()
    fake_client = _FakeClient(
        [
            _FakeResponse(
                500,
                text='{"status":"FAILED","error":"等待 Coze 视频文案超时"}',
            ),
        ]
    )

    monkeypatch.setattr(collector, "redis_client", fake_redis)
    monkeypatch.setattr(collector.httpx, "Client", lambda **_kwargs: fake_client)
    monkeypatch.setattr(collector.settings, "stock_temp_daily_task_max_retries", 3)

    try:
        collector.run_daily_collection_request(
            collector_key="douyin_coze_emotion_daily",
            endpoint="/collect-douyin-coze-emotion-daily",
            payload={"target_date": "2026-07-17"},
        )
    except httpx.HTTPStatusError as exc:
        assert "等待 Coze 视频文案超时" in str(exc)
    else:
        raise AssertionError("expected non-authentication failure to be raised")

    assert fake_client.calls == [
        ("/collect-douyin-coze-emotion-daily", {"target_date": "2026-07-17"}),
    ]
    assert fake_redis.deleted == ["daily-temp:lock:douyin_coze_emotion_daily"]


def test_option_minute_daily_uses_session_timeout(monkeypatch):
    fake_redis = _FakeRedis()
    fake_client = _FakeClient(
        [_FakeResponse(200, {"status": "SUCCESS", "result": {"status": "SUCCESS"}})]
    )
    client_kwargs = []

    monkeypatch.setattr(collector, "redis_client", fake_redis)
    monkeypatch.setattr(
        collector.httpx,
        "Client",
        lambda **kwargs: client_kwargs.append(kwargs) or fake_client,
    )
    monkeypatch.setattr(collector.settings, "option_minute_daily_service_timeout_seconds", 23400)
    monkeypatch.setattr(collector.settings, "collector_dedupe_lock_ttl_seconds", 120)

    result = collector.run_daily_collection_request(
        collector_key="option_minute_daily",
        endpoint="/collect-option-minute-daily",
        payload={"target_date": "2026-07-13"},
    )

    assert result["status"] == "ok"
    assert client_kwargs[0]["timeout"] == 23400
    assert fake_redis.expire_seconds == 23700


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

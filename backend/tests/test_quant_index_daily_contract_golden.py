import json
from datetime import date
from pathlib import Path

import httpx

from app.services.task_service import COLLECTION_TASK_DEFINITIONS
from app.tasks import collector


GOLDEN_PATH = Path(__file__).parent / "golden" / "quant_index_daily_contract_v1.json"


def _load_golden(path=GOLDEN_PATH):
    return json.loads(path.read_text(encoding="utf-8"))


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 7, 31)


class _FakeRedis:
    def __init__(self):
        self.owner = None
        self.deleted = []

    def set(self, _key, owner, nx=False, ex=None):
        assert nx is True
        assert ex is not None
        self.owner = owner
        return True

    def get(self, _key):
        return self.owner

    def delete(self, key):
        self.deleted.append(key)


class _FakeResponse:
    status_code = 200
    is_error = False

    def __init__(self, payload):
        self._payload = payload
        self.request = httpx.Request("POST", "http://test.local/collect-quant-index-daily")

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, expected_endpoint, expected_payload, response_payload):
        self.expected_endpoint = expected_endpoint
        self.expected_payload = expected_payload
        self.response = _FakeResponse(response_payload)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, endpoint, json):
        self.calls.append((endpoint, json))
        assert endpoint == self.expected_endpoint
        assert json == self.expected_payload
        return self.response


def test_fit_consumes_quant_index_daily_golden_contract(monkeypatch):
    golden = _load_golden()
    request = golden["request"]
    definition = COLLECTION_TASK_DEFINITIONS[request["collector_key"]]
    assert definition["endpoint"] == request["endpoint"]

    fake_redis = _FakeRedis()
    fake_client = _FakeClient(
        expected_endpoint=request["endpoint"],
        expected_payload=request["payload"],
        response_payload=golden["provider_response"],
    )
    monkeypatch.setattr(collector, "date", _FrozenDate)
    monkeypatch.setattr(collector, "redis_client", fake_redis)
    monkeypatch.setattr(collector.httpx, "Client", lambda **_kwargs: fake_client)

    result = collector.run_daily_collection_request(**request, request_id="golden-contract-v1")

    assert result == golden["consumer_response"]
    assert fake_client.calls == [(request["endpoint"], request["payload"])]
    assert fake_redis.deleted == ["daily-temp:lock:quant_index_daily"]


def test_sibling_akshare_golden_sample_does_not_drift():
    sibling_path = (
        Path(__file__).resolve().parents[3]
        / "akshareProkect"
        / "tests"
        / "golden"
        / GOLDEN_PATH.name
    )
    if sibling_path.exists():
        assert _load_golden(sibling_path) == _load_golden()


from unittest.mock import Mock

from src import etherscan_ingestion


def test_fetch_page_retries_after_rate_limit(monkeypatch):
    # 1. Chuẩn bị hai phản hồi API giả
    rate_limited = Mock(status_code=429)
    success = Mock(status_code=200)

    expected_records = [
        {"blockNumber": "1001", "hash": "0xexample"}
    ]

    success.json.return_value = {
        "status": "1",
        "message": "OK",
        "result": expected_records,
    }

    responses = iter([rate_limited, success])
    calls = []
    sleep_delays = []

    def fake_get(url, params, timeout):
        calls.append((url, params.copy(), timeout))
        return next(responses)

    monkeypatch.setattr(
        etherscan_ingestion.requests, "get", fake_get
    )
    monkeypatch.setattr(
        etherscan_ingestion.time, "sleep", sleep_delays.append
    )

    # 2. Chạy hàm thật trong project
    response, records = etherscan_ingestion.fetch_page(
        api_key="fake-test-key",
        address="0x" + "a" * 40,
        action="tokentx",
        page=1,
        offset=100,
        start_block=1001,
    )

    # 3. Kiểm tra kết quả
    assert response is success
    assert records == expected_records
    assert len(calls) == 2
    assert calls[0][1]["startblock"] == 1001
    assert calls[1][1]["startblock"] == 1001
    assert calls[0][1]["page"] == calls[1][1]["page"] == 1
    assert sleep_delays == [
        etherscan_ingestion.BASE_DELAY_SECONDS
    ]

    # file này đang đóng giả etherscan để thử phản ứn của chương trình khi gặp lỗi


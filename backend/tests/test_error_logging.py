import asyncio
from types import SimpleNamespace

import main


def test_unexpected_error_never_logs_exception_payload(caplog):
    request = SimpleNamespace(state=SimpleNamespace(request_id="review-test"))
    secret = "sensitive-document-value"
    response = asyncio.run(main.unexpected_error(request, RuntimeError(secret)))
    assert response.status_code == 500
    assert secret not in caplog.text
    assert secret.encode() not in response.body
    assert "review-test" in caplog.text
    assert "RuntimeError" in caplog.text

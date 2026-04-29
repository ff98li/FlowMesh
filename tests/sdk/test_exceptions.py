"""Status-code mapping tests for SDK exceptions."""

import httpx
import pytest
from flowmesh._base_client import _raise_for_status
from flowmesh.exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
    ValidationError,
)


class TestStatusCodeMapping:
    @staticmethod
    def _mock_response(status_code: int, body: str = "error") -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            text=body,
            request=httpx.Request("GET", "http://test/api/v1/test"),
        )

    def test_401_raises_authentication_error(self) -> None:
        resp = self._mock_response(401)
        with pytest.raises(AuthenticationError) as exc_info:
            _raise_for_status(resp, "GET")
        assert exc_info.value.status_code == 401

    def test_403_raises_authentication_error(self) -> None:
        resp = self._mock_response(403)
        with pytest.raises(AuthenticationError):
            _raise_for_status(resp, "GET")

    def test_404_raises_not_found_error(self) -> None:
        resp = self._mock_response(404)
        with pytest.raises(NotFoundError) as exc_info:
            _raise_for_status(resp, "GET")
        assert exc_info.value.status_code == 404

    def test_400_raises_validation_error(self) -> None:
        resp = self._mock_response(400)
        with pytest.raises(ValidationError):
            _raise_for_status(resp, "GET")

    def test_422_raises_validation_error(self) -> None:
        resp = self._mock_response(422)
        with pytest.raises(ValidationError):
            _raise_for_status(resp, "GET")

    def test_500_raises_api_error(self) -> None:
        resp = self._mock_response(500)
        with pytest.raises(APIError) as exc_info:
            _raise_for_status(resp, "GET")
        assert exc_info.value.status_code == 500

    def test_200_does_not_raise(self) -> None:
        resp = self._mock_response(200, "ok")
        _raise_for_status(resp, "GET")  # should not raise

    def test_api_error_attributes(self) -> None:
        resp = self._mock_response(502, '{"detail": "bad gateway"}')
        with pytest.raises(APIError) as exc_info:
            _raise_for_status(resp, "POST")
        err = exc_info.value
        assert err.status_code == 502
        assert err.method == "POST"
        assert "test" in err.url

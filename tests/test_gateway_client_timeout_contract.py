"""Regression tests for the H.E.R.B.I.E. worker client timeout and response validation."""
import io
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from agents.herbie_gateway_client import HerbieGatewayClient, GatewayError


class _Response:
    def __init__(self, payload):
        self.data = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.data.read(size)


class GatewayClientContractTests(unittest.TestCase):
    def setUp(self):
        self.client = HerbieGatewayClient("http://127.0.0.1:8787", "x" * 48, "test-model")

    def test_default_timeout_exceeds_gateway_upstream_budget(self):
        self.assertGreater(self.client.timeout, 45)

    def test_blank_inference_is_not_success(self):
        for reply in ("", " ", "\t\n", "\u2003"):
            with self.subTest(reply=repr(reply)):
                request_id = str(uuid4())
                payload = {"schema_version": 1, "request_id": request_id,
                           "model": "test-model", "reply": reply}

                class _Opener:
                    def open(self, request, timeout):
                        return _Response(payload)

                with patch("agents.herbie_gateway_client.urllib.request.build_opener",
                           return_value=_Opener()):
                    with self.assertRaises(GatewayError):
                        self.client.infer("coding", "test prompt", request_id)


if __name__ == "__main__":
    unittest.main()

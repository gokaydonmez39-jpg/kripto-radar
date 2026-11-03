"""No-network, fail-first tests for bounded provider READ recovery."""
import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import private_sheet_writer as mod


def client():
    api = mod.SheetApi.__new__(mod.SheetApi)
    api.base = "https://sheets.googleapis.com/v4/spreadsheets/SYNTHETIC"
    api.token = "SYNTHETIC_TOKEN"
    api.sheet_ids = {}
    return api


def response():
    return io.BytesIO(b'{"verified": true}')


class ReadOnlyRetryTests(unittest.TestCase):
    def test_get_transient_http503_then_success(self):
        err = HTTPError("synthetic", 503, "unavailable", None, None)
        with patch.object(mod, "urlopen", side_effect=[err, response()]) as req:
            with patch.object(mod, "time", create=True) as timer:
                result = client().request("/values/synthetic")
        self.assertTrue(result["verified"])
        self.assertEqual(req.call_count, 2)
        self.assertLessEqual(timer.sleep.call_count, 1)

    def test_get_transient_urlerror_then_success(self):
        with patch.object(mod, "urlopen", side_effect=[URLError("offline"), response()]) as req:
            with patch.object(mod, "time", create=True):
                self.assertTrue(client().request("/values/synthetic")["verified"])
        self.assertEqual(req.call_count, 2)

    def test_get_403_not_retried(self):
        with patch.object(mod, "urlopen", side_effect=HTTPError(
                "synthetic", 403, "permission denied", None, None)) as req:
            with self.assertRaises(mod.HandoffBlocked):
                client().request("/values/synthetic")
        self.assertEqual(req.call_count, 1)

    def test_post_timeout_never_retried(self):
        with patch.object(mod, "urlopen", side_effect=URLError("ambiguous write")) as req:
            with self.assertRaises(mod.HandoffBlocked):
                client().request(":batchUpdate", method="POST", body={"requests": []})
        self.assertEqual(req.call_count, 1)

    def test_get_two_failures_stop_and_do_not_leak_response(self):
        with patch.object(mod, "urlopen", side_effect=[URLError("private-row-payload"),
                   URLError("private-row-payload")]) as req:
            with patch.object(mod, "time", create=True):
                with self.assertRaises(mod.HandoffBlocked) as caught:
                    client().request("/values/synthetic")
        self.assertEqual(req.call_count, 2)
        self.assertNotIn("private-row-payload", str(caught.exception))

    def test_post_http_503_still_never_retry(self):
        with patch.object(mod, "urlopen", side_effect=HTTPError(
                "synthetic", 503, "ambiguous", None, None)) as req:
            with self.assertRaises(mod.HandoffBlocked):
                client().request(":batchUpdate", method="POST", body={"requests": []})
        self.assertEqual(req.call_count, 1)


if __name__ == "__main__":
    unittest.main()

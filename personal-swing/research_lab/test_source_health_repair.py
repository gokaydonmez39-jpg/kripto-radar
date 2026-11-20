"""Offline adversarial tests for GitHub read-only autonomous bounded repair."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import source_health_live as live


class BoundedReadRepairTest(unittest.TestCase):
    @staticmethod
    def error(code):
        return HTTPError("https://api.github.com/synthetic", code, "synthetic", {}, None)

    def test_normal_get_does_not_repair(self):
        reader=live.GitHubReader("test-token-not-real")
        with patch.object(live,"urlopen",return_value=io.BytesIO(b'{"ok": true}')) as http, \
             patch.object(live.time,"sleep") as sleep:
            self.assertEqual(reader.json("/actions/runs/101"),{"ok":True})
            self.assertEqual(http.call_count,1)
            sleep.assert_not_called()
        self.assertEqual((reader.transient_failures,reader.recovered_reads),(0,0))

    def test_transient_http_is_recovered_with_one_get(self):
        for code in (429,500,502,503,504):
            with self.subTest(code=code):
                reader=live.GitHubReader("test-token-not-real")
                with patch.object(live,"urlopen",side_effect=[
                        self.error(code),io.BytesIO(b'{"ok": true}')]) as http, \
                     patch.object(live.time,"sleep") as sleep:
                    self.assertEqual(reader.json("/actions/runs/101"),{"ok":True})
                    self.assertEqual(http.call_count,2)
                    sleep.assert_called_once_with(1)
                    for call in http.call_args_list:
                        self.assertEqual(call.args[0].get_method(),"GET")
                        self.assertIsNone(call.args[0].data)
                self.assertEqual((reader.transient_failures,reader.recovered_reads),(1,1))

    def test_transport_fault_is_recovered(self):
        for fault in (URLError("synthetic"),TimeoutError("synthetic")):
            with self.subTest(fault=type(fault).__name__):
                reader=live.GitHubReader("test-token-not-real")
                with patch.object(live,"urlopen",side_effect=[
                        fault,io.BytesIO(b'ok')]) as http, \
                     patch.object(live.time,"sleep") as sleep:
                    self.assertEqual(reader.text("/actions/jobs/11/logs"),"ok")
                    self.assertEqual(http.call_count,2)
                    sleep.assert_called_once_with(1)
                self.assertEqual(reader.recovered_reads,1)

    def test_auth_and_missing_source_never_retried(self):
        for code in (400,401,403,404,409,422):
            with self.subTest(code=code):
                reader=live.GitHubReader("test-token-not-real")
                with patch.object(live,"urlopen",side_effect=[
                        self.error(code),io.BytesIO(b'{"ok": true}')]) as http, \
                     patch.object(live.time,"sleep") as sleep:
                    with self.assertRaisesRegex(live.NoProof,"NONRETRYABLE_GITHUB_READ"):
                        reader._get("/actions/runs/101")
                    self.assertEqual(http.call_count,1)
                    sleep.assert_not_called()
                self.assertEqual((reader.transient_failures,reader.recovered_reads),(0,0))

    def test_three_attempts_exhausts_fail_closed(self):
        reader=live.GitHubReader("test-token-not-real")
        with patch.object(live,"urlopen",side_effect=[
                self.error(429),self.error(503),TimeoutError("synthetic")]) as http, \
             patch.object(live.time,"sleep") as sleep:
            with self.assertRaisesRegex(live.NoProof,"GITHUB_READ_RETRY_EXHAUSTED"):
                reader._get("/actions/runs/101")
            self.assertEqual(http.call_count,3)
            self.assertEqual([call.args[0] for call in sleep.call_args_list],[1,2])
            for call in http.call_args_list:
                self.assertEqual(call.args[0].get_method(),"GET")
                self.assertIsNone(call.args[0].data)
        self.assertEqual((reader.transient_failures,reader.recovered_reads),(3,0))

    def test_two_failures_then_recovery(self):
        reader=live.GitHubReader("test-token-not-real")
        with patch.object(live,"urlopen",side_effect=[
                self.error(502),URLError("synthetic"),io.BytesIO(b'ok')]) as http, \
             patch.object(live.time,"sleep") as sleep:
            self.assertEqual(reader.text("/actions/jobs/9/logs"),"ok")
            self.assertEqual(http.call_count,3)
            self.assertEqual([c.args[0] for c in sleep.call_args_list],[1,2])
        self.assertEqual((reader.transient_failures,reader.recovered_reads),(2,1))

    def test_invalid_path_is_never_fetched(self):
        reader=live.GitHubReader("test-token-not-real")
        for path in ("/repos/other","/actions/../secret","/actions/"+("x"*245)):
            with self.subTest(path=path[:30]), \
                 patch.object(live,"urlopen") as http:
                with self.assertRaises(live.NoProof):reader._get(path)
                http.assert_not_called()

    def test_oversize_response_is_not_repaired(self):
        reader=live.GitHubReader("test-token-not-real")
        with patch.object(live,"urlopen",return_value=io.BytesIO(b"x"*2_000_001)) as http, \
             patch.object(live.time,"sleep") as sleep:
            with self.assertRaises(live.NoProof):reader._get("/actions/runs/101")
            self.assertEqual(http.call_count,1)
            sleep.assert_not_called()

    def test_malformed_success_body_is_not_repaired(self):
        reader=live.GitHubReader("test-token-not-real")
        with patch.object(live,"urlopen",return_value=io.BytesIO(b"NOT_JSON")) as http, \
             patch.object(live.time,"sleep") as sleep:
            with self.assertRaises(json.JSONDecodeError):reader.json("/actions/runs/101")
            self.assertEqual(http.call_count,1)
            sleep.assert_not_called()

    def test_repair_has_no_write_or_dispatch_capability(self):
        self.assertEqual(live.GitHubReader.MAX_READ_ATTEMPTS,3)
        self.assertFalse(any(hasattr(live.GitHubReader,k) for k in (
            "post","put","patch","delete","dispatch","send","merge","trade")))


if __name__ == "__main__":
    unittest.main()

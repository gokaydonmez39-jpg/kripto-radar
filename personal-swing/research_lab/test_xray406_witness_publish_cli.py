from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

import test_xray406_witness_acceptance as fixtures
from xray406_witness_github import TARGET
from xray406_witness_publish import Indeterminate
from xray406_witness_publish_cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        f = fixtures.WitnessAcceptanceTests("test_positive_exact_check_and_timely_readback")
        self.addCleanup(f.doCleanups)
        f.setUp()
        self.f = f
        self.argv = ["--git-dir", str(f.root), "--base", f.base, "--candidate", f.head,
                     "--run-id", "11", "--attempt", "1", "--cutoff-utc", f.cutoff.isoformat()]

    def test_dry_run_is_default_and_never_applies(self):
        f = self.f
        with patch("xray406_witness_publish_cli.receipt_pair", return_value=(None, None)), \
             patch("xray406_witness_publish_cli.GitHubIsolatedTransport") as transport, \
             patch("xray406_witness_publish_cli.plan") as plan, \
             patch("xray406_witness_publish_cli.publish") as publish, redirect_stdout(StringIO()) as out:
            plan.return_value.latest_observed_at = f.cutoff
            self.assertEqual(main(self.argv, clock=lambda: f.generated), 0)
            self.assertIn("ISOLATED_DRY_RUN_PASS", out.getvalue())
            publish.assert_not_called()
            self.assertEqual(transport.return_value.head.call_count, 2)

    def test_dry_run_transport_rejects_graphql(self):
        f = self.f
        def force_write(run_id, attempt, candidate, call):
            return call("graphql", {})
        with patch("xray406_witness_publish_cli.receipt_pair", side_effect=force_write), \
             redirect_stderr(StringIO()):
            self.assertEqual(main(self.argv, call=lambda *a: self.fail("mutation"), clock=lambda: f.generated), 2)

    def test_apply_cannot_target_main(self):
        f = self.f
        with patch("xray406_witness_publish_cli.receipt_pair", return_value=(None, None)), \
             patch("xray406_witness_publish_cli.GitHubIsolatedTransport") as transport, \
             patch("xray406_witness_publish_cli.publish") as publish, redirect_stderr(StringIO()):
            def wrong_target(*args):
                call = transport.call_args.args[1]
                call("graphql", {"variables": {"input": {"refUpdates": [
                    {"name": "refs/heads/main", "beforeOid": f.base,
                     "afterOid": f.head, "force": False}]}}})
            publish.side_effect = wrong_target
            self.assertEqual(main(self.argv + ["--apply-isolated"],
                                  call=lambda *a: self.fail("mutation")), 2)

    def test_apply_does_not_retry_unknown(self):
        with patch("xray406_witness_publish_cli.receipt_pair", return_value=(None, None)), \
             patch("xray406_witness_publish_cli.publish", side_effect=Indeterminate) as publish, \
             redirect_stderr(StringIO()) as err:
            self.assertEqual(main(self.argv + ["--apply-isolated"]), 3)
            self.assertIn("DO_NOT_RETRY", err.getvalue())
            publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()

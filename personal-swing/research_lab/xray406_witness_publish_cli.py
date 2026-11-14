"""Operator entry point. Default is read-only and target is test-only."""
import argparse
from datetime import datetime, timezone
import json
import sys

from xray406_witness_acceptance import Rejected, utc
from xray406_witness_github import GitHubIsolatedTransport, TARGET, gh, receipt_pair
from xray406_witness_handoff import REPO, plan, staging_ref
from xray406_witness_publish import Indeterminate, publish


def main(argv=None, call=gh, clock=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-dir", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--cutoff-utc", required=True)
    parser.add_argument("--apply-isolated", action="store_true")
    a = parser.parse_args(argv)
    clock = clock or (lambda: datetime.now(timezone.utc))

    def scoped(path, payload=None):
        if path == "graphql":
            if not a.apply_isolated or payload is None:
                raise Rejected("MUTATION_REFUSED")
            refs = payload["variables"]["input"]["refUpdates"]
            if refs != [{"name": TARGET, "beforeOid": a.base,
                         "afterOid": a.candidate, "force": False}]:
                raise Rejected("MUTATION_REFUSED")
            return call(path, payload)
        if payload is not None or not (
            path == f"repos/{REPO}" or path.startswith(f"repos/{REPO}/")
        ):
            raise Rejected("READ_OUT_OF_SCOPE")
        return call(path)

    try:
        cutoff = utc(datetime.fromisoformat(a.cutoff_utc.replace("Z", "+00:00")))
        run, source = receipt_pair(a.run_id, a.attempt, a.candidate, scoped)
        t = GitHubIsolatedTransport(clock, scoped)
        if a.apply_isolated:
            result = publish(a.git_dir, a.base, a.candidate, run, source, t, clock, cutoff)
            record = {"result": "ISOLATED_PUBLISH_PASS", "observed_at": result.observed_at.isoformat()}
        else:
            ready = plan(a.git_dir, a.base, a.candidate, run, source,
                         t.head(staging_ref(a.candidate)), t.head("target"), clock(), cutoff)
            record = {"result": "ISOLATED_DRY_RUN_PASS", "latest_readback": ready.latest_observed_at.isoformat()}
        print(json.dumps({**record, "candidate": a.candidate, "target": TARGET}, sort_keys=True))
        return 0
    except Indeterminate:
        print("ISOLATED_WRITE_OUTCOME_UNPROVEN_DO_NOT_RETRY", file=sys.stderr)
        return 3
    except (Rejected, ValueError, KeyError, TypeError, OSError, RuntimeError):
        # Never emit tracebacks that could contain API response material.
        print("ISOLATED_WITNESS_GATE_REFUSED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

"""GitHub adapter for the isolated #406 Witness publisher, never for main."""
from datetime import datetime
import json
import re
import subprocess

from xray406_witness_acceptance import CHECK, GUARD, LEDGER, SHA, CheckReceipt, MainReceipt, require
from xray406_witness_handoff import REPO, STAGING_PREFIX, CheckSource, RunReceipt

TARGET = "refs/heads/xray-406-writer-probe-20261114"
MUTATION = """mutation Publish($input: UpdateRefsInput!) {
  updateRefs(input: $input) { clientMutationId }
}"""


def gh(path, payload=None):
    args = ["gh", "api", path]
    kwargs = {}
    if payload is not None:
        require(path == "graphql", "WRITES_MUST_USE_ATOMIC_REF_MUTATION")
        args += ["--input", "-"]
        kwargs["input"] = json.dumps(payload)
    result = subprocess.run(args, capture_output=True, text=True,
                            check=False, timeout=25, **kwargs)
    require(result.returncode == 0, "GITHUB_API_FAILED")
    return json.loads(result.stdout)


def api(path, call):
    return call(f"repos/{REPO}/{path}")


def receipt_pair(run_id, attempt, candidate, call=gh):
    require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0
            and isinstance(candidate, str) and SHA.fullmatch(candidate), "INVALID_EVIDENCE_INPUT")
    run = api(f"actions/runs/{run_id}/attempts/{attempt}", call)
    require(run["id"] == run_id and run["run_attempt"] == attempt, "RUN_ATTEMPT_MISMATCH")
    rr = RunReceipt(run["repository"]["full_name"], run["head_repository"]["full_name"],
                    "refs/heads/" + run["head_branch"], run["head_sha"], run["actor"]["login"],
                    run["event"], run["path"], run_id, attempt)
    result = api(f"commits/{candidate}/check-runs?check_name={CHECK}&filter=all&per_page=100", call)
    records = result["check_runs"]
    require(result["total_count"] == len(records) == 1, "CHECK_CARDINALITY")
    c = records[0]
    require(c["status"] == "completed", "CHECK_NOT_COMPLETED")
    jobs = api(f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100", call)
    require(jobs["total_count"] == len(jobs["jobs"]), "JOBS_INCOMPLETE")
    matching = [j for j in jobs["jobs"] if j["name"] == CHECK]
    require(len(matching) == 1, "CHECK_JOB_CARDINALITY")
    job = matching[0]
    require(job["head_sha"] == candidate and job["status"] == "completed"
            and job["conclusion"] == "success", "JOB_NOT_VERIFIED")
    stamp = datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00"))
    check = CheckReceipt(c["head_sha"], c["name"], c["app"]["id"], c["conclusion"], stamp)
    return rr, CheckSource(check, run_id, attempt, job["id"], c["details_url"])


class GitHubIsolatedTransport:
    def __init__(self, clock, call=gh):
        self.clock, self.call = clock, call

    def head(self, ref):
        if ref == "target":
            ref = TARGET
        require(ref == TARGET or re.fullmatch(re.escape(STAGING_PREFIX) + "[0-9a-f]{40}", ref),
                "REF_OUT_OF_SCOPE")
        response = api("git/ref/" + ref.removeprefix("refs/"), self.call)
        require(response["ref"] == ref and response["object"]["type"] == "commit"
                and SHA.fullmatch(response["object"]["sha"]), "REF_READ_UNVERIFIED")
        return response["object"]["sha"]

    def publish_once(self, expected, candidate):
        require(all(isinstance(v, str) and SHA.fullmatch(v) for v in (expected, candidate))
                and expected != candidate, "BAD_WRITE_SHAS")
        repo = self.call(f"repos/{REPO}")
        require(repo["full_name"] == REPO and repo["node_id"].startswith("R_"),
                "REPO_ID_NOT_VERIFIED")
        key = f"xray406-witness-{candidate}"
        payload = {"query": MUTATION, "variables": {"input": {
            "repositoryId": repo["node_id"], "clientMutationId": key,
            "refUpdates": [{"name": TARGET, "beforeOid": expected,
                            "afterOid": candidate, "force": False}],
        }}}
        result = self.call("graphql", payload)
        if result.get("errors"):
            return None
        return True if (result.get("data") or {}).get("updateRefs", {}).get(
            "clientMutationId") == key else None

    def read_target(self, candidate):
        head = self.head("target")
        require(head == candidate, "TARGET_NOT_CANDIDATE")
        # Read the two blobs from the immutable commit tree. The ledger is
        # large, so do not fetch its contents with the Contents API.
        root = api(f"git/commits/{head}", self.call)["tree"]["sha"]
        require(SHA.fullmatch(root), "BAD_ROOT_TREE")
        tree = api(f"git/trees/{root}", self.call)
        node = self.entry(tree, "nasdaq-xray", "tree", "040000")
        nested = api(f"git/trees/{node}", self.call)
        guard = self.entry(nested, GUARD.split("/")[-1], "blob", "100644")
        ledger = self.entry(nested, LEDGER.split("/")[-1], "blob", "100644")
        require(self.head("target") == head, "TARGET_MOVED_DURING_READBACK")
        return MainReceipt(head, self.clock(), guard, ledger)

    @staticmethod
    def entry(tree, path, kind, mode):
        require(tree.get("truncated") is False, "TREE_NOT_COMPLETE")
        entries = [e for e in tree["tree"] if e["path"] == path]
        require(len(entries) == 1 and entries[0]["type"] == kind
                and entries[0]["mode"] == mode and SHA.fullmatch(entries[0]["sha"]),
                "TREE_ENTRY_NOT_VERIFIED")
        return entries[0]["sha"]

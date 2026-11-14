"""Verify one natural #406 old-route receipt. No network or write methods."""
from dataclasses import dataclass
import re

from xray406_witness_acceptance import GUARD, LEDGER, SHA, require
from xray406_witness_handoff import REPO

MERGE = "6a9bd28133c7c227415faff4ea88ddd97602d24a"
PATH = ".github/workflows/xray-resilience-observability.yml"
PERSIST = "Persist official safety independent of blocked research pointer"
SUMMARY = "Record natural Official Witness publication evidence"
TITLE = "XRAY #406 · Natural Official Witness observation"
LABEL = "Observation of the existing publication route. Not staging CI or production cutover acceptance."
KEYS = ("WITNESS_BASE", "WITNESS_HEAD", "WITNESS_GUARD", "WITNESS_LEDGER")


@dataclass(frozen=True)
class Receipt:
    run_id: int
    job_id: int
    base: str
    head: str
    guard: str
    ledger: str
    status: str = "OLD_ROUTE_NATURAL_RECEIPT_VERIFIED"
    proves_first_visibility: bool = False


def sha(value):
    require(isinstance(value, str) and SHA.fullmatch(value), "MALFORMED_GIT_SHA")
    return value


def parse_summary(markdown):
    require(isinstance(markdown, str) and len(markdown) <= 65536, "SUMMARY_READBACK_MISSING")
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    headings = [i for i, line in enumerate(lines) if line in (TITLE, "### " + TITLE)]
    require(len(headings) == 1, "SUMMARY_CARDINALITY")
    start = headings[0]
    require(lines[start+1:start+2] == [LABEL], "SUMMARY_ROUTE_LABEL_MISSING")
    fields = {}
    for line in lines[start+2:]:
        match = re.fullmatch(r"(?:- )?(WITNESS_BASE|WITNESS_HEAD|WITNESS_GUARD|WITNESS_LEDGER): (?:`([0-9a-f]{40})`|([0-9a-f]{40}))", line)
        if not match:
            break
        key, formatted, plain = match.groups()
        require(key not in fields, "SUMMARY_DUPLICATE_FIELD")
        fields[key] = formatted or plain
    require(tuple(fields) == KEYS, "SUMMARY_FIELDS_INCOMPLETE")
    return tuple(fields[k] for k in KEYS)


def ancestor(earlier, later, get, code):
    if earlier == later:
        return
    result = get(f"compare/{earlier}...{later}")
    require(result.get("status") == "ahead"
            and (result.get("merge_base_commit") or {}).get("sha") == earlier, code)


def entry(data, tree_sha, name, kind, mode):
    require(data.get("sha") == tree_sha and data.get("truncated") is False,
            "WITNESS_TREE_INCOMPLETE")
    found = [x for x in data.get("tree", []) if x.get("path") == name]
    require(len(found) == 1 and found[0].get("type") == kind
            and found[0].get("mode") == mode, "WITNESS_TREE_ENTRY_INVALID")
    return sha(found[0].get("sha"))


def verify(run_id, job_id, run, jobs, summary, get):
    """Caller must collect inputs from exact GitHub readbacks, including summary.

    A successful result observes the old route only. A commit timestamp, an
    archive, and this receipt are never evidence of first public visibility.
    """
    require(type(run_id) is int and type(job_id) is int and min(run_id, job_id) > 0
            and (run.get("id"), run.get("run_attempt"), run.get("event"),
                 run.get("head_branch"), run.get("status"), run.get("conclusion"),
                 run.get("path"), (run.get("repository") or {}).get("full_name"),
                 (run.get("head_repository") or {}).get("full_name"))
            == (run_id, 1, "schedule", "main", "completed", "success", PATH, REPO, REPO),
            "NATURAL_RUN_NOT_VERIFIED")
    checkout = sha(run.get("head_sha"))
    entries = jobs.get("jobs", [])
    require(jobs.get("total_count") == len(entries), "NATURAL_JOBS_INCOMPLETE")
    matches = [job for job in entries if job.get("name") == "resilience"]
    require(len(matches) == 1, "NATURAL_JOB_CARDINALITY")
    job = matches[0]
    require((job.get("id"), job.get("run_id"), job.get("head_sha"),
             job.get("status"), job.get("conclusion"))
            == (job_id, run_id, checkout, "completed", "success"), "NATURAL_JOB_NOT_VERIFIED")
    step_numbers = []
    for name in (PERSIST, SUMMARY):
        steps = [step for step in job.get("steps", []) if step.get("name") == name]
        require(len(steps) == 1 and steps[0].get("status") == "completed"
                and steps[0].get("conclusion") == "success"
                and type(steps[0].get("number")) is int, "NATURAL_STEP_NOT_VERIFIED")
        step_numbers.append(steps[0]["number"])
    require(0 < step_numbers[0] < step_numbers[1], "NATURAL_STEP_ORDER_INVALID")
    base, head, guard, ledger = parse_summary(summary)
    ancestor(MERGE, checkout, get, "SOURCE_BEFORE_RECEIPT_MERGE")
    ancestor(checkout, base, get, "WITNESS_BASE_NOT_DESCENDANT")
    commit = get("commits/" + head)
    require(commit.get("sha") == head and [x.get("sha") for x in commit.get("parents", [])] == [base],
            "WITNESS_COMMIT_NOT_BOUND")
    files = commit.get("files", [])
    require(len(files) == 2 and all(f.get("status") == "modified" for f in files)
            and {f.get("filename"): f.get("sha") for f in files}
            == {GUARD: guard, LEDGER: ledger}, "WITNESS_DIFF_NOT_EXACT")
    obj = get("git/commits/" + head)
    require(obj.get("sha") == head, "WITNESS_GIT_OBJECT_NOT_BOUND")
    root = sha((obj.get("tree") or {}).get("sha"))
    nested = entry(get("git/trees/" + root), root, "nasdaq-xray", "tree", "040000")
    tree = get("git/trees/" + nested)
    found = tuple(entry(tree, nested, path.rsplit("/", 1)[1], "blob", "100644")
                  for path in (GUARD, LEDGER))
    require(found == (guard, ledger), "WITNESS_IMMUTABLE_BLOB_MISMATCH")
    return Receipt(run_id, job_id, base, head, guard, ledger)

"""Choose a versioned Nasdaq guard available by the completed-session cutoff.

Reads only the public GitHub repository, anchored to the actual checkout.
Does not call market providers or change a trading decision. Commit metadata
and an archived witness are not proof of first public availability.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.github.com/repos/gokaydonmez39-jpg/kripto-radar"
GUARD = "nasdaq-xray/canonical_official_source_guard.json"
MAX_BYTES = 2 * 1024 * 1024
MAX_VERSIONS = 20
MAX_AGE = timedelta(hours=24)


def instant(value):
    if type(value) is not str or not 1 <= len(value) <= 40:
        raise ValueError("BAD_TIME")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.utcoffset() != timedelta(0):
        raise ValueError("TIME_NOT_UTC")
    return t.astimezone(timezone.utc)


def choose(versions, cutoff):
    """Return raw bytes-as-text of the newest admissible version or None."""
    eligible = {}
    for commit, raw in versions:
        publication = instant(commit)
        if not cutoff - MAX_AGE <= publication <= cutoff:
            continue
        witness = json.loads(raw)
        if not isinstance(witness, dict):
            raise ValueError("BAD_WITNESS")
        seen = instant(witness.get("generated_at_utc"))
        if seen > publication:
            raise ValueError("WITNESS_CLOCK_AFTER_COMMIT")
        if seen < cutoff - MAX_AGE:
            continue
        key = seen, publication
        if key in eligible and json.loads(eligible[key]) != witness:
            raise ValueError("CONFLICTING_WITNESS")
        eligible[key] = raw
    return eligible[max(eligible)] if eligible else None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_reader(token):
    opener = build_opener(NoRedirect())
    def read(path, raw=False):
        if not path.startswith(("/commits?", "/contents/" + GUARD + "?")):
            raise ValueError("BAD_GITHUB_PATH")
        headers = {"Accept": "application/vnd.github.raw+json" if raw
                   else "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "xray-personal-477-guard-cutoff"}
        if token:
            headers["Authorization"] = "Bearer " + token
        with opener.open(Request(API + path, headers=headers), timeout=8) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("GITHUB_BODY_TOO_LARGE")
            return data.decode("utf-8")
    return read


def archived_guard(ref, cutoff, read):
    if type(ref) is not str or not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("BAD_CHECKOUT_SHA")
    args = urlencode(dict(sha=ref, path=GUARD, since=(cutoff - MAX_AGE).isoformat(),
                          until=cutoff.isoformat(), per_page=MAX_VERSIONS + 1))
    history = json.loads(read("/commits?" + args))
    if type(history) is not list or len(history) > MAX_VERSIONS:
        raise ValueError("GITHUB_HISTORY_UNCERTAIN")
    versions = []
    for item in history:
        sha = item["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("BAD_HISTORY_SHA")
        t = item["commit"]["committer"]["date"]
        if cutoff - MAX_AGE <= instant(t) <= cutoff:
            versions.append((t, read("/contents/" + GUARD + "?ref=" + sha, raw=True)))
    return choose(versions, cutoff)


def main():
    from official_shadow_477 import cutoff_for_session
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", required=True)
    p.add_argument("--ref", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    try:
        source, dest = Path(args.snapshot), Path(args.out)
        if source.resolve() == dest.resolve() or dest.exists() or dest.is_symlink():
            raise ValueError("OUTPUT_ALREADY_EXISTS")
        data = json.loads(source.read_text(encoding="utf-8"))
        raw = archived_guard(args.ref, cutoff_for_session(data["asof_et"]),
                             github_reader(os.environ.get("GITHUB_TOKEN", "")))
        if raw is None:
            print("OFFICIAL_SHADOW_GUARD=NO_TIMELY_REPO_WITNESS")
            return 1
        with dest.open("x", encoding="utf-8") as stream:
            stream.write(raw)
        print("OFFICIAL_SHADOW_GUARD=TIMELY_REPO_WITNESS_RESEARCH_ONLY")
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        print("OFFICIAL_SHADOW_GUARD=HISTORY_UNCERTAIN")
        return 2


if __name__ == "__main__":
    sys.exit(main())

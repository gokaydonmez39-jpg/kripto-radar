#!/usr/bin/env python3
"""A44 read-only GitHub source metadata witness for an A43-admitted cohort.

Never downloads, imports, executes or installs third-party code. Nothing here
can approve a candidate for production, alpha, trading or private data access.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

SCOPE = "NASDAQ_RESEARCH_ONLY_NO_CRYPTO"
ACCEPTED_LICENSE_IDENTIFIERS = frozenset({
    "mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc"
})
SHA40 = re.compile(r"^[0-9a-f]{40}$")
OWNER_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
MAX_BODY = 256 * 1024


class AdmissionError(ValueError):
    pass


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise AdmissionError(msg)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def github_repo_url(url: str) -> tuple[str, str] | None:
    """A deliberately narrow allowlist, not a general browser."""
    if not isinstance(url, str):
        return None
    try:
        u = urlparse(url)
        parts = u.path.strip("/").split("/")
        if (u.scheme != "https" or u.hostname != "github.com" or
                u.port not in (None, 443) or u.username is not None or
                u.password is not None or u.query or u.fragment or
                len(parts) < 2 or not all(OWNER_REPO.fullmatch(p) for p in parts[:2])):
            return None
        name = parts[1].removesuffix(".git")
        if not name or name in (".", "..") or parts[0] in (".", ".."):
            return None
        return parts[0], name
    except ValueError:
        return None


def public_github_get(path: str, *, timeout: float = 5.0) -> dict:
    require(isinstance(path, str) and re.fullmatch(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
                                                 r"(?:/commits/[A-Za-z0-9_.%/-]+)?", path),
            "INVALID_GITHUB_API_PATH")
    opener = build_opener(NoRedirect, HTTPSHandler(context=ssl.create_default_context()))
    headers = {"User-Agent": "xray-nasdaq-a44-readonly/1.0",
               "Accept": "application/vnd.github+json"}
    # Standard read-only token for API rate quota. Never forward to candidate URL.
    token = os.environ.get("GH_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request("https://api.github.com" + path, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=timeout) as resp:
            require(resp.status == 200, "GITHUB_API_NON_200")
            body = resp.read(MAX_BODY + 1)
            require(len(body) <= MAX_BODY, "GITHUB_API_OVERSIZE")
            parsed = json.loads(body)
            require(isinstance(parsed, dict), "GITHUB_API_NON_OBJECT")
            return parsed
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise AdmissionError("GITHUB_API_UNAVAILABLE_" + type(exc).__name__) from None


def source_classification(row: dict, *, fetcher=public_github_get) -> dict:
    require(type(row) is dict and type(row.get("registry_id")) is int,
            "BAD_CANDIDATE_ROW")
    url = row.get("url", "")
    result = {"registry_id": row["registry_id"],
              "name": row.get("name", ""), "tier": row.get("tier", ""),
              "source_url": url, "stage": "SOURCE_METADATA_ONLY",
              "promotion": "BLOCKED_PENDING_INDEPENDENT_FUNCTIONAL_AND_PIT_TEST",
              "run_upstream_code": False, "broker": False, "license_approved": False,
              "status": "SOURCE_PROVENANCE_UNKNOWN"}
    parsed = github_repo_url(url)
    if parsed is None:
        result["status"] = "NON_GITHUB_OR_MISSING_URL_MANUAL_PROVENANCE"
        return result
    owner, name = parsed
    path = "/repos/" + owner + "/" + name
    try:
        data = fetcher(path)
        require(isinstance(data, dict), "GITHUB_METADATA_INVALID")
        full = data.get("full_name")
        require(isinstance(full, str) and full.casefold() == (owner + "/" + name).casefold(),
                "GITHUB_REPO_ID_MISMATCH")
        require(type(data.get("id")) is int and data["id"] > 0 and
                data.get("private") is False, "GITHUB_REPO_NOT_VERIFIED_PUBLIC")
        result["canonical_repo"] = full
        result["repo_numeric_id"] = data["id"]
        result["archived"] = data.get("archived")
        result["fork"] = data.get("fork")
        if data.get("archived") is not False or data.get("disabled") is True:
            result["status"] = "HOLD_ARCHIVED_DISABLED_OR_UNVERIFIED"
            return result
        # Forks must be audited against their authoritative upstream source.
        if data.get("fork") is not False:
            result["status"] = "HOLD_FORK_PARENT_NOT_VERIFIED"
            return result
        license_data = data.get("license")
        key = license_data.get("key", "") if isinstance(license_data, dict) else ""
        result["license_tag"] = key
        if not isinstance(key, str) or key.casefold() not in ACCEPTED_LICENSE_IDENTIFIERS:
            result["status"] = "HOLD_LICENSE_REVIEW"
            return result
        branch = data.get("default_branch")
        require(isinstance(branch, str) and re.fullmatch(r"[A-Za-z0-9_./-]{1,100}", branch) is not None,
                "INVALID_DEFAULT_BRANCH")
        commit = fetcher(path + "/commits/" + quote(branch, safe=""))
        require(isinstance(commit, dict) and isinstance(commit.get("sha"), str) and
                SHA40.fullmatch(commit["sha"]), "SOURCE_COMMIT_SHA_UNKNOWN")
        result["source_head_sha"] = commit["sha"]
        result["status"] = "PROVENANCE_RECORDED_TEST_REQUIRED"
        # License tags are not legal reviews. Even success stays non-promotable.
        return result
    except AdmissionError as ex:
        result["status"] = "SOURCE_PROBE_UNKNOWN"
        result["diagnostic"] = str(ex)
        return result


def build_assessment(receipt: dict, raw: bytes, *, network: bool,
                     fetcher=public_github_get) -> dict:
    require(isinstance(receipt, dict) and receipt.get("schema") ==
            "XRAY_NASDAQ_CANDIDATE_AUTOPILOT_RECEIPT_V1", "A42_RECEIPT_INVALID")
    require(receipt.get("source") == SCOPE and receipt.get("automatic_promotion") is False,
            "A42_SCOPE_OR_PROMOTION_CONFLICT")
    require(receipt.get("orders") is False and receipt.get("private_sheet_writes") is False,
            "A42_UNSAFE_SIDE_EFFECTS")
    findings = receipt.get("findings")
    require(isinstance(findings, list) and 1 <= len(findings) <= 7, "BATCH_BOUND_BREACH")
    require(all(isinstance(row, dict) and row.get("integration_status") == "NOT_INTEGRATED"
                for row in findings), "A42_PREMATURE_INTEGRATION_CLAIM")
    ids = [row["registry_id"] for row in findings]
    require(all(type(x) is int and 1 <= x <= 284 for x in ids) and
            len(set(ids)) == len(ids), "CANDIDATE_ID_DRIFT")
    outputs = [source_classification(row, fetcher=fetcher) if network else
               {**source_classification({**row, "url": ""}, fetcher=fetcher),
                "status": "OFFLINE_UNPROBED"} for row in findings]
    result = {"schema": "XRAY_NASDAQ_A44_SOURCE_EVIDENCE_V1",
              "registry_sha256": receipt["registry_sha256"],
              "candidate_receipt_sha256": hashlib.sha256(raw).hexdigest(),
              "asof_et": receipt["asof"],
              "scope": SCOPE, "automatic_promotion": False,
              "network_enabled": network, "results": outputs}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--network", action="store_true")
    args = parser.parse_args()
    raw = Path(args.receipt).read_bytes()
    result = build_assessment(json.loads(raw), raw, network=args.network)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    counts = {}
    for row in result["results"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("XRAY_A44=PASS;SOURCES=%d;AUTOPROMOTE=FALSE;STATUSES=%s" %
          (len(result["results"]), json.dumps(counts, sort_keys=True)))


if __name__ == "__main__":
    main()

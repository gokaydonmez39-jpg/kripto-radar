#!/usr/bin/env python3
"""Personal 477 EOD: atomic per-session Git reference lease foundation.

NOT enabled in production. No new timer, dispatch, Sheet, order, or delivery.
GitHub's create-ref is the single acquisition point for cooperating writers.
A CAS-like read/check/write against a Google Sheet is NOT an atomic lock.
A protected, non-rewritable tag namespace and real credential canary are
necessary BEFORE this can guard a live producer.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import re

REPO = "gokaydonmez39-jpg/kripto-radar"
WORKFLOW = ".github/workflows/xray-personal-477-eod.yml"
REF_PREFIX = "refs/tags/xray-personal477-eod-epoch-"
TAG_PREFIX = "xray-personal477-eod-epoch-"
SCHEMA = "XRAY_PERSONAL_477_EPOCH_LEASE_V1"
PROTECTED_PATTERN = "refs/tags/xray-personal477-eod-epoch-*"
SHA40 = re.compile(r"[0-9a-f]{40}")
RUN = re.compile(r"[1-9][0-9]*")


class LeaseHold(ValueError):
    pass


def require(ok, stage):
    if not ok:
        raise LeaseHold(stage)


def epoch_tag(asof):
    require(isinstance(asof, str) and
            re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", asof) is not None,
            "EPOCH_DATE_INVALID")
    try:
        require(date.fromisoformat(asof).isoformat() == asof,
                "EPOCH_DATE_INVALID")
    except ValueError:
        raise LeaseHold("EPOCH_DATE_INVALID") from None
    return TAG_PREFIX + asof


def verified_natural_owner(env, asof, now=None, *, completed_session=None):
    """Construct owner only from exact main/schedule/attempt-one identity.

    completed_session is injectable ONLY for isolated no-I/O regression tests.
    Production must use the real official XNAS calendar and 10h cutoff.
    """
    require(isinstance(env, dict), "LEASE_RUN_IDENTITY_UNKNOWN")
    now = now if now is not None else datetime.now(timezone.utc)
    require(isinstance(now, datetime) and now.tzinfo is not None and
            now.utcoffset() is not None, "LEASE_CLOCK_UNKNOWN")
    now = now.astimezone(timezone.utc)
    tag = epoch_tag(asof)
    sha, rid = env.get("GITHUB_SHA"), env.get("GITHUB_RUN_ID")
    require(
        env.get("GITHUB_REPOSITORY") == REPO and
        env.get("GITHUB_REF") == "refs/heads/main" and
        env.get("GITHUB_WORKFLOW_REF") ==
            REPO + "/" + WORKFLOW + "@refs/heads/main" and
        env.get("GITHUB_EVENT_NAME") == "schedule" and
        env.get("GITHUB_RUN_ATTEMPT") == "1" and
        isinstance(sha, str) and SHA40.fullmatch(sha) is not None and
        isinstance(rid, str) and RUN.fullmatch(rid) is not None,
        "LEASE_NATURAL_PRODUCER_UNVERIFIED",
    )
    try:
        import daily_job
        current = (completed_session(now) if completed_session is not None
                   else daily_job.current_completed_session(now))
        require(current == asof, "LEASE_XNAS_CURRENT_WINDOW_UNVERIFIED")
    except LeaseHold:
        raise
    except Exception:
        raise LeaseHold("LEASE_XNAS_CURRENT_WINDOW_UNVERIFIED") from None
    return {
        "schema": SCHEMA, "asof_et": asof, "ref": REF_PREFIX + asof,
        "tag": tag, "source_event": "schedule", "workflow": WORKFLOW,
        "source_sha": sha, "run_id": int(rid), "run_attempt": 1,
        "observed_at": now.isoformat().replace("+00:00", "Z"),
    }


def _manifest(owner):
    keys=("schema","asof_et","ref","tag","source_event","workflow",
          "source_sha","run_id","run_attempt","observed_at")
    require(isinstance(owner, dict) and
            isinstance(owner.get("asof_et"),str) and
            owner.get("schema") == SCHEMA and
            owner.get("source_event") == "schedule" and
            owner.get("ref") == REF_PREFIX + owner.get("asof_et","") and
            owner.get("tag") == TAG_PREFIX + owner.get("asof_et","") and
            isinstance(owner.get("source_sha"),str) and
            SHA40.fullmatch(owner["source_sha"]) is not None and
            type(owner.get("run_id")) is int and owner["run_id"] > 0 and
            owner.get("run_attempt") == 1 and
            owner.get("workflow") == WORKFLOW and
            all(k in owner for k in keys), "LEASE_OWNER_CONTRACT_INVALID")
    return json.dumps({key:owner[key] for key in keys},
                      sort_keys=True,separators=(",",":"),ensure_ascii=True)


def verify_live_tag_protection(transport):
    """Read ruleset list + exact tag-rule details before ANY write.

    Neither branch rulesets nor unprotected tags are an immutable lease.
    A matching rule must forbid updates/deletions and have no bypass actors.
    An administrator can still alter repository rules: a later production
    integration must recheck protection at every acquisition/readback.
    """
    summary=transport("GET","/rulesets")
    require(isinstance(summary,list),"LEASE_TAG_PROTECTION_UNVERIFIED")
    candidates=[r for r in summary
                if isinstance(r,dict) and r.get("target")=="tag" and
                r.get("enforcement")=="active" and
                isinstance(r.get("id"),int) and r["id"]>0]
    for item in candidates:
        detailed=transport("GET","/rulesets/"+str(item["id"]))
        if not isinstance(detailed,dict):
            continue
        cond=detailed.get("conditions",{}).get("ref_name",{})
        if not isinstance(cond,dict):
            continue
        rules=detailed.get("rules")
        if (detailed.get("id")==item["id"] and
                detailed.get("target")=="tag" and
                detailed.get("enforcement")=="active" and
                cond.get("include")==[PROTECTED_PATTERN] and
                cond.get("exclude")==[] and
                detailed.get("bypass_actors")==[] and
                isinstance(rules,list) and
                {"update","deletion"}.issubset(
                    {rule.get("type") for rule in rules
                     if isinstance(rule,dict)})):
            return True
    raise LeaseHold("LEASE_TAG_PROTECTION_UNVERIFIED")


def acquire_first_claim(owner, transport):
    """One unrepeatable claim, followed by two independent GET checks.

    Every uncertain/error/duplicate POST fails closed. No retries, even after
    a timeout. A lease alone NEVER constitutes an EOD or ChatGPT acceptance.
    """
    message=_manifest(owner)
    require(callable(transport), "LEASE_TRANSPORT_UNAVAILABLE")
    try:
        verify_live_tag_protection(transport)
        tagged=transport("POST", "/git/tags", {
            "tag": owner["tag"], "message": message,
            "object": owner["source_sha"], "type": "commit",
            "tagger": {
                "name": "github-actions[bot]",
                "email": "41898282+github-actions[bot]@users.noreply.github.com",
                "date": owner["observed_at"],
            },
        })
        tag_sha=tagged.get("sha") if isinstance(tagged,dict) else None
        require(isinstance(tag_sha,str) and SHA40.fullmatch(tag_sha) is not None,
                "LEASE_TAG_OBJECT_UNVERIFIED")
        # This is the ONLY atomic first-claim operation for a given ASOF.
        # Duplicate/unknown result may never re-enter the write path.
        ref=transport("POST", "/git/refs", {
            "ref": owner["ref"], "sha": tag_sha,
        })
        require(isinstance(ref,dict) and ref.get("ref")==owner["ref"] and
                isinstance(ref.get("object"),dict) and
                ref["object"].get("sha")==tag_sha and
                ref["object"].get("type")=="tag",
                "LEASE_CREATE_REF_UNVERIFIED")
        observed_ref=transport("GET", "/git/ref/tags/"+owner["tag"])
        observed_tag=transport("GET", "/git/tags/"+tag_sha)
        require(
            isinstance(observed_ref,dict) and
            observed_ref.get("ref")==owner["ref"] and
            isinstance(observed_ref.get("object"),dict) and
            observed_ref["object"].get("sha")==tag_sha and
            observed_ref["object"].get("type")=="tag" and
            isinstance(observed_tag,dict) and
            observed_tag.get("tag")==owner["tag"] and
            observed_tag.get("sha")==tag_sha and
            observed_tag.get("message")==message and
            isinstance(observed_tag.get("object"),dict) and
            observed_tag["object"].get("type")=="commit" and
            observed_tag["object"].get("sha")==owner["source_sha"],
            "LEASE_READBACK_CONFLICT")
        # Ref and annotation may have been valid when read, but a ruleset
        # can be disabled between the first preflight and creation.
        # A previously created ref must NEVER confer write authority
        # after its immutability guarantee disappeared. This is a
        # post-readback GET-only check; no retry or compensating delete.
        verify_live_tag_protection(transport)
    except LeaseHold:
        raise
    except HTTPError as error:
        # 422 may mean a collision OR provider validation/rate limit.
        # Either way this caller is not authorized to proceed.
        raise LeaseHold("LEASE_REF_COLLISION_OR_PROVIDER_REJECTION"
                        if error.code==422 else "LEASE_GITHUB_HTTP_UNCERTAIN") from None
    except (URLError, TimeoutError, OSError, ValueError, TypeError, KeyError):
        raise LeaseHold("LEASE_GITHUB_TRANSPORT_UNCERTAIN") from None
    return {
        "state": "FIRST_CLAIM_READBACK_VERIFIED_NOT_EOD",
        "schema": SCHEMA, "asof_et": owner["asof_et"],
        "run_id": owner["run_id"], "tag_sha": tag_sha,
        "ref": owner["ref"], "source_sha": owner["source_sha"],
        "source_event": "schedule", "sheet_writes": 0,
        "orders": False, "ab_release_authorized": False,
        "device_ack": "UNKNOWN",
    }


def github_transport(token, *, opener=urlopen):
    """Optional authenticated transport. NEVER log token, URL or HTTP body."""
    require(isinstance(token,str) and bool(token),
            "LEASE_GITHUB_TOKEN_NOT_CONFIGURED")
    prefix="https://api.github.com/repos/"+REPO
    def call(method,path,body=None):
        allowed=(path.startswith("/git/") or
                 (method=="GET" and
                  (path=="/rulesets" or
                   re.fullmatch(r"/rulesets/[1-9][0-9]*",path) is not None)))
        require(method in ("POST","GET") and allowed and
                ".." not in path and "?" not in path,
                "LEASE_API_PATH_INVALID")
        data=(json.dumps(body,separators=(",",":")).encode("utf-8")
              if body is not None else None)
        request=Request(prefix+path,data=data,method=method,headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"xray-personal477-epoch-lease",
            "Content-Type":"application/json",
        })
        with opener(request,timeout=20) as response:
            require(response.status==(201 if method=="POST" else 200),
                    "LEASE_GITHUB_STATUS_UNVERIFIED")
            return json.load(response)
    return call


# IMPORTANT: This module intentionally has no CLI or automatically invoked
# production entry point. Activate only after a real tag-create collision
# canary, immutable Git tag protection, parent-child provenance, and the
# private Sheet/A/B consumer contracts are independently accepted.

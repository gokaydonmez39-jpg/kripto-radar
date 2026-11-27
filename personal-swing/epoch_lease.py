#!/usr/bin/env python3
"""Personal 477 EOD: atomic per-session Git reference lease foundation.

NOT enabled in production. No new timer, dispatch, Sheet, order, or delivery.
GitHub's create-ref is the single acquisition point for cooperating writers.
A CAS-like read/check/write against a Google Sheet is NOT an atomic lock.
A protected, non-rewritable tag namespace and real credential canary are
necessary BEFORE this can guard a live producer.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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


def _manifest(owner, *, now=None):
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
            type(owner.get("run_attempt")) is int and
            owner["run_attempt"] == 1 and
            owner.get("workflow") == WORKFLOW and
            all(k in owner for k in keys), "LEASE_OWNER_CONTRACT_INVALID")
    # This is a SECOND admission boundary. A caller passing a forged owner
    # may never turn an invalid/stale ASOF into a PERMANENT protected tag.
    # Do not trust a well-formed free-text ref alone.
    try:
        require(owner["tag"]==epoch_tag(owner["asof_et"]),
                "LEASE_OWNER_CONTRACT_INVALID")
        observed=owner["observed_at"]
        require(isinstance(observed,str) and re.fullmatch(
                    r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T"
                    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?Z",
                    observed) is not None,"LEASE_OWNER_CONTRACT_INVALID")
        parsed=datetime.fromisoformat(observed.replace("Z","+00:00"))
        require(parsed.tzinfo is not None and
                parsed.utcoffset()==timedelta(0) and
                parsed.isoformat().replace("+00:00","Z")==observed,
                "LEASE_OWNER_CONTRACT_INVALID")
        at=now if now is not None else datetime.now(timezone.utc)
        require(isinstance(at,datetime) and at.tzinfo is not None and
                at.utcoffset() is not None,"LEASE_OWNER_CONTRACT_INVALID")
        at=at.astimezone(timezone.utc)
        elapsed=at-parsed
        require(-timedelta(seconds=5)<=elapsed<=timedelta(minutes=5),
                "LEASE_OWNER_CONTRACT_INVALID")
        import daily_job
        require(daily_job.current_completed_session(at)==owner["asof_et"],
                "LEASE_OWNER_CONTRACT_INVALID")
    except Exception:
        # Provider/calendar/time errors all DENY before the first GET/POST.
        raise LeaseHold("LEASE_OWNER_CONTRACT_INVALID") from None
    return json.dumps({key:owner[key] for key in keys},
                      sort_keys=True,separators=(",",":"),ensure_ascii=True)


def verify_live_tag_protection(transport, *, probe_only=False):
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
    if not candidates:
        raise LeaseHold("LEASE_TAG_PROTECTION_UNVERIFIED:ACTIVE_TAG_NOT_VISIBLE")
    exact_rule_without_bypass=False
    unavailable_bypass=False
    for item in candidates:
        detailed=transport("GET","/rulesets/"+str(item["id"]))
        if not isinstance(detailed,dict):
            continue
        cond=detailed.get("conditions",{}).get("ref_name",{})
        if not isinstance(cond,dict):
            continue
        rules=detailed.get("rules")
        exact=(detailed.get("id")==item["id"] and
               detailed.get("target")=="tag" and
               detailed.get("enforcement")=="active" and
               cond.get("include")==[PROTECTED_PATTERN] and
               cond.get("exclude")==[] and
               isinstance(rules,list) and
               {"update","deletion","non_fast_forward"}.issubset(
                   {rule.get("type") for rule in rules
                    if isinstance(rule,dict)}))
        if not exact:
            continue
        exact_rule_without_bypass=True
        bypass=detailed.get("bypass_actors")
        if bypass==[]:
            return True
        if bypass is None:
            unavailable_bypass=True
    if unavailable_bypass:
        if probe_only:
            # Action token may omit admin-only bypass metadata. This proves
            # ONLY public rule conditions, NEVER full immutability authority.
            return "TAG_RULESET_PROJECTION_PASS_BYPASS_UNKNOWN"
        raise LeaseHold("LEASE_TAG_PROTECTION_UNVERIFIED:BYPASS_FIELD_UNAVAILABLE")
    if exact_rule_without_bypass:
        raise LeaseHold("LEASE_TAG_PROTECTION_UNVERIFIED:BYPASS_ACTOR_PRESENT")
    raise LeaseHold("LEASE_TAG_PROTECTION_UNVERIFIED:EXACT_RULE_MISMATCH")


def verify_live_natural_run_receipt(owner, receipt, *, now):
    """Require actual GitHub REST run identity before *any* permanent tag.

    GITHUB_* process environment alone cannot prove that a run ID actually
    belongs to this canonical scheduled EOD. This read-only witness is a
    NECESSARY precondition, never a standalone lease or delivery receipt.
    """
    require(isinstance(owner,dict) and isinstance(receipt,dict) and
            isinstance(now,datetime) and now.tzinfo is not None and
            now.utcoffset() is not None,
            "LEASE_NATURAL_RUN_READBACK_UNVERIFIED")
    observed=now.astimezone(timezone.utc)
    require(type(receipt.get("id")) is int and
            receipt["id"] == owner["run_id"] and
            type(receipt.get("run_attempt")) is int and
            receipt["run_attempt"] == 1 and
            receipt.get("event") == "schedule" and
            receipt.get("path") == WORKFLOW and
            receipt.get("head_branch") == "main" and
            receipt.get("head_sha") == owner["source_sha"] and
            isinstance(receipt.get("repository"),dict) and
            receipt["repository"].get("full_name") == REPO and
            receipt.get("status") == "in_progress" and
            receipt.get("conclusion") is None,
            "LEASE_NATURAL_RUN_READBACK_UNVERIFIED")

    def utc(raw):
        if not isinstance(raw,str) or not raw.endswith("Z"):
            return None
        try:
            parsed=datetime.fromisoformat(raw[:-1]+"+00:00")
            if parsed.isoformat().replace("+00:00","Z")!=raw:
                return None
            return parsed
        except ValueError:
            return None

    created=utc(receipt.get("created_at"))
    updated=utc(receipt.get("updated_at"))
    require(created is not None and updated is not None and
            created <= updated <= observed+timedelta(seconds=5) and
            observed-timedelta(hours=10) <= created,
            "LEASE_NATURAL_RUN_READBACK_UNVERIFIED")
    # A scheduled run created before the *actual* XNAS close+45m can never
    # claim the protected day, even if its event and branch labels look good.
    try:
        import exchange_calendars as ec
        calendar=ec.get_calendar("XNAS")
        require(calendar.is_session(owner["asof_et"]),
                "LEASE_NATURAL_RUN_READBACK_UNVERIFIED")
        cutoff=(calendar.session_close(owner["asof_et"]).to_pydatetime()
                .astimezone(timezone.utc)+timedelta(minutes=45))
    except LeaseHold:
        raise
    except Exception:
        raise LeaseHold("LEASE_NATURAL_RUN_READBACK_UNVERIFIED") from None
    # The immutable source collection is scoped to the EXACT same
    # official XNAS close+45m through +10h epoch. The direct run-ID GET
    # must enforce that upper bound independently: a late natural run
    # cannot be trusted merely because it is still "in_progress".
    # Inclusive at the cutoff and +10h boundary; +1 second is HOLD.
    require(cutoff <= created <= cutoff + timedelta(hours=10),
            "LEASE_NATURAL_RUN_READBACK_UNVERIFIED")
    return True


def verify_live_unique_natural_epoch(owner, receipt, transport):
    """Require the exact official-XNAS-window listing to contain THIS run only.

    The earlier offline-guard admission is not transferable to a later
    first-claim or Sheet POST. Lazy import avoids module import cycles;
    every call is read-only and a missing/malformed/duplicate page is HOLD.
    """
    import natural_run_readonly_probe as source
    source.verify_unique_natural_epoch(owner, receipt, transport)
    return True


def acquire_first_claim(owner, transport, *, now=None, runtime_env=None):
    """One unrepeatable claim, followed by two independent GET checks.

    Every uncertain/error/duplicate POST fails closed. No retries, even after
    a timeout. A lease alone NEVER constitutes an EOD or ChatGPT acceptance.
    The caller's source_event field is NOT authoritative: independently
    re-derive the producer identity from the real GitHub runner environment.
    runtime_env and now injection are strictly for OFFLINE tests.
    """
    captured=now if now is not None else datetime.now(timezone.utc)
    message=_manifest(owner,now=captured)
    require(callable(transport), "LEASE_TRANSPORT_UNAVAILABLE")
    # Do this after strict timestamp/window validation but BEFORE *any* IO.
    # A forged owner with source_event='schedule' is not a natural run.
    import os
    if runtime_env is not None:
        require(now is not None,"LEASE_OWNER_PROVENANCE_UNVERIFIED")
    live=dict(os.environ) if runtime_env is None else dict(runtime_env)
    try:
        observed=datetime.fromisoformat(owner["observed_at"].replace("Z","+00:00"))
        reconstructed=verified_natural_owner(live,owner["asof_et"],observed)
    except LeaseHold:
        raise
    except Exception:
        raise LeaseHold("LEASE_NATURAL_PRODUCER_UNVERIFIED") from None
    require(owner==reconstructed,"LEASE_OWNER_PROVENANCE_UNVERIFIED")
    try:
        # Independently read the *real* GitHub scheduled run before any POST.
        # No unproven GITHUB_RUN_ID or manually forged source owner may write
        # a one-way protected epoch tag.
        current_run=transport("GET","/actions/runs/"+str(owner["run_id"]))
        verify_live_natural_run_receipt(owner,current_run,now=captured)
        verify_live_unique_natural_epoch(owner,current_run,transport)
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
        # A second schedule may appear between the first GET and the
        # permanent ref POST. Do not return a usable lease to the Sheet
        # writer if the source collection is now ambiguous.
        verify_live_unique_natural_epoch(owner,current_run,transport)
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


def verify_existing_tag_consumer(asof, transport, *, now=None,
                                 runtime_env=None, completed_session=None,
                                 recovery_owner_shadow=False):
    """Independently re-read current natural owner's protected lease; GET only.

    This cannot acquire ownership or release Sheets/A/B. Future consumers
    may use its source witness only after separate integration/race tests.
    Caller-injected runtime/clock/session are for isolated OFFLINE tests.
    Never retry or mutate a missing/ambiguous permanent tag.
    """
    require(type(recovery_owner_shadow) is bool, "LEASE_RECOVERY_SHADOW_MODE_INVALID")
    captured=now if now is not None else datetime.now(timezone.utc)
    require(isinstance(captured,datetime) and captured.tzinfo is not None and
            captured.utcoffset() is not None,
            "LEASE_CONSUMER_CLOCK_UNVERIFIED")
    captured=captured.astimezone(timezone.utc)
    require(callable(transport),"LEASE_CONSUMER_TRANSPORT_UNAVAILABLE")
    import os
    if runtime_env is not None:
        require(now is not None,"LEASE_CONSUMER_PROVENANCE_UNVERIFIED")
    live=dict(os.environ) if runtime_env is None else dict(runtime_env)
    # Reject manual dispatch, rerun, other repo/branch/workflow, invalid ASOF
    # and an uncompleted XNAS session BEFORE contacting a tag endpoint.
    expected=verified_natural_owner(
        live,asof,captured,completed_session=completed_session)
    try:
        verify_live_tag_protection(transport)
        ref=transport("GET","/git/ref/tags/"+expected["tag"])
        require(isinstance(ref,dict) and
                ref.get("ref")==expected["ref"] and
                isinstance(ref.get("object"),dict) and
                ref["object"].get("type")=="tag",
                "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED")
        tag_sha=ref["object"].get("sha")
        require(isinstance(tag_sha,str) and
                SHA40.fullmatch(tag_sha) is not None,
                "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED")
        tag=transport("GET","/git/tags/"+tag_sha)
        require(isinstance(tag,dict) and tag.get("sha")==tag_sha and
                tag.get("tag")==expected["tag"] and
                isinstance(tag.get("message"),str) and
                isinstance(tag.get("object"),dict) and
                tag["object"].get("type")=="commit",
                "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED")
        try:
            manifest=json.loads(tag["message"])
            keys=("schema","asof_et","ref","tag","source_event",
                  "workflow","source_sha","run_id","run_attempt",
                  "observed_at")
            require(isinstance(manifest,dict) and
                    set(manifest)==set(keys),
                    "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED")
            observed=manifest["observed_at"]
            require(isinstance(observed,str) and observed.endswith("Z"),
                    "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED")
            attested=datetime.fromisoformat(
                observed.replace("Z","+00:00"))
            require(attested.utcoffset()==timedelta(0) and
                    -timedelta(seconds=5)<=captured-attested<=timedelta(hours=10),
                    "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED")
            # Exact canonical manifest bytes: no duplicate JSON keys,
            # alternative serialization or unrecognized injected claims.
            canonical=_manifest(manifest,now=attested)
            require(tag["message"]==canonical and
                    tag["object"].get("sha")==manifest["source_sha"],
                    "LEASE_CONSUMER_TAG_READBACK_UNVERIFIED")
        except (ValueError,TypeError,KeyError,LeaseHold):
            raise LeaseHold("LEASE_CONSUMER_TAG_READBACK_UNVERIFIED") from None
        # The current writer's actual natural run must equal the immutable
        # recorded tag owner. A later run may NEVER borrow another run's tag.
        fields=("schema","asof_et","ref","tag","source_event","workflow",
                "source_sha","run_id","run_attempt")
        require(all(manifest[k]==expected[k] for k in fields),
                "LEASE_CONSUMER_OWNER_MISMATCH")
        actual=transport("GET","/actions/runs/"+str(expected["run_id"]))
        verify_live_natural_run_receipt(manifest,actual,now=captured)
        if recovery_owner_shadow:
            import natural_run_readonly_probe as source
            shadow=source.verify_owned_natural_epoch(manifest,actual,transport,now=captured)
            require(shadow.get("state")=="IMMUTABLE_OWNER_COLLECTION_READ_ONLY" and
                    shadow.get("write_authority") is False and shadow.get("writes")==0,
                    "LEASE_RECOVERY_SHADOW_INVALID")
        else:
            verify_live_unique_natural_epoch(manifest,actual,transport)
        # Repository protection might have been revoked during readback:
        # a previously valid tag is not sufficient if protection is gone.
        verify_live_tag_protection(transport)
    except LeaseHold:
        raise
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError,KeyError):
        raise LeaseHold("LEASE_CONSUMER_TAG_READBACK_UNVERIFIED") from None
    return {
        "state":("LEASE_RECOVERY_OWNER_SHADOW_READBACK_ONLY" if recovery_owner_shadow
                 else "LEASE_OWNER_READBACK_ONLY"), "schema":SCHEMA,
        "asof_et":asof, "run_id":expected["run_id"],
        "source_sha":expected["source_sha"], "tag_sha":tag_sha,
        "source_event":"schedule", "sheet_writes":0,
        "orders":False, "ab_release_authorized":False,
        "device_ack":"UNKNOWN",
        **({"recovery_owner_shadow":shadow, "write_authority":False} if recovery_owner_shadow else {}),
    }


def verify_scoped_git_write_body(path, body):
    """No generic Git writes: only canonical NASDAQ 477 epoch tag/ref bodies.

    This checks the exact *payload* before the HTTP boundary. Existing
    natural-producer, official XNAS-window, live ruleset, single-owner and
    readback gates remain separately mandatory. This helper never grants a
    live claim, Sheet POST or delivery.
    """
    try:
        require(type(body) is dict, "LEASE_API_BODY_INVALID")
        if path == "/git/refs":
            require(set(body) == {"ref", "sha"} and
                    isinstance(body.get("ref"), str) and
                    isinstance(body.get("sha"), str) and
                    SHA40.fullmatch(body["sha"]) is not None and
                    body["ref"].startswith(REF_PREFIX),
                    "LEASE_API_BODY_INVALID")
            asof = body["ref"][len(REF_PREFIX):]
            require(body["ref"] == "refs/tags/" + epoch_tag(asof),
                    "LEASE_API_BODY_INVALID")
            import exchange_calendars as ec
            require(ec.get_calendar("XNAS").is_session(asof),
                    "LEASE_API_BODY_INVALID")
            return True

        require(path == "/git/tags" and
                set(body) == {"tag", "message", "object",
                              "type", "tagger"} and
                isinstance(body.get("tag"), str) and
                body["tag"].startswith(TAG_PREFIX) and
                isinstance(body.get("message"), str) and
                isinstance(body.get("object"), str) and
                SHA40.fullmatch(body["object"]) is not None and
                body.get("type") == "commit" and
                type(body.get("tagger")) is dict,
                "LEASE_API_BODY_INVALID")
        asof = body["tag"][len(TAG_PREFIX):]
        require(body["tag"] == epoch_tag(asof),
                "LEASE_API_BODY_INVALID")
        owner = json.loads(body["message"])
        require(type(owner) is dict and
                isinstance(owner.get("observed_at"), str) and
                owner["observed_at"].endswith("Z"),
                "LEASE_API_BODY_INVALID")
        observed = datetime.fromisoformat(
            owner["observed_at"].replace("Z", "+00:00"))
        require(observed.tzinfo is not None and
                observed.utcoffset() == timedelta(0) and
                body["message"] == _manifest(owner, now=observed) and
                body["tag"] == owner["tag"] and
                body["object"] == owner["source_sha"] and
                body["tagger"] == {
                    "name": "github-actions[bot]",
                    "email": "41898282+github-actions[bot]@users.noreply.github.com",
                    "date": owner["observed_at"],
                },
                "LEASE_API_BODY_INVALID")
        return True
    except (LeaseHold, ValueError, TypeError, KeyError,
            OverflowError, ImportError, AttributeError):
        raise LeaseHold("LEASE_API_BODY_INVALID") from None


def github_transport(token, *, opener=urlopen):
    """Optional authenticated transport. NEVER log token, URL or HTTP body."""
    require(isinstance(token,str) and bool(token),
            "LEASE_GITHUB_TOKEN_NOT_CONFIGURED")
    prefix="https://api.github.com/repos/"+REPO
    def call(method,path,body=None):
        # Restrict BOTH HTTP method and path. A generic /git/* POST is an
        # unauthorized mutation route, even if future code supplies it.
        allowed=(
            (method=="POST" and path in ("/git/tags","/git/refs"))
            or (method=="GET" and (
                path=="/rulesets"
                or re.fullmatch(r"/actions/runs/[1-9][0-9]*",path) is not None
                # Only the canonical EOD workflow's GET-only, fixed
                # RFC3339 UTC creation range; no whole-day bucket, broadened
                # event, pagination or dispatch route.
                or re.fullmatch(
                    r"/actions/workflows/xray-personal-477-eod[.]yml/runs[?]"
                    r"event=schedule&per_page=100&created="
                    r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T"
                    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z[.][.]"
                    r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T"
                    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z",
                    path) is not None
                or re.fullmatch(r"/rulesets/[1-9][0-9]*",path) is not None
                or re.fullmatch(
                    r"/git/ref/tags/xray-personal477-eod-epoch-"
                    r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",path) is not None
                or re.fullmatch(r"/git/tags/[0-9a-f]{40}",path) is not None
            ))
        )
        require(allowed,"LEASE_API_PATH_INVALID")
        if method == "POST":
            verify_scoped_git_write_body(path, body)
        else:
            require(body is None, "LEASE_API_BODY_INVALID")
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


def main(argv=None):
    """Read-only CI canary. This entry point NEVER creates tags or refs.

    The atomic claim function is intentionally NOT invoked from any CLI.
    A successful live protection GET is still NOT a race/producer receipt.
    """
    import os
    import sys

    args = sys.argv[1:] if argv is None else argv
    if args not in (["--verify-tag-protection"],["--probe-tag-protection"]):
        print(json.dumps({"status": "TAG_RULESET_READ_ONLY_HOLD",
                          "reason_code": "UNSUPPORTED_CLI_ACTION",
                          "writes": 0, "ab_release_authorized": False}))
        return 3
    if (os.environ.get("GITHUB_REPOSITORY") != REPO or
            not os.environ.get("GITHUB_TOKEN")):
        print(json.dumps({"status": "TAG_RULESET_READ_ONLY_HOLD",
                          "reason_code": "TAG_CANARY_IDENTITY_OR_TOKEN_MISSING",
                          "writes": 0, "ab_release_authorized": False}))
        return 3
    try:
        result=verify_live_tag_protection(
            github_transport(os.environ["GITHUB_TOKEN"]),
            probe_only=(args==["--probe-tag-protection"]))
    except Exception as exc:
        # Only audit-approved fixed categories may enter public logs.
        # Never expose HTTP body, exception message, URL or token.
        if isinstance(exc, HTTPError):
            status = exc.code if exc.code in (400, 401, 403, 404, 429) else 0
            reason = ("TAG_RULESET_HTTP_" + str(status)
                      if status else "TAG_RULESET_HTTP_OTHER")
        elif isinstance(exc, LeaseHold):
            # All subcodes are authored literals, never external strings.
            code=str(exc)
            kind=code.split(":",1)[1] if ":" in code else ""
            allowed=frozenset(("ACTIVE_TAG_NOT_VISIBLE",
                               "BYPASS_FIELD_UNAVAILABLE",
                               "BYPASS_ACTOR_PRESENT",
                               "EXACT_RULE_MISMATCH"))
            reason=("TAG_RULESET_"+kind if kind in allowed
                    else "TAG_RULESET_CONTRACT_NOT_MATCHED")
        elif isinstance(exc, URLError):
            reason = "TAG_RULESET_NETWORK_UNAVAILABLE"
        else:
            reason = "TAG_RULESET_READ_EXCEPTION"
        print(json.dumps({"status": "TAG_RULESET_READ_ONLY_HOLD",
                          "reason_code": reason,
                          "writes": 0, "ab_release_authorized": False}))
        return 3
    partial=result=="TAG_RULESET_PROJECTION_PASS_BYPASS_UNKNOWN"
    print(json.dumps({
        "status": ("TAG_RULESET_PROJECTION_PASS_BYPASS_UNKNOWN"
                   if partial else "TAG_RULESET_LIVE_GET_PASS"),
        "protected_pattern": PROTECTED_PATTERN,
        "bypass_verified": not partial,
        "writes": 0, "ab_release_authorized": False,
        "device_ack": "UNKNOWN",
    }))
    return 0


# IMPORTANT: Only the GET-only ruleset preflight has a CLI. The first-claim
# function has NO CLI, timer, Sheet or producer integration. A live immutable
# Git tag create-ref collision and independent consumer receipts are still
# necessary before any recovery can be enabled.
if __name__ == "__main__":
    raise SystemExit(main())

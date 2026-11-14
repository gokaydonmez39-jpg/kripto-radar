"""Stage one verified Official Witness commit using a scoped App token.

The caller supplies a token only to this step through the runner environment.
The token is never written to git config, argv, disk, or output. The fixed
remote and namespace are the only write destination. Never stage an old run.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import re
import subprocess

from xray406_witness_acceptance import check_candidate, require, utc
from xray406_witness_handoff import REPO, staging_ref

REMOTE = f"https://github.com/{REPO}.git"
BUDGET = timedelta(seconds=120)


class StageUnknown(RuntimeError):
    pass


@dataclass(frozen=True)
class StageReceipt:
    ref: str
    head: str
    already_staged: bool


def stage(root, base, candidate, cutoff: datetime, clock, transport):
    generated, _, _ = check_candidate(root, base, candidate)
    ref = staging_ref(candidate)
    deadline = min(utc(cutoff), generated + timedelta(minutes=15))
    now = utc(clock())
    require(generated <= now and now + BUDGET < deadline, "STAGING_WINDOW_CLOSED")
    require(transport.read("refs/heads/main") == base, "BASE_MOVED_NO_STAGE")
    existing = transport.read(ref)
    if existing is not None:
        require(existing == candidate, "STAGING_REF_ALREADY_OCCUPIED")
        return StageReceipt(ref, candidate, True)
    now = utc(clock())
    require(generated <= now and now + BUDGET < deadline, "STAGING_WINDOW_CLOSED")
    try:
        written = transport.create_only(root, ref, candidate)
        observed = transport.read(ref)
    except Exception as exc:
        raise StageUnknown("STAGING_OUTCOME_UNKNOWN_DO_NOT_RETRY") from exc
    if written is not True or observed != candidate:
        raise StageUnknown("STAGING_OUTCOME_UNKNOWN_DO_NOT_RETRY")
    return StageReceipt(ref, candidate, False)


class GitStageTransport:
    """Git remote writes are restricted to create-if-absent staging refs.

    With an App token the child process alone receives it via GH_TOKEN.
    Reset checkout authorization headers and other credential helpers.
    """
    def __init__(self, command=subprocess.run, app_token=None):
        self.command, self.app_token = command, app_token

    def invoke(self, args, *, timeout, write=False):
        env = os.environ.copy()
        for key in tuple(env):
            if key in {"GH_TOKEN", "GITHUB_TOKEN", "GIT_ASKPASS", "SSH_ASKPASS", "GH_DEBUG"} or key.startswith(("GIT_TRACE", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")) or key in {"GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_CURL_VERBOSE"}:
                env.pop(key)
        env.update(GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
        opts = ["-c", "http.extraHeader=", "-c", "credential.helper="]
        if write and self.app_token:
            env["GH_TOKEN"] = self.app_token
            opts += ["-c", "credential.helper=!gh auth git-credential"]
        return self.command(["git", *opts, *args], env=env,
                            capture_output=True, text=True, timeout=timeout, check=False)

    def read(self, ref):
        require(ref == "refs/heads/main" or re.fullmatch(
            r"refs/heads/xray-406-official-witness-staging/[0-9a-f]{40}", ref),
            "REF_OUT_OF_SCOPE")
        result = self.invoke(["ls-remote", "--exit-code", "--refs", REMOTE, ref], timeout=20)
        if result.returncode == 2:
            return None
        require(result.returncode == 0, "REF_READ_FAILED")
        sha, observed_ref = result.stdout.strip().split("\t")
        require(observed_ref == ref and re.fullmatch(r"[0-9a-f]{40}", sha), "BAD_REF_READBACK")
        return sha

    def create_only(self, root, ref, candidate):
        require(ref == staging_ref(candidate), "REF_OUT_OF_SCOPE")
        result = self.invoke(["-C", str(root), "-c", "core.hooksPath=/dev/null", "push", "--porcelain",
                              "--no-follow-tags", "--force-with-lease=" + ref + ":",
                              REMOTE, candidate + ":" + ref], timeout=35, write=True)
        return result.returncode == 0

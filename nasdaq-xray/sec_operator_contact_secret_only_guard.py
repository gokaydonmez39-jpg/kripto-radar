#!/usr/bin/env python3
"""Reject GitHub Actions plaintext SEC operator-contact variable exposures.

Never reads, prints, handles or calls the operator's actual contact value.
GitHub repository variables are not secret-masked in public Actions logs.
Only encrypted GitHub Secret is eligible for the SEC User-Agent environment.
This cannot create SEC access, vendor rights, identity PASS, MC, or R92.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SECRET_LINE = re.compile(r"^\s*XRAY_SEC_USER_AGENT\s*:\s*\$\{\{\s*secrets\.XRAY_SEC_USER_AGENT\s*\}\}\s*$")
CONTACT_LINE = re.compile(r"^\s*XRAY_SEC_USER_AGENT\s*:")
PLAINTEXT_VAR = "vars.XRAY_SEC_USER_AGENT"
# A masking command AFTER an env var has been rendered in Actions job logs
# does not undo an earlier plaintext exposure. Therefore no vars fallback.
DANGEROUS_ECHO = re.compile(
    r"(?i)(?:echo|printf|printenv|set\s+-x).{0,120}(?:\$\{?XRAY_SEC_USER_AGENT\}?|env\.XRAY_SEC_USER_AGENT)"
)

def errors(path: str, content: str) -> list[str]:
    found = []
    if PLAINTEXT_VAR in content:
        found.append("PLAIN_TEXT_REPOSITORY_VAR_FALLBACK")
    for n, line in enumerate(content.splitlines(), 1):
        if CONTACT_LINE.match(line) and SECRET_LINE.fullmatch(line) is None:
            found.append("NON_SECRET_OPERATOR_ENV_LINE_" + str(n))
        if DANGEROUS_ECHO.search(line):
            found.append("CONTACT_ECHO_OR_SHELL_TRACE_LINE_" + str(n))
    return found

def scan() -> list[tuple[str, list[str]]]:
    if not WORKFLOWS.is_dir():
        raise RuntimeError("XRAY_GITHUB_WORKFLOWS_MISSING")
    out = []
    workflows = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if len(workflows) < 10:
        raise RuntimeError("XRAY_WORKFLOW_SCOPE_TOO_SMALL")
    for p in workflows:
        bad = errors(p.name,p.read_text(encoding="utf-8"))
        if bad:
            out.append((p.name,bad))
    return out

def selftest():
    good = "      XRAY_SEC_USER_AGENT: ${{ secrets.XRAY_SEC_USER_AGENT }}\n"
    assert errors("ok.yml",good)==[]
    cases = [
      ("repo_var", "      XRAY_SEC_USER_AGENT: ${{ secrets.XRAY_SEC_USER_AGENT || vars.XRAY_SEC_USER_AGENT }}\n"),
      ("plain_var", "      XRAY_SEC_USER_AGENT: ${{ vars.XRAY_SEC_USER_AGENT }}\n"),
      ("literal_contact", "      XRAY_SEC_USER_AGENT: contact-string-at-domain\n"),
      ("echo", "run: echo \"$XRAY_SEC_USER_AGENT\"\n"),
      ("shell_trace", "run: set -x; echo $XRAY_SEC_USER_AGENT\n"),
    ]
    for label,body in cases:
        assert errors(label+".yml",body),label
    print("XRAY_SEC_CONTACT_SECRET_GUARD_SELFTEST=PASS_FIVE_NEGATIVES_NO_VALUE_EVER_READ")

def main():
    x=argparse.ArgumentParser()
    x.add_argument("--selftest",action="store_true")
    opt=x.parse_args()
    if opt.selftest:
        selftest()
        return
    bad=scan()
    if bad:
        for name,reasons in bad:
            print("XRAY_SEC_CONTACT_RISK_PATH="+name+" reason="+",".join(reasons))
        raise SystemExit("XRAY_PUBLIC_OPERATOR_CONTACT_PLAINTEXT_ENV=FAIL_CLOSED")
    print("XRAY_PUBLIC_OPERATOR_CONTACT_PLAINTEXT_ENV=PASS_ALL_WORKFLOWS_SECRET_ONLY_NO_USER_VALUE_READ")
if __name__=="__main__":
    main()

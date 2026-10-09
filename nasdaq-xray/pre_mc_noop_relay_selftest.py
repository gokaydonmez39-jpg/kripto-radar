#!/usr/bin/env python3
"""Regression: a healthy frozen Pre-MC no-op must not redeliver Post-MC.
Post-MC also has a scheduled fallback and push triggers on real authority
changes; a no-op dispatch caused repeat identical SOURCE_MC_REQUIRED failures.
No alpha/market-data/notification authority changes.
"""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parent
WF=(ROOT.parent/".github/workflows/xray-canonical-current-pre-mc.yml").read_text()

def selftest():
    assert re.search(r"- name: Commit current pre-MC artifacts\n\s+id: precommit\n",WF), "MISSING_COMMIT_OUTPUT_ID"
    nochange=re.search(r'if git diff --cached --quiet; then\n(.{0,200}?)\n\s+exit 0',WF,re.S)
    assert nochange and 'changed=false' in nochange.group(1), "NOOP_NOT_RECORDED"
    success=re.search(r'if git push origin HEAD:main; then\n(.{0,200}?)\n\s+exit 0',WF,re.S)
    assert success and 'changed=true' in success.group(1), "PROVEN_PERSISTENCE_NOT_RECORDED"
    step=re.search(r"- name: Atomically wake Post-MC from exact current Pre-MC sources\n\s+if: ([^\n]+)",WF)
    assert step and "steps.precommit.outputs.changed == 'true'" in step.group(1), "REDUNDANT_NOOP_POSTMC_REDISPATCH"
    assert "if: success()" not in (step.group(0) if step else ""), "OLD_ALWAYS_ON_RELAY_STILL_PRESENT"
    assert 'cron: "50 * * * 1-5"' in (
        ROOT.parent/".github/workflows/xray-canonical-current-post-mc.yml").read_text(), "POSTMC_FALLBACK_MISSING"
    print("XRAY_PREMC_NOOP_RELAY=PASS_NO_REPEAT_MC_FAILURE_STORM_RELAY_ONLY_ON_REAL_COMMIT")

if __name__=="__main__":selftest()

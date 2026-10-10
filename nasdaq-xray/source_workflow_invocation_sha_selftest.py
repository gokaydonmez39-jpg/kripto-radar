#!/usr/bin/env python3
"""GitHub Actions attestation: checkout must equal the immutable invoking SHA.

Static gate prevents a queued run silently validating a later moving main.
Never grants source rights, candidate, order or canonical GO.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
TARGETS=(
 ".github/workflows/xray-alpaca-free-sip-shadow-proof.yml",
 ".github/workflows/xray-c418-source-successor-preflight.yml",
)

def main():
    for item in TARGETS:
        s=(ROOT/item).read_text(encoding="utf-8")
        assert "uses: actions/checkout@v4" in s,("CHECKOUT_MISSING",item)
        assert "ref: main" not in s,("CHECKOUT_UNPINNED_MOVING_MAIN",item)
        assert "ref: ${{ github.sha }}" in s,("CHECKOUT_NOT_PINNED_TO_TRIGGER",item)
        assert 'run: test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in s,(
            "CHECKOUT_SHA_NOT_COMPARED_TO_INVOCATION",item)
        assert "workflow_dispatch:" in s
    print("XRAY_SOURCE_WORKFLOW_INVOCATION_SHA=PASS_NO_CROSS_COMMIT_ATTESTATION")

if __name__=="__main__":
    main()

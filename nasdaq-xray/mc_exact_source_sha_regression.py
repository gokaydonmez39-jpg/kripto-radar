#!/usr/bin/env python3
"""Enforce immutable exact price Git blob provenance in terminal MC selection."""
from pathlib import Path

source=(Path(__file__).resolve().parent/"build_current_terminal.py").read_text()
start=source.index("def find_mc(")
end=source.index("\ndef main():",start)
selector=source[start:end]
assert "if len(exact)!=1:" in selector, "EXACT_PRICE_BLOB_SELECTOR_GUARD_MISSING"
assert "raise RuntimeError" in selector, "NO_FAIL_CLOSED_ON_MISSING_EXACT_PRICE"
assert "return semantic[0]" not in selector, "MC_SEMANTIC_REBIND_BYPASSES_SOURCE_SHA"
print("XRAY_MC_EXACT_PRICE_SOURCE_SHA=PASS")

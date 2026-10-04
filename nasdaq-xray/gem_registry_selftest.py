#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=ROOT/"gem_integration_registry.json"
j=json.loads(p.read_text())
assert j["schema"]=="XRAY_GEM_INTEGRATION_REGISTRY_V1"
assert j["execution"]=="NONE" and j["real_money"]=="NO-GO"
assert j["unknown_never_pass"] is True
g=j["gems"]; assert len(g)==j["expected_gem_count"]==36
ids=[x["id"] for x in g]; assert ids==list(range(1,37)),ids
assert len({x["name"] for x in g})==36
for x in g:
    assert x["tier"]
    assert isinstance(x["runtime_paths"],list) and x["runtime_paths"]
    if x["tier"].startswith(("SHADOW","RESEARCH","BLOCKED","DISCOVERY","POSTMORTEM","PROVENANCE","ENTITLEMENT","NONCANONICAL")):
        assert x["cutover"] is False,(x["id"],x["tier"])
# Explicitly preserve the two final hard blockers.
assert next(x for x in g if x["id"]==15)["cutover"] is False
assert next(x for x in g if x["id"]==32)["cutover"] is False
print("XRAY_GEM_REGISTRY_SELFTEST=PASS count=36")

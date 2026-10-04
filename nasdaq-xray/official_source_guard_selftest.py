#!/usr/bin/env python3
from official_source_guard import derive_security_suspensions

def row(d,s,e):
    return {"EffectiveDate":d,"Symbol":s,"IssueEvent":e}

s,e=derive_security_suspensions([row("2026-10-02","AAA","Issue Suspensions")])
assert s==["AAA"] and e["AAA"]["latest_suspension"]=="2026-10-02"

s,_=derive_security_suspensions([
    row("2026-10-02","AAA","Issue Suspensions"),
    row("2026-10-03","AAA","Security Additions"),
])
assert "AAA" not in s

s,_=derive_security_suspensions([
    row("2026-10-02","AAA","Security Additions"),
    row("2026-10-02","AAA","Issue Suspensions"),
])
assert "AAA" in s

s,_=derive_security_suspensions([
    row("2026-10-02","AAA","Issue Suspensions"),
    row("2026-10-03","AAA","Anticipated Security Additions"),
])
assert "AAA" in s

s,_=derive_security_suspensions([
    row("2026-10-02","AAA","Security Additions"),
    row("2026-10-03","AAA","Issue Suspensions"),
])
assert "AAA" in s

s,_=derive_security_suspensions([
    row("2026-10-02","AAA","Issue Suspensions"),
    row("2026-10-03","AAA","Security Additions"),
    row("2026-10-04","AAA","Issue Suspensions"),
    row("2026-10-02","BBB","Issue Suspensions"),
    row("2026-10-05","BBB","Security Additions"),
])
assert s==["AAA"],s
print("XRAY_OFFICIAL_SECURITY_STATUS_STATE_SELFTEST=PASS")

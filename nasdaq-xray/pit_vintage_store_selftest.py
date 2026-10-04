#!/usr/bin/env python3
from __future__ import annotations
import tempfile
from pathlib import Path
from pit_vintage_store import append_vintage, latest_visible, visible_vintages

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    p1=append_vintage(root,"SEC_COMPANYFACTS","CIK1","2026-01-01T12:00:00Z","SEC",{"shares":100},{"accession":"A"})
    p1b=append_vintage(root,"SEC_COMPANYFACTS","CIK1","2026-01-01T12:00:00Z","SEC",{"shares":100},{"accession":"A"})
    assert p1==p1b
    append_vintage(root,"SEC_COMPANYFACTS","CIK1","2026-02-01T12:00:00Z","SEC",{"shares":110},{"accession":"B"})
    assert len(visible_vintages(root,"SEC_COMPANYFACTS","CIK1","2026-01-15T00:00:00Z"))==1
    assert latest_visible(root,"SEC_COMPANYFACTS","CIK1","2026-01-15T00:00:00Z")["payload"]["shares"]==100
    assert latest_visible(root,"SEC_COMPANYFACTS","CIK1","2026-02-15T00:00:00Z")["payload"]["shares"]==110
print("XRAY_PIT_VINTAGE_STORE_SELFTEST=PASS")

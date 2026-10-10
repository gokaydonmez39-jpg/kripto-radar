#!/usr/bin/env python3
"""Fail-closed paging for Alpaca historical multi-stock SIP SHADOW research.

A successful first page is not evidence of a complete symbol cohort.
Alpaca sorts first by symbol then time and caps limit ACROSS all symbols.
All raw rows stay inside the caller's process and are never printed or
persisted by this helper. Provider entitlement and C4.17 PRIMARY authority
are NOT inferred by successful transport.
"""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
import re

MAX_PAGES = 24
MAX_ROWS_PER_SYMBOL = 450
MAX_CURSOR_CHARS = 2048
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,12}$")


def collect_pages(symbols: list[str], get_page, *, max_pages: int = MAX_PAGES):
    """get_page(token_or_None)->dict; reject incomplete, looping or altered scope."""
    if (not isinstance(symbols,list) or not 1 <= len(symbols) <= 32
            or not all(isinstance(s,str) and SYMBOL_RE.fullmatch(s) for s in symbols)
            or len(set(symbols)) != len(symbols)):
        raise RuntimeError("ALPACA_PAGE_SCOPE_INVALID")
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES:
        raise RuntimeError("ALPACA_PAGE_BUDGET_INVALID")

    rows: dict[str,list[dict]] = {s:[] for s in symbols}
    observed: dict[str,set[str]] = {s:set() for s in symbols}
    used_tokens: set[str] = set()
    next_token = None

    for page_idx in range(max_pages):
        data = get_page(next_token)
        if not isinstance(data,dict) or not isinstance(data.get("bars"),dict):
            raise RuntimeError("ALPACA_PAGE_JSON_SCHEMA_INVALID")
        part = data["bars"]
        if any(s not in rows for s in part):
            raise RuntimeError("ALPACA_PAGE_FOREIGN_SYMBOL")
        page_count = 0
        for sym, batch in part.items():
            if not isinstance(batch,list):
                raise RuntimeError("ALPACA_PAGE_SYMBOL_BARS_INVALID")
            for item in batch:
                if not isinstance(item,dict) or not isinstance(item.get("t"),str):
                    raise RuntimeError("ALPACA_PAGE_BAD_TIMESTAMP")
                stamp=item["t"]
                if not stamp or stamp in observed[sym]:
                    raise RuntimeError("ALPACA_PAGE_DUPLICATE_TIMESTAMP")
                observed[sym].add(stamp)
                rows[sym].append(item)
                page_count+=1
                if len(rows[sym])>MAX_ROWS_PER_SYMBOL:
                    raise RuntimeError("ALPACA_PAGE_SYMBOL_ROW_BUDGET")
        token=data.get("next_page_token")
        if token is None:
            return rows
        if (not isinstance(token,str) or not token
                or len(token)>MAX_CURSOR_CHARS
                or any(ord(c)<33 or ord(c)>126 for c in token)):
            raise RuntimeError("ALPACA_PAGE_CURSOR_INVALID")
        if token in used_tokens:
            raise RuntimeError("ALPACA_PAGE_CURSOR_LOOP")
        if page_count == 0:
            raise RuntimeError("ALPACA_PAGE_NO_PROGRESS")
        used_tokens.add(token)
        next_token=token
    raise RuntimeError("ALPACA_PAGE_BUDGET_EXHAUSTED_NEVER_PARTIAL_PASS")


def selftest() -> None:
    a={"t":"2026-10-08T04:00:00Z","o":10,"h":11,"l":9,"c":10.5,"v":100}
    b={"t":"2026-10-09T04:00:00Z","o":12,"h":13,"l":11,"c":12.5,"v":200}
    c={"t":"2026-10-09T04:00:00Z","o":14,"h":15,"l":13,"c":14.5,"v":300}
    good=[
        {"bars":{"AAA":[a,b]},"next_page_token":"next=="},
        {"bars":{"BBB":[c]},"next_page_token":None},
    ]
    called=[]
    def fetched(tok):
        called.append(tok)
        return deepcopy(good[len(called)-1])
    out=collect_pages(["AAA","BBB"],fetched)
    assert called==[None,"next=="],called
    assert len(out["AAA"])==2 and len(out["BBB"])==1
    assert out["BBB"][0]["v"]==300
    # "one page" cannot be interpreted as all symbols when a cursor is present
    try:
        collect_pages(["AAA","BBB"],lambda tok:good[0],max_pages=1)
    except RuntimeError as e:
        assert "BUDGET_EXHAUSTED" in str(e)
    else:
        raise AssertionError("PARTIAL_MULTI_SYMBOL_PAGE_WAS_ACCEPTED")

    bads=[
        ("FOREIGN", [{"bars":{"ZZZ":[a]},"next_page_token":None}], "FOREIGN_SYMBOL"),
        ("MALFORMED", [{"bars":[],"next_page_token":None}], "JSON_SCHEMA"),
        ("DUPLICATE", [{"bars":{"AAA":[a,a]},"next_page_token":None}], "DUPLICATE_TIMESTAMP"),
        ("DUPLICATE_ACROSS", [
            {"bars":{"AAA":[a]},"next_page_token":"p"},
            {"bars":{"AAA":[a]},"next_page_token":None}], "DUPLICATE_TIMESTAMP"),
        ("LOOP", [
            {"bars":{"AAA":[a]},"next_page_token":"p"},
            {"bars":{"BBB":[b]},"next_page_token":"p"}], "CURSOR_LOOP"),
        ("NO_PROGRESS", [
            {"bars":{"AAA":[a]},"next_page_token":"p"},
            {"bars":{},"next_page_token":"q"}], "NO_PROGRESS"),
        ("CURSOR_POISON", [
            {"bars":{"AAA":[a]},"next_page_token":"p\nkey"}], "CURSOR_INVALID"),
        ("NO_TIMESTAMP", [
            {"bars":{"AAA":[{"o":10}]},"next_page_token":None}], "BAD_TIMESTAMP"),
        ("UNBOUNDED", [
            {"bars":{"AAA":[dict(a,t=f"2026-10-{x:04d}T04:00:00Z") for x in range(451)]},
             "next_page_token":None}], "SYMBOL_ROW_BUDGET"),
    ]
    for name,arr,expected in bads:
        pointer=[0]
        def f(tok):
            ix=pointer[0]
            pointer[0]+=1
            return deepcopy(arr[min(ix,len(arr)-1)])
        try:collect_pages(["AAA","BBB"],f)
        except RuntimeError as exc:
            assert expected in str(exc),(name,str(exc))
        else:raise AssertionError(name)
    for scope in ([],["AAA","AAA"],["AAA","../KEY"],list(range(5)),["AAA"]*33):
        try:collect_pages(scope,lambda _:good[0])
        except RuntimeError:pass
        else:raise AssertionError("INVALID_SYMBOL_SCOPE_ACCEPTED")
    print("XRAY_ALPACA_SIP_PAGINATION_SELFTEST=PASS_TWO_PAGES_NINE_NEGATIVE_FIVE_SCOPE_NEGATIVE_NO_VENDOR")


if __name__=="__main__":
    selftest()

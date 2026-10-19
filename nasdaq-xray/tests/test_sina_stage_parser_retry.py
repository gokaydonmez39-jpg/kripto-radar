"""Sina source failures: parser/schema and definitive HTTP are not retryable.

Exercise the actual parse_hist function AST with a no-network provider double.
No akshare installation, vendor requests, OHLCV, cash, orders, or AL.
"""
import ast
import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import urllib.error

SOURCE=Path(__file__).resolve().parents[1]/"sina_stage.py"


def load_actual_parse_hist():
    tree=ast.parse(SOURCE.read_text(encoding="utf-8"),filename=str(SOURCE))
    function=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
                  and x.name=="parse_hist")
    only=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
    scope={"HARD_PRICE":5.0,"HARD_HISTORY":260,
           "HARD_DV30":50_000_000.0,"math":math,"json":json,
           "urllib":__import__("urllib")}
    exec(compile(only,str(SOURCE),"exec"),scope)
    return scope["parse_hist"],scope


class SinaNontransientRetry(TestCase):
    def classify(self, error):
        parser,scope=load_actual_parse_hist()
        def fail(**kwargs):
            raise error
        scope["ak"]=SimpleNamespace(stock_us_daily=fail)
        guard=ModuleType("official_first_trade_260_history_guard")
        guard.fence=lambda *args:None
        with patch.dict(sys.modules,{guard.__name__:guard}):
            return parser("ACFN","2026-10-16",["2026-10-16"])

    def test_real_syntax_error_no_same_epoch_retry(self):
        status,info=self.classify(SyntaxError("invalid syntax"))
        self.assertEqual(status,"UNKNOWN_STATIC")
        self.assertEqual(info["reason"],"SINA_SOURCE_SCHEMA_NONRETRYABLE")
        self.assertEqual(info["exception_type"],"SyntaxError")
        self.assertIs(info["retryable_in_same_epoch"],False)

    def test_index_error_no_same_epoch_retry(self):
        status,info=self.classify(IndexError("list index out of range"))
        self.assertEqual(status,"UNKNOWN_STATIC")
        self.assertEqual(info["exception_type"],"IndexError")

    def test_key_error_no_same_epoch_retry(self):
        status,info=self.classify(KeyError("date"))
        self.assertEqual(status,"UNKNOWN_STATIC")
        self.assertEqual(info["exception_type"],"KeyError")

    def test_type_error_no_same_epoch_retry(self):
        status,info=self.classify(TypeError("unexpected field"))
        self.assertEqual(status,"UNKNOWN_STATIC")
        self.assertEqual(info["exception_type"],"TypeError")

    def test_http403_is_nonretryable(self):
        exc=urllib.error.HTTPError("https://example.invalid",403,
                                  "Forbidden",hdrs=None,fp=None)
        status,info=self.classify(exc)
        self.assertEqual(status,"UNKNOWN_STATIC")
        self.assertEqual(info["reason"],"SINA_SOURCE_HTTP_NONRETRYABLE")
        self.assertEqual(info["http_status"],403)

    def test_http429_remains_bounded_retry(self):
        exc=urllib.error.HTTPError("https://example.invalid",429,
                                  "Rate Limit",hdrs=None,fp=None)
        status,info=self.classify(exc)
        self.assertEqual(status,"UNKNOWN_RETRY")

    def test_all_nontransient_http_4xx_are_quarantined(self):
        for code in (402, 405, 406, 409, 418, 423, 426, 428, 431, 451):
            with self.subTest(code=code):
                exc=urllib.error.HTTPError("https://example.invalid",code,
                                          "Definitive",hdrs=None,fp=None)
                status,info=self.classify(exc)
                self.assertEqual(status,"UNKNOWN_STATIC")
                self.assertEqual(info["reason"],"SINA_SOURCE_HTTP_NONRETRYABLE")
                self.assertEqual(info["http_status"],code)

    def test_retryable_http_statuses_are_exact(self):
        for code in (408, 425, 429, 500, 503):
            with self.subTest(code=code):
                exc=urllib.error.HTTPError("https://example.invalid",code,
                                          "Transient",hdrs=None,fp=None)
                self.assertEqual(self.classify(exc)[0],"UNKNOWN_RETRY")

    def test_transport_timeout_remains_bounded_retry(self):
        status,info=self.classify(TimeoutError("timed out"))
        self.assertEqual(status,"UNKNOWN_RETRY")

    def test_empty_provider_response_remains_unknown_static(self):
        parser,scope=load_actual_parse_hist()
        scope["ak"]=SimpleNamespace(stock_us_daily=lambda **kw:None)
        guard=ModuleType("official_first_trade_260_history_guard")
        guard.fence=lambda *args:None
        with patch.dict(sys.modules,{guard.__name__:guard}):
            status,info=parser("ACFN","2026-10-16",["2026-10-16"])
        self.assertEqual(status,"UNKNOWN_STATIC")
        self.assertEqual(info,"SINA_HISTORY_EMPTY")


if __name__=="__main__":
    import unittest
    unittest.main()

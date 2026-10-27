import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from nasdaq_edgar_pit_header_gate import validated_header_asof,FilingBlocked

NY=ZoneInfo("America/New_York")
def demo_header(accept="20261027153000",cik="0000999999",form="8-K"):
    # Completely synthetic SEC-style index header; no company-specific data.
    return (
    "<html><head><title>synthetic SEC header</title><!--\n"
    "<SEC-HEADER>0000999999-26-000001.hdr.sgml : 20261027\n"
    "<ACCEPTANCE-DATETIME>"+accept+"\n"
    "<ACCESSION-NUMBER>0000999999-26-000001\n"
    "<TYPE>"+form+"\n"
    "<PUBLIC-DOCUMENT-COUNT>1\n"
    "<PERIOD>20261027\n"
    "<ITEMS>8.01\n"
    "<FILING-DATE>20261027\n"
    "<FILER>\n<COMPANY-DATA>\n"
    "<CONFORMED-NAME>Example NASDAQ Fictional Corporation\n"
    "<CIK>"+cik+"\n"
    "</COMPANY-DATA>\n"
    "<FILING-VALUES>\n<FORM-TYPE>"+form+"\n"
    "<ACT>34\n<FILE-NUMBER>001-11111\n"
    "<FILM-NUMBER>261111111\n</FILING-VALUES>\n"
    "<BUSINESS-ADDRESS>\n<STREET1>1 Fictional Street\n"
    "<CITY>Example\n<STATE>NY\n<ZIP>10001\n</BUSINESS-ADDRESS>\n"
    "<MAIL-ADDRESS>\n<STREET1>1 Fictional Street\n"
    "<CITY>Example\n<STATE>NY\n<ZIP>10001\n</MAIL-ADDRESS>\n"
    "</FILER>\n</SEC-HEADER>\n--></head><body></body></html>"
    )
class TestEdgarPointInTimeGate(unittest.TestCase):
    def setUp(self):
        self.close=datetime(2026,10,27,16,0,tzinfo=NY)
    def test_accepted_before_close_is_known(self):
        result=validated_header_asof(demo_header(),"0000999999",self.close)
        self.assertEqual(result["cik"],"0000999999")
        self.assertEqual(result["form"],"8-K")
        self.assertIn("15:30:00",result["accepted_at_et"])
    def test_next_morning_filing_not_known_previous_close(self):
        with self.assertRaisesRegex(FilingBlocked,"LOOKAHEAD"):
            validated_header_asof(demo_header("20261028091200"),"0000999999",self.close)
    def test_after_close_same_day_not_known(self):
        with self.assertRaisesRegex(FilingBlocked,"LOOKAHEAD"):
            validated_header_asof(demo_header("20261027160300"),"0000999999",self.close)
    def test_wrong_cik_rejected(self):
        with self.assertRaisesRegex(FilingBlocked,"ISSUER_CIK"):
            validated_header_asof(demo_header(cik="0000123456"),"0000999999",self.close)
    def test_no_local_naive_close(self):
        with self.assertRaisesRegex(FilingBlocked,"TZ_AWARE"):
            validated_header_asof(demo_header(),"0000999999",datetime(2026,10,27,16,0))
    def test_unknown_form_rejected(self):
        with self.assertRaisesRegex(FilingBlocked,"UNSUPPORTED_FORM"):
            validated_header_asof(demo_header(form="S-3"),"0000999999",self.close)
if __name__=="__main__":unittest.main()

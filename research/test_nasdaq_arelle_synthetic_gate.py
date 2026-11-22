"""Fictional XBRL fixture + adversarial PIT and Arelle tests; never production."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nasdaq_arelle_synthetic_gate import (
    ShadowGateBlocked, examine_fictional_xbrl, arelle_offline_probe
)

NY = ZoneInfo("America/New_York")
TAXONOMY = """<?xml version="1.0" encoding="utf-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns:xbrli="http://www.xbrl.org/2003/instance"
  targetNamespace="https://example.invalid/xray-nasdaq-synthetic"
  xmlns:ex="https://example.invalid/xray-nasdaq-synthetic" elementFormDefault="qualified">
  <xs:import namespace="http://www.xbrl.org/2003/instance"
    schemaLocation="http://www.xbrl.org/2003/xbrl-instance-2003-12-31.xsd"/>
  <xs:element name="SyntheticCash" id="ex_SyntheticCash" type="xbrli:monetaryItemType"
      substitutionGroup="xbrli:item" xbrli:periodType="instant"/>
</xs:schema>"""
INSTANCE = """<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:link="http://www.xbrl.org/2003/linkbase"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
  xmlns:ex="https://example.invalid/xray-nasdaq-synthetic">
  <link:schemaRef xlink:type="simple" xlink:href="synthetic_taxonomy.xsd"/>
  <xbrli:context id="ctx1">
    <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000999999</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-10-27</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
  <ex:SyntheticCash contextRef="ctx1" unitRef="usd" decimals="0">1000</ex:SyntheticCash>
</xbrli:xbrl>"""

class TestArelleSyntheticShadow(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = Path(self.temp.name)
        (p / "synthetic_taxonomy.xsd").write_text(TAXONOMY, encoding="utf-8")
        self.instance = p / "synthetic_instance.xbrl"
        self.instance.write_text(INSTANCE, encoding="utf-8")
        self.close = datetime(2026, 10, 27, 16, tzinfo=NY)
        self.accepted = datetime(2026, 10, 27, 15, 30, tzinfo=NY)

    def check(self, xml=INSTANCE, **kwargs):
        self.instance.write_text(xml, encoding="utf-8")
        options = dict(path=self.instance, cik="0000999999",
                       accepted_et=self.accepted, asof_et=self.close)
        options.update(kwargs)
        return examine_fictional_xbrl(**options)

    def test_valid_fictional_pit_preflight(self):
        result = self.check()
        self.assertEqual(result["amount"], "1000")
        self.assertEqual(result["cik"], "0000999999")

    def test_after_close_lookahead_rejected(self):
        with self.assertRaisesRegex(ShadowGateBlocked, "LOOKAHEAD"):
            self.check(accepted_et=datetime(2026, 10, 27, 16, 1, tzinfo=NY))

    def test_wrong_issuer_rejected(self):
        with self.assertRaisesRegex(ShadowGateBlocked, "ISSUER_CIK"):
            self.check(INSTANCE.replace("0000999999", "0000000001"))

    def test_remote_taxonomy_rejected(self):
        with self.assertRaisesRegex(ShadowGateBlocked, "LOCAL_TAXONOMY"):
            self.check(INSTANCE.replace("synthetic_taxonomy.xsd", "https://evil.example/taxonomy.xsd"))

    def test_xml_entity_rejected(self):
        with self.assertRaisesRegex(ShadowGateBlocked, "XML_ENTITY"):
            self.check(INSTANCE.replace("<xbrli:xbrl",
                '<!DOCTYPE xbrli:xbrl [<!ENTITY test "x">]><xbrli:xbrl', 1))

    def test_nan_rejected(self):
        with self.assertRaisesRegex(ShadowGateBlocked, "NONFINITE"):
            self.check(INSTANCE.replace(">1000<", ">NaN<"))

    def test_duplicate_context_rejected(self):
        a = INSTANCE.index('  <xbrli:context id="ctx1">')
        b = INSTANCE.index('  <xbrli:unit id="usd">')
        with self.assertRaisesRegex(ShadowGateBlocked, "CONTEXT_UNIQUE"):
            self.check(INSTANCE[:b] + INSTANCE[a:b] + INSTANCE[b:])

    def test_naive_datetime_rejected(self):
        with self.assertRaisesRegex(ShadowGateBlocked, "TZ_AWARE"):
            self.check(asof_et=datetime(2026, 10, 27, 16))

    def test_arelle_independently_loads_one_fact(self):
        self.check()
        self.assertEqual(arelle_offline_probe(self.instance), 1)

if __name__ == "__main__":
    unittest.main()

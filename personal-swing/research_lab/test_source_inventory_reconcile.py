"""Synthetic-only source catalogue tests. No network, secrets or vendor bars."""
import unittest
import source_inventory_reconcile as mod


def catalog():
    return {"schema": "XRAY_RESEARCH_UNIFIED_88_V1", "entries": [
        dict({"key": f"src-{i}", "url": f"https://github.com/example/project{i}"},
             **{field: False for field in mod.FIELDS}) for i in range(88)
    ]}


def archive():
    return [
        {"ID": "RT-001", "Kaynak_depo": "https://github.com/EXAMPLE/project0.git",
         "Oncelik": "P0", "Kabul_durumu": "RESEARCH_ONLY", "Paylasim_id_utc": ""},
        {"ID": "RT-002", "Kaynak_depo": "https://different.example/source",
         "Oncelik": "P1", "Kabul_durumu": "NOT_INTEGRATED", "Paylasim_id_utc": ""},
        {"ID": "RT-003", "Kaynak_depo": "",
         "Oncelik": "HOLD", "Kabul_durumu": "HOLD", "Paylasim_id_utc": ""},
    ]


class ReconcileTest(unittest.TestCase):
    def blocked(self, action, code):
        with self.assertRaisesRegex(mod.ReconciliationBlocked, code):
            action()

    def test_registry_only_never_claims_union_or_acceptance(self):
        r = mod.reconcile(catalog(), None)
        self.assertEqual(r["github_registry_entries"], 88)
        self.assertEqual(r["archive_status"], "NOT_SUPPLIED_UNKNOWN")
        self.assertIsNone(r["catalogue_union_total"])
        self.assertFalse(r["may_promote_sources"])

    def test_archive_exact_url_distinct_only(self):
        r = mod.reconcile(catalog(), archive())
        self.assertEqual(r["archive_records"], 3)
        self.assertEqual(r["exact_url_matches"], 1)
        self.assertEqual(r["unmatched_archive_rows_not_claimed_unique"], 2)
        self.assertEqual(r["archive_priorities"], {"HOLD": 1, "P0": 1, "P1": 1})
        self.assertEqual(r["archive_missing_urls"], 1)
        self.assertIsNone(r["catalogue_union_total"])

    def test_duplicate_rt_rejected(self):
        rows = archive()
        rows[2]["ID"] = "RT-001"
        self.blocked(lambda: mod.reconcile(catalog(), rows), "DUPLICATE_RT_ID")

    def test_gap_rt_rejected(self):
        rows = archive()
        rows[1]["ID"] = "RT-004"
        self.blocked(lambda: mod.reconcile(catalog(), rows), "RT_ID_GAP")

    def test_privileges_rejected(self):
        d = catalog()
        d["entries"][0]["may_issue_al"] = True
        self.blocked(lambda: mod.reconcile(d, None), "UNAUTHORIZED_RESEARCH_PRODUCTION_PERMISSION")

    def test_missing_permission_flag_rejected(self):
        d = catalog()
        d["entries"][0].pop("may_place_order")
        self.blocked(lambda: mod.reconcile(d, None), "UNAUTHORIZED_RESEARCH_PRODUCTION_PERMISSION")

    def test_duplicate_registry_key_rejected(self):
        d = catalog()
        d["entries"][1]["key"] = d["entries"][0]["key"]
        self.blocked(lambda: mod.reconcile(d, None), "DUPLICATE_REGISTRY_KEY")

    def test_wrong_count_rejected(self):
        d = catalog()
        d["entries"].pop()
        self.blocked(lambda: mod.reconcile(d, None), "EXPECTED_88")

    def test_invalid_archive_priority_rejected(self):
        rows = archive()
        rows[1]["Oncelik"] = "P5"
        self.blocked(lambda: mod.reconcile(catalog(), rows), "UNKNOWN_ARCHIVE_PRIORITY")

    def test_credential_url_rejected(self):
        rows = archive()
        rows[0]["Kaynak_depo"] = "https://token@example.com/repo"
        self.blocked(lambda: mod.reconcile(catalog(), rows), "CREDENTIALS_IN_URL")

    def test_archive_status_required(self):
        rows = archive()
        rows[0]["Kabul_durumu"] = " "
        self.blocked(lambda: mod.reconcile(catalog(), rows), "MISSING_ARCHIVE_STATUS")

    def test_url_case_trailing_git_normalized(self):
        self.assertEqual(mod.canonical_url("HTTPS://GITHUB.com/Some/Repo.GIT/?a=1"),
                         "https://github.com/some/repo")


if __name__ == "__main__":
    unittest.main()

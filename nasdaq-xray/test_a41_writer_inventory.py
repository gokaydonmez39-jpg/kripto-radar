"""Offline, no-network positive and negative regression for A41 writer screening."""
import json
from pathlib import Path
import tempfile
import unittest

import a41_writer_inventory as a


class A41InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / ".github" / "workflows"
        self.folder.mkdir(parents=True)

    def add(self, filename, source):
        dest = self.folder / filename
        dest.write_text(source, encoding="utf-8")
        return dest

    def test_read_only_workflow_passes_static_screen(self):
        self.add("safe.yml", """permissions:
  contents: read
jobs:
  test:
    steps:
      - run: python -m unittest -q
""")
        result = a.inventory(self.root)
        self.assertEqual(result["status"], "PASS_STATIC_NO_WRITERS")
        self.assertEqual(result["scanned_count"], 1)
        self.assertEqual(result["direct_main_writer_count"], 0)

    def test_main_push_holds(self):
        self.add("publisher.yml", """permissions:
  contents: write
jobs:
  publish:
    steps:
      - run: |
          git commit -m receipt
          git push origin HEAD:main
""")
        result = a.inventory(self.root)
        self.assertEqual(result["status"], "HOLD_DIRECT_MAIN_WRITERS")
        self.assertEqual(result["direct_main_push_sites"], 1)

    def test_scoped_write_without_push_holds(self):
        self.add("job.yml", """permissions:
  contents: read
jobs:
  mutate:
    permissions:
      contents: write
    steps:
      - run: echo pass
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_write_all_holds(self):
        self.add("all.yml", "permissions: write-all\njobs:\n  x:\n    steps: []\n")
        self.assertEqual(a.inventory(self.root)["manual_review_count"], 1)

    def test_dynamic_push_holds(self):
        self.add("dynamic.yml", """jobs:
  x:
    steps:
      - run: git push "$REMOTE" "$REF"
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_gh_dispatch_is_not_mistaken_for_read_only(self):
        self.add("dispatch.yml", """jobs:
  x:
    steps:
      - run: gh workflow run another.yml
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_api_mutation_holds(self):
        self.add("api.yml", """jobs:
  x:
    steps:
      - run: python -c "requests.post('https://example.invalid')"
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_pr_creator_holds(self):
        self.add("pr.yml", """jobs:
  x:
    steps:
      - uses: peter-evans/create-pull-request@v7
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_multiline_continued_main_push_is_a_direct_writer(self):
        self.add("split-push.yml", """jobs:
  writer:
    steps:
      - run: |
          git push origin \\
            HEAD:main
""")
        audit = a.inventory(self.root)
        self.assertEqual(audit["status"], "HOLD_DIRECT_MAIN_WRITERS")
        self.assertEqual(audit["direct_main_writer_count"], 1)
        self.assertEqual(audit["direct_main_push_sites"], 1)

    def test_curl_post_with_implicit_token_needs_mutation_review(self):
        self.add("curl-writer.yml", """jobs:
  publish:
    steps:
      - run: curl -X POST https://api.github.com/repos/acme/project/dispatches
""")
        audit = a.inventory(self.root)
        self.assertEqual(audit["status"], "HOLD_WRITABLE_OR_UNREVIEWED")
        self.assertEqual(audit["manual_review_count"], 1)

    def test_github_release_creation_needs_mutation_review(self):
        self.add("gh-release.yml", """jobs:
  publish:
    steps:
      - run: gh release create v1.0.0 artifact.zip
""")
        audit = a.inventory(self.root)
        self.assertEqual(audit["status"], "HOLD_WRITABLE_OR_UNREVIEWED")
        self.assertEqual(audit["manual_review_count"], 1)

    def test_gh_api_implicit_post_fails_closed(self):
        self.add("gh-fields.yml", """jobs:
  publisher:
    steps:
      - run: gh api repos/acme/project/dispatches -f event_type=checkpoint
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_gh_api_typed_field_post_fails_closed(self):
        self.add("gh-fields-typed.yml", """jobs:
  publisher:
    steps:
      - run: gh api repos/acme/project/dispatches -F event_id=1
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_gh_api_input_payload_requires_review(self):
        self.add("gh-input.yml", """jobs:
  publisher:
    steps:
      - run: gh api repos/acme/project/dispatches --input event.json
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_curl_upload_short_put_fails_closed(self):
        self.add("curl-short-upload.yml", """jobs:
  publisher:
    steps:
      - run: curl -T payload.json https://api.example.invalid/v1/upload
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_curl_upload_long_put_fails_closed(self):
        self.add("curl-long-upload.yml", """jobs:
  publisher:
    steps:
      - run: curl --upload-file payload.json https://api.example.invalid/v1/upload
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_curl_form_post_fails_closed(self):
        self.add("curl-form.yml", """jobs:
  publisher:
    steps:
      - run: curl -F evidence=@payload.json https://api.example.invalid/upload
""")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_WRITABLE_OR_UNREVIEWED")

    def test_known_gh_api_read_only_get_remains_static_pass(self):
        self.add("gh-get.yml", """jobs:
  inspect:
    steps:
      - run: gh api repos/acme/project/commits
""")
        self.assertEqual(a.inventory(self.root)["status"], "PASS_STATIC_NO_WRITERS")

    def test_known_curl_head_remains_static_pass(self):
        self.add("curl-head.yml", """jobs:
  inspect:
    steps:
      - run: curl -I https://api.example.invalid/status
""")
        self.assertEqual(a.inventory(self.root)["status"], "PASS_STATIC_NO_WRITERS")

    def test_invalid_yaml_fails_closed(self):
        self.add("invalid.yml", "jobs: [\n")
        result = a.inventory(self.root)
        self.assertEqual(result["status"], "HOLD_UNREADABLE_WORKFLOWS")
        self.assertEqual(result["scanned_count"], 0)

    def test_empty_workflow_is_not_pass(self):
        self.add("empty.yml", "jobs: {}\n")
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_UNREADABLE_WORKFLOWS")

    def test_missing_dir_is_error(self):
        with self.assertRaisesRegex(a.AuditError, "WORKFLOW_DIRECTORY_MISSING"):
            a.inventory(self.root / "missing")

    def test_symlink_rejected(self):
        target = self.root / "source.txt"
        target.write_text("jobs: {x: {steps: []}}", encoding="utf-8")
        (self.folder / "alias.yml").symlink_to(target)
        self.assertEqual(a.inventory(self.root)["status"], "HOLD_UNREADABLE_WORKFLOWS")

    def test_inventory_does_not_write_source(self):
        self.add("read.yml", "jobs: {x: {steps: []}}\n")
        before = [(f.name, f.read_bytes()) for f in self.folder.iterdir()]
        a.inventory(self.root)
        self.assertEqual(before, [(f.name, f.read_bytes()) for f in self.folder.iterdir()])

    def test_sha256_is_content_hash_and_no_payload_leaks(self):
        f = self.add("read.yml", "jobs: {x: {steps: []}}\n")
        report = a.inventory(self.root)
        import hashlib
        self.assertEqual(report["workflows"][0]["sha256"], hashlib.sha256(f.read_bytes()).hexdigest())
        self.assertNotIn(f.read_text(), json.dumps(report))

    def test_workflow_count_is_all_files_not_only_writers(self):
        self.add("r1.yml", "jobs: {x: {steps: []}}\n")
        self.add("r2.yaml", "jobs: {x: {steps: []}}\n")
        self.add("notes.txt", "this is not a workflow")
        self.assertEqual(a.inventory(self.root)["workflow_count"], 2)


if __name__ == "__main__":
    unittest.main()

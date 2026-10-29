"""Políticas explícitas de imágenes: sin red real ni sustituciones silenciosas."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import reference as ref
from test_reference import article, solve


class ImageModes(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.file = self.root / "fixture.png"
        self.file.write_bytes(b"fixed image bytes")
        self.url = "https://example.invalid/one.png"

    def scenario(self, name):
        output = self.root / name
        notebook = Path(__file__).resolve().parents[2] / "wikipedia-article-analysis.ipynb"
        manifest = ref.create_bundle(output, {"clients": 1, "selected_rows": 4, "files": []}, notebook)
        first = article("alpha", url="duplicate", sections='[{"name":"biography"}]', image={"content_url": self.url})
        rows = [first, deepcopy(first), article("beta", url="other", sections='[{"name":"biography"}]', image={"content_url": "https://example.invalid/two.png"}), article("gamma", url="absent", sections='[{"name":"biography"}]')]
        results, stats = solve(rows)
        ref.export_client(output, manifest, 0, results, stats)
        return output

    def q2(self, output):
        return ref.read_jsonl(output / "client-0/q2.jsonl")

    def test_defer_preserves_pending_null_and_other_queries(self):
        output = self.scenario("deferred")
        before = {q: ref.digest(output / f"client-0/{q}.jsonl") for q in ("q1", "q2", "q3", "q4", "q5")}
        with patch.object(ref, "urlopen") as fetch:
            audit = ref.handle_images(output)
            fetch.assert_not_called()
        self.assertEqual(audit["status"], "incomplete_images")
        self.assertEqual(audit["q2_pending_records"], 3)
        self.assertEqual(sum(row["image"] is None for row in self.q2(output)), 1)
        self.assertEqual(before, {q: ref.digest(output / f"client-0/{q}.jsonl") for q in before})
        self.assertEqual(json.loads((output / "manifest.json").read_text())["image_handling"], {"mode": "defer"})

    def test_fixture_preserves_sources_duplicates_and_independent_bytes(self):
        output = self.scenario("fixture")
        previous = self.q2(output)
        unchanged = {q: ref.digest(output / f"client-0/{q}.jsonl") for q in ("q1", "q3", "q4", "q5")}
        with patch.object(ref, "urlopen") as fetch:
            self.assertEqual(ref.handle_images(output, "fixture", self.file)["status"], "complete")
            fetch.assert_not_called()
        current = self.q2(output)
        self.assertEqual(len(current), len(previous))
        for old, new in zip(previous, current):
            if old["image"] is None:
                self.assertIsNone(new["image"])
            else:
                self.assertEqual(new["image"]["source_url"], old["image"]["source_url"])
                self.assertEqual(new["image"]["provenance"], "synthetic_fixture")
                self.assertEqual((output / new["image"]["path"]).read_bytes(), self.file.read_bytes())
        self.assertFalse((self.root / "images/index.json").exists())
        self.assertEqual(unchanged, {q: ref.digest(output / f"client-0/{q}.jsonl") for q in unchanged})
        self.file.write_bytes(b"edited fixture")
        self.assertEqual(ref.verify_bundle(output)["status"], "complete")
        with self.assertRaisesRegex(ValueError, "pending"):
            ref.handle_images(output, "fixture", self.file)

    def test_network_failure_does_not_supply_fixture_bytes(self):
        output = self.scenario("network")
        with patch.object(ref, "capture_user_agent", return_value="Test/1.0"), patch.object(ref, "urlopen", side_effect=OSError("offline")) as fetch, patch.object(ref, "store_image") as store:
            with self.assertRaisesRegex(RuntimeError, "Q2 sigue incompleta"):
                ref.handle_images(output, "network")
            self.assertEqual(fetch.call_count, 1)
            store.assert_not_called()
        self.assertEqual(ref.verify_bundle(output, require_images=False)["q2_pending_records"], 3)
        self.assertTrue(all(row["image"] is None or row["image"]["status"] == "pending" for row in self.q2(output)))

    def test_network_rejects_fixture_in_bundle_or_legacy_url_index(self):
        output = self.scenario("synthetic")
        ref.handle_images(output, "fixture", self.file)
        image = next(row["image"] for row in self.q2(output) if row["image"])
        with patch.object(ref, "urlopen") as fetch:
            with self.assertRaisesRegex(ValueError, "synthetic_fixture"):
                ref.capture_images(output)
            fetch.assert_not_called()
        # Even a legacy index populated by old tiny preparation cannot masquerade as a capture.
        ref.write_image_index(self.root / "images", {image["source_url"]: image})
        pending = self.scenario("pending")
        with patch.object(ref, "urlopen") as fetch:
            with self.assertRaisesRegex(RuntimeError, "synthetic_fixture"):
                ref.capture_images(pending)
            fetch.assert_not_called()

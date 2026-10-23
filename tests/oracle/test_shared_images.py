"""Reutilización de bytes entre escenarios, conservando las referencias de cada uno."""

from email.message import Message
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import reference as ref
from test_reference import article, solve


class Response(io.BytesIO):
    url = "https://example.invalid/image.png"
    headers = Message()
    headers["Content-Type"] = "image/png"


class SharedImages(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        agent = patch.object(ref, "capture_user_agent", return_value="Fixture/1.0")
        agent.start()
        self.addCleanup(agent.stop)

    def scenario(self, name, urls):
        output = self.root / name
        notebook = Path(__file__).resolve().parents[2] / "wikipedia-article-analysis.ipynb"
        manifest = ref.create_bundle(output, {"clients": 1, "selected_rows": len(urls),
                                              "files": []}, notebook)
        results, stats = solve([article("alpha", url=f"article-{i}",
                                        sections='[{"name":"biography"}]',
                                        image={"content_url": url})
                                for i, url in enumerate(urls)])
        ref.export_client(output, manifest, 0, results, stats)
        return output

    def images(self, output):
        return [row["image"] for row in ref.read_jsonl(output / "client-0/q2.jsonl")]

    def capture(self, output, raw=b"exact-original-image"):
        with patch.object(ref, "urlopen", return_value=Response(raw)) as fetch:
            ref.capture_images(output, interval=0)
        return fetch

    def test_sibling_scenario_reuses_url_without_network_or_contact(self):
        first = self.scenario("first", [Response.url])
        self.capture(first)
        second = self.scenario("second", [Response.url, Response.url])
        unchanged = {q: ref.digest(second / f"client-0/{q}.jsonl")
                     for q in ("q1", "q3", "q4", "q5")}
        with patch.object(ref, "urlopen") as fetch, patch.object(ref, "capture_user_agent") as contact:
            self.assertEqual(ref.capture_images(second)["status"], "complete")
            fetch.assert_not_called()
            contact.assert_not_called()
        images = self.images(second)
        self.assertEqual(images, self.images(first) * 2)
        self.assertTrue(images[0]["path"].startswith("../images/"))
        self.assertFalse((second / "images").exists())
        self.assertEqual(len(list((self.root / "images").glob("*.bin"))), 1)
        for q, checksum in unchanged.items():
            self.assertEqual(ref.digest(second / f"client-0/{q}.jsonl"), checksum)
        saved = json.loads((second / "manifest.json").read_text())
        session = saved["image_capture_sessions"][-1]
        self.assertEqual((session["attempted"], session["downloaded"], session["reused_from_store"]),
                         (0, 0, 1))

    def test_different_urls_with_identical_bytes_share_one_file(self):
        first = self.scenario("first", [Response.url])
        second = self.scenario("second", ["https://example.invalid/another.png"])
        self.capture(first)
        self.assertEqual(self.capture(second).call_count, 1)
        self.assertEqual(self.images(first)[0]["path"], self.images(second)[0]["path"])
        self.assertNotEqual(self.images(first)[0]["source_url"], self.images(second)[0]["source_url"])
        self.assertEqual(len(ref.load_image_index(self.root / "images")), 2)
        self.assertEqual(len(list((self.root / "images").glob("*.bin"))), 1)

    def test_missing_or_corrupt_cached_image_is_not_silently_redownloaded(self):
        first = self.scenario("first", [Response.url])
        self.capture(first)
        blob = first / self.images(first)[0]["path"]
        for name, content in (("corrupt", b"corrupt"), ("missing", None)):
            with self.subTest(name=name):
                if content is None:
                    blob.unlink()
                else:
                    blob.write_bytes(content)
                second = self.scenario(name, [Response.url])
                with patch.object(ref, "urlopen") as fetch:
                    with self.assertRaisesRegex(RuntimeError, "Q2 sigue incompleta"):
                        ref.capture_images(second)
                    fetch.assert_not_called()
                self.assertEqual(self.images(second)[0]["status"], "pending")

    def test_index_changes_do_not_change_an_existing_scenarios_expected_bytes(self):
        first = self.scenario("first", [Response.url])
        self.capture(first, b"old-original")
        pinned = (first / "client-0/q2.jsonl").read_bytes()
        index = ref.load_image_index(self.root / "images")
        new_bytes = self.root / "new-image"
        new_bytes.write_bytes(b"new-original")
        image = {**index[Response.url], "sha256": ref.digest(new_bytes),
                 "bytes": new_bytes.stat().st_size}
        index[Response.url] = ref.store_image(first, new_bytes, image)
        ref.write_image_index(self.root / "images", index)
        with patch.object(ref, "urlopen") as fetch:
            ref.capture_images(first)
            second = self.scenario("second", [Response.url])
            ref.capture_images(second)
            fetch.assert_not_called()
        self.assertEqual((first / "client-0/q2.jsonl").read_bytes(), pinned)
        self.assertNotEqual(self.images(first)[0]["sha256"], self.images(second)[0]["sha256"])
        self.assertEqual(ref.verify_bundle(first)["status"], "complete")
        self.assertEqual(ref.verify_bundle(second)["status"], "complete")

    def test_404_is_kept_in_its_scenario_and_not_cached_for_other_scenarios(self):
        first = self.scenario("first", [Response.url])
        error = HTTPError(Response.url, 404, "Not Found", Message(), io.BytesIO())
        with patch.object(ref, "urlopen", side_effect=error):
            ref.capture_images(first)
        self.assertEqual(ref.load_image_index(self.root / "images"), {})
        second = self.scenario("second", [Response.url])
        self.assertEqual(self.capture(second).call_count, 1)
        self.assertEqual(self.images(first)[0]["status"], "not_found")
        self.assertEqual(ref.verify_bundle(second)["status"], "complete")

    def test_verifier_still_accepts_legacy_scenario_local_image_paths(self):
        output = self.scenario("legacy", [Response.url])
        blob = output / "images/original.bin"
        blob.parent.mkdir()
        blob.write_bytes(b"legacy-original")
        rows = ref.read_jsonl(output / "client-0/q2.jsonl")
        rows[0]["image"].update(status="available", path="images/original.bin",
                                sha256=ref.digest(blob), bytes=blob.stat().st_size)
        path = output / "client-0/q2.jsonl"
        ref.write_jsonl(path, rows)
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["clients"][0]["queries"]["q2"].update(sha256=ref.digest(path), status="complete")
        ref.finish_bundle(output, manifest)
        self.assertEqual(ref.verify_bundle(output)["status"], "complete")


if __name__ == "__main__":
    unittest.main()

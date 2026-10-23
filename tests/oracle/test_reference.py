"""Casos con expectativas revisables: semántica, asignación y referencias incompletas."""

from copy import deepcopy
from datetime import datetime
from email.message import Message
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import pyarrow as pa
import pyarrow.parquet as pq

import reference as ref


def article(abstract, year=2020, language="en", url="article", sections="[]", image=None):
    return {"name": url, "url": url, "identifier": 1,
            "date_modified": datetime(year, 12, 31, 23, 59, 59),
            "in_language": {"identifier": language}, "abstract": abstract,
            "sections": sections, "image": image}


def solve(rows):
    return ref.serial_queries(((('sample.parquet', i), row) for i, row in enumerate(rows)),
                              {"the", "et"})


class SerialSemantics(unittest.TestCase):
    def test_repeated_words_records_languages_and_cutoff(self):
        old = article("the alpha alpha beta 123", url="old",
                      sections='[{"name":"BIOGRAPHY"}]')
        result, stats = solve([old, deepcopy(old),
                               article("alpha gamma", 2019, "fr", "fr"),
                               article("alpha alpha beta beta gamma", 2021, url="new")])
        self.assertEqual([r["url"] for r in result["q1"]], ["old", "old"])
        self.assertEqual(result["q2"], [{"name": "old", "url": "old", "image": None}] * 2)
        self.assertEqual(result["q3"], [{"word": "alpha"}, {"word": "gamma"}])
        self.assertEqual(result["q4"], [{"word": "alpha", "count": 4},
                                       {"word": "beta", "count": 3},
                                       {"word": "gamma", "count": 2}])
        self.assertEqual(result["q5"], [{"url": "new", "count": 5}])
        self.assertEqual((stats["historical_sum"], stats["historical_count"]), (8, 3))

    def test_null_empty_strict_threshold_and_no_history(self):
        result, stats = solve([article("alpha beta", url="hist"),
                               article(None, url="null"), article("", url="empty"),
                               article("gamma", 2021, url="above")])
        self.assertEqual((stats["historical_sum"], stats["historical_count"]), (2, 2))
        self.assertEqual(result["q5"], [])  # Igual al promedio, no superior.
        result, stats = solve([article(None), article("alpha alpha", 2021)])
        self.assertEqual(result["q5"], [])
        self.assertEqual(stats["q5_state"], "no_historical_base")
        self.assertEqual(solve([])[0], {q: [] for q in ["q1", "q2", "q3", "q4", "q5"]})

    def test_top20_ties_order_unicode_and_reordering(self):
        text = " ".join(f"term{i:02}" for i in range(25))
        rows = [article(text), article("ÉCOLE école et 123 456", language="fr")]
        result, _ = solve(rows)
        self.assertEqual(result["q4"], [{"word": f"term{i:02}", "count": 1} for i in range(20)])
        self.assertEqual(result, solve(list(reversed(rows)))[0])
        self.assertEqual(ref.tokens("ÉCOLE école et 123", {"et"}), ["école", "école"])

    def test_clients_are_isolated_and_sections_match_exactly(self):
        a, _ = solve([article("privateword", sections='[{"name":"biography notes"}]')])
        b, _ = solve([article("privateword", language="fr")])
        self.assertEqual(a["q3"], [])
        self.assertEqual(b["q3"], [])
        self.assertEqual(a["q2"], [])


class FilesAndPartitions(unittest.TestCase):
    def setUp(self):
        agent = patch.object(ref, "capture_user_agent", return_value="OracleTests/1.0 (fixture@example.invalid)")
        agent.start()
        self.addCleanup(agent.stop)

    def test_partition_is_exhaustive_disjoint_and_batch_independent(self):
        with tempfile.TemporaryDirectory() as temp:
            dataset = Path(temp)
            for language, count in [("en", 7), ("fr", 5)]:
                path = dataset / f"{language}wiki/data/{language}wiki_namespace_0_00000.parquet"
                path.parent.mkdir(parents=True)
                pq.write_table(pa.Table.from_pylist([article("alpha", language=language,
                                                             url=str(i)) for i in range(count)]), path)
            inputs = ref.inventory(dataset, clients=3)
            partitions = []
            for client in range(3):
                first = list(ref.client_rows(dataset, inputs, client, batch_size=2))
                second = list(ref.client_rows(dataset, inputs, client, batch_size=5))
                self.assertEqual(first, second)
                partitions.append({identity for identity, _ in first})
            self.assertEqual([len(part) for part in partitions], [4, 4, 4])
            self.assertEqual(len(set.union(*partitions)), 12)
            self.assertFalse(partitions[0] & partitions[1])
            capped = ref.inventory(dataset, clients=3, rows_per_file=4)
            self.assertEqual([len(list(ref.client_rows(dataset, capped, c))) for c in range(3)],
                             [3, 3, 2])

    def test_missing_bytes_cannot_pass_as_a_complete_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "expected"
            inputs = {"clients": 1, "selected_rows": 1, "files": []}
            notebook = Path(__file__).resolve().parents[2] / "wikipedia-article-analysis.ipynb"
            manifest = ref.create_bundle(output, inputs, notebook)
            result, stats = solve([article("alpha", sections='[{"name":"biographie"}]',
                                           image={"content_url": "https://example.invalid/image.png"})])
            ref.export_client(output, manifest, 0, result, stats)
            self.assertEqual(ref.verify_bundle(output, require_images=False)["status"],
                             "incomplete_images")
            with self.assertRaisesRegex(ValueError, "Q2 INCOMPLETA"):
                ref.verify_bundle(output)
            blob = output / "client-0/q1.jsonl"
            blob.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Salida modificada"):
                ref.verify_bundle(output, require_images=False)

    def test_failed_image_capture_stays_pending_and_available_bytes_are_verified(self):
        class ImageResponse(io.BytesIO):
            url = "https://example.invalid/image.png"
            headers = Message()
            headers["Content-Type"] = "image/png"

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "expected"
            notebook = Path(__file__).resolve().parents[2] / "wikipedia-article-analysis.ipynb"
            manifest = ref.create_bundle(output, {"clients": 1, "selected_rows": 2,
                                                  "files": []}, notebook)
            row = article("alpha", sections='[{"name":"biography"}]',
                          image={"content_url": ImageResponse.url})
            result, stats = solve([row, deepcopy(row)])
            ref.export_client(output, manifest, 0, result, stats)
            with patch.object(ref, "urlopen", side_effect=OSError("red no disponible")) as fetch:
                with self.assertRaisesRegex(RuntimeError, "Q2 sigue incompleta"):
                    ref.capture_images(output)
                self.assertEqual(fetch.call_count, 1)
            self.assertEqual(ref.verify_bundle(output, require_images=False)["q2_pending_records"], 2)
            raw = b"\x89PNG\r\n\x1a\nexact-original-test-bytes"
            with patch.object(ref, "urlopen", return_value=ImageResponse(raw)) as fetch:
                self.assertEqual(ref.capture_images(output)["status"], "complete")
                self.assertEqual(fetch.call_count, 1)  # Dos filas, una descarga de la URL.
            q2 = ref.read_jsonl(output / "client-0/q2.jsonl")
            self.assertEqual(len(q2), 2)
            blob = output / q2[0]["image"]["path"]
            self.assertEqual(blob.read_bytes(), raw)
            blob.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "Imagen modificada"):
                ref.verify_bundle(output)

    def test_interval_http429_and_retry_after_do_not_retry_early(self):
        class Response(io.BytesIO):
            url = "https://example.invalid/one.png"
            headers = Message()
            headers["Content-Type"] = "image/png"

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "expected"
            notebook = Path(__file__).resolve().parents[2] / "wikipedia-article-analysis.ipynb"
            manifest = ref.create_bundle(output, {"clients": 1, "selected_rows": 2,
                                                  "files": []}, notebook)
            results, stats = solve([
                article("alpha", url="a", sections='[{"name":"biography"}]',
                        image={"content_url": Response.url}),
                article("beta", url="b", sections='[{"name":"biography"}]',
                        image={"content_url": "https://example.invalid/two.png"})])
            ref.export_client(output, manifest, 0, results, stats)
            headers = Message()
            headers["Retry-After"] = "120"
            error = HTTPError("https://example.invalid/two.png", 429,
                              "Too many requests", headers, io.BytesIO())
            with patch.object(ref.time, "monotonic", return_value=10), \
                    patch.object(ref.time, "sleep") as sleep, \
                    patch.object(ref, "urlopen", side_effect=[Response(b"original"), error]) as fetch:
                with self.assertRaisesRegex(RuntimeError, "Q2 sigue incompleta"):
                    ref.capture_images(output, interval=3)
                sleep.assert_called_once_with(3)
                self.assertEqual(fetch.call_count, 2)
                request = fetch.call_args_list[0].args[0]
                self.assertEqual(request.get_header("User-agent"), "OracleTests/1.0 (fixture@example.invalid)")
            saved = json.loads((output / "manifest.json").read_text())
            self.assertEqual(saved["image_capture_error"]["http_status"], 429)
            self.assertEqual(saved["image_capture_error"]["retry_after"], "120")
            self.assertEqual(saved["image_capture_sessions"][-1]["downloaded"], 1)
            with patch.object(ref, "urlopen") as fetch:
                with self.assertRaisesRegex(RuntimeError, "Respetar Retry-After"):
                    ref.capture_images(output)
                fetch.assert_not_called()

    def test_404_is_logged_and_later_images_are_captured_without_losing_records(self):
        class Response(io.BytesIO):
            url = "https://example.invalid/ok.png"
            headers = Message()
            headers["Content-Type"] = "image/png"

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "expected"
            notebook = Path(__file__).resolve().parents[2] / "wikipedia-article-analysis.ipynb"
            manifest = ref.create_bundle(output, {"clients": 1, "selected_rows": 3,
                                                  "files": []}, notebook)
            missing = "https://example.invalid/missing.png"
            results, stats = solve([
                article("alpha", url="a", sections='[{"name":"biography"}]',
                        image={"content_url": missing}),
                article("beta", url="b", sections='[{"name":"biography"}]',
                        image={"content_url": Response.url}),
                article("gamma", url="c", sections='[{"name":"biography"}]',
                        image={"content_url": missing})])
            ref.export_client(output, manifest, 0, results, stats)
            error = HTTPError(missing, 404, "Not Found", Message(), io.BytesIO())
            with patch.object(ref.time, "monotonic", return_value=10), \
                    patch.object(ref.time, "sleep") as sleep, \
                    patch.object(ref, "urlopen", side_effect=[error, Response(b"original")]) as fetch:
                audit = ref.capture_images(output)
                self.assertEqual(fetch.call_count, 2)
                sleep.assert_called_once_with(3)
            self.assertEqual(audit["status"], "incomplete_images")
            self.assertEqual(audit["q2_pending_records"], 0)
            self.assertEqual(audit["q2_not_found_records"], 2)
            rows = ref.read_jsonl(output / "client-0/q2.jsonl")
            self.assertEqual([r["image"]["status"] for r in rows],
                             ["not_found", "available", "not_found"])
            log = ref.read_jsonl(output / "image-404-errors.jsonl")
            self.assertEqual(len(log), 1)
            self.assertEqual(log[0]["source_url"], missing)
            self.assertEqual(log[0]["http_status"], 404)
            with self.assertRaisesRegex(ValueError, "Q2 INCOMPLETA"):
                ref.verify_bundle(output)
            with patch.object(ref, "urlopen") as fetch:
                ref.capture_images(output)  # No volver a pedir URLs ya registradas como 404.
                fetch.assert_not_called()

    def test_404_does_not_prevent_a_later_429_from_stopping_the_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "expected"
            notebook = Path(__file__).resolve().parents[2] / "wikipedia-article-analysis.ipynb"
            manifest = ref.create_bundle(output, {"clients": 1, "selected_rows": 3,
                                                  "files": []}, notebook)
            results, stats = solve([article("alpha", url=f"article-{i}",
                                            sections='[{"name":"biography"}]',
                                            image={"content_url": f"https://example.invalid/{i}.png"})
                                    for i in range(3)])
            ref.export_client(output, manifest, 0, results, stats)
            errors = [HTTPError("https://example.invalid/0.png", 404, "Not Found", Message(), io.BytesIO()),
                      HTTPError("https://example.invalid/1.png", 429, "Too Many Requests", Message(), io.BytesIO())]
            with patch.object(ref.time, "sleep"), patch.object(ref, "urlopen", side_effect=errors) as fetch:
                with self.assertRaisesRegex(RuntimeError, "descarga detenida"):
                    ref.capture_images(output)
                self.assertEqual(fetch.call_count, 2)
            audit = ref.verify_bundle(output, require_images=False)
            self.assertEqual((audit["q2_not_found_records"], audit["q2_pending_records"]), (1, 2))
            saved = json.loads((output / "manifest.json").read_text())
            self.assertEqual(saved["image_capture_error"]["http_status"], 429)


class DownloadConfiguration(unittest.TestCase):
    def test_contact_comes_from_env_file_and_environment_can_override_it(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            path.write_text('WIKIMEDIA_OPERATOR_NAME="Fixture Operator"\n'
                            'WIKIMEDIA_OPERATOR_EMAIL="fixture@example.invalid"\n')
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(ref.capture_user_agent(path),
                                 "WikiAnalyticsSerialOracle/1.0 (Fixture Operator; mailto:fixture@example.invalid)")
                with patch.dict(os.environ, {"WIKIMEDIA_OPERATOR_NAME": "Override"}):
                    self.assertIn("(Override;", ref.capture_user_agent(path))
            path.write_text('WIKIMEDIA_OPERATOR_NAME="Missing Email"\n')
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "Configurar"):
                    ref.capture_user_agent(path)

    def test_retry_after_supports_seconds_and_http_dates(self):
        now = ref.datetime(2026, 10, 22, tzinfo=ref.timezone.utc)
        self.assertEqual(ref.retry_after_deadline("120", now), now + ref.timedelta(seconds=120))
        self.assertEqual(ref.retry_after_deadline("Thu, 22 Oct 2026 00:02:00 GMT", now),
                         now + ref.timedelta(seconds=120))
        self.assertIsNone(ref.retry_after_deadline("invalid", now))


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from compare import compare, compare_client_results, normalize


class ComparisonTest(unittest.TestCase):
    def test_multisets_preserve_occurrences(self):
        examples = {
            "q1": {"url": "a", "date_modified": "2020-01-01T00:00:00.000"},
            "q5": {"url": "a", "count": 5},
        }
        with tempfile.TemporaryDirectory() as directory:
            expected, actual = (Path(directory) / name for name in ("expected", "actual"))
            for query, row in examples.items():
                other = dict(row, url="b")
                def write(path, rows):
                    path.write_text("".join(json.dumps(value) + "\n" for value in rows))
                write(expected, [row, row, other])
                write(actual, [other, row, row])
                compare(query, expected, actual)
                for rows in ([row, other], [row, row, row, other], [dict(row, url="wrong"), row, other]):
                    write(actual, rows)
                    with self.assertRaises(AssertionError):
                        compare(query, expected, actual)

    def test_images_compare_bytes_and_multiplicity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blob = root / "image.bin"
            blob.write_bytes(b"image bytes")
            descriptor = {"status": "available", "path": "image.bin", "bytes": 11,
                          "sha256": hashlib.sha256(blob.read_bytes()).hexdigest()}
            row = {"name": "name", "url": "url", "image": descriptor}
            normalized = normalize("q2", [row, row], root)
            self.assertNotEqual(normalized, normalize("q2", [row], root))
            self.assertNotEqual(normalized, normalize("q2", [dict(row, image=None), row], root))
            metadata = dict(descriptor, source_url="ignored", captured_at="ignored")
            self.assertEqual(normalized, normalize("q2", [dict(row, image=metadata), row], root))
            for status in ("pending", "not_found"):
                with self.assertRaises(ValueError):
                    normalize("q2", [dict(row, image=dict(descriptor, status=status))], root)
            blob.write_bytes(b"wrong bytes")
            with self.assertRaises(ValueError):
                normalize("q2", [row], root)
            changed = dict(descriptor, sha256=hashlib.sha256(blob.read_bytes()).hexdigest())
            self.assertNotEqual(normalized, normalize("q2", [dict(row, image=changed), dict(row, image=changed)], root))

    def test_vocabulary_and_top_order(self):
        for rows in ([{"word": "a"}, {"word": "a"}], [{"word": "b"}, {"word": "a"}]):
            with self.assertRaises(ValueError):
                normalize("q3", rows, ".")
        top = [{"word": "a", "count": 2}, {"word": "b", "count": 2}]
        normalize("q4", top, ".")
        for rows in (top[::-1], [top[0], top[0]], [{"word": str(i), "count": 1} for i in range(21)]):
            with self.assertRaises(ValueError):
                normalize("q4", rows, ".")
        with self.assertRaises(ValueError):
            normalize("q5", [{"url": "a", "count": True}], ".")

    def test_all_five_outputs_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                compare_client_results(directory, directory)

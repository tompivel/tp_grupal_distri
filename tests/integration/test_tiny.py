from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from compare import compare, read
from run import check, EXPECTED, FIXTURES, ROOT
import reference


class TinyTest(unittest.TestCase):
    def test_integrity_schemas_and_assignment(self):
        audit = check()
        self.assertEqual(audit["references"]["status"], "complete")
        self.assertEqual(audit["integration"]["status"], "pending")
        manifest = json.loads((EXPECTED / "manifest.json").read_text())
        self.assertEqual(reference.inventory(FIXTURES, clients=2), manifest["input"])
        for file in manifest["input"]["files"]:
            path = FIXTURES / file["path"]
            language = path.parent.parent.name
            raw = json.loads((ROOT / "dataset" / language / "schema.json").read_text())
            schema = pa.ipc.read_schema(pa.BufferReader(bytes.fromhex(raw["arrow_ipc_hex"])))
            self.assertEqual(pq.read_schema(path), schema)
            self.assertEqual(len(schema), 19)
        for index in (0, 1):
            rows = list(reference.client_rows(FIXTURES, manifest["input"], index))
            self.assertEqual(len(rows), 16)
            self.assertTrue(all(f"/tiny/{index}/" in row["url"] for _, row in rows))
            self.assertEqual(rows[0][1], rows[1][1])  # exact repeated article

    def test_frozen_outputs_match_serial_oracle(self):
        manifest = json.loads((EXPECTED / "manifest.json").read_text())
        for index, client in enumerate(manifest["clients"]):
            computed, stats = reference.serial_queries(reference.client_rows(FIXTURES, manifest["input"], index), reference.load_stopwords())
            self.assertEqual(stats["historical_sum"], 32 if index == 0 else 48)
            self.assertEqual(stats["historical_count"], 8)
            for query, rows in computed.items():
                frozen = read(EXPECTED / client["queries"][query]["path"])
                if query == "q2":
                    for row in frozen:
                        if row["image"]:
                            self.assertEqual((EXPECTED / row["image"]["path"]).read_bytes(), (FIXTURES / "services/pixel.png").read_bytes())
                            row["image"] = {"source_url": row["image"]["source_url"], "status": "pending"}
                self.assertEqual(rows, frozen, (index, query))

    def test_hand_checked_query_cases(self):
        tied_a = "amber bas beta birch bridge brume cedar delta dune egal ember equal fern flocon gamma grove".split()
        tied_b = "amber bas beta birch bridge brume cedar delta dune east egal ember equal fern flocon".split()
        for index in (0, 1):
            root = EXPECTED / f"client-{index}"
            prefix = f"https://example.invalid/tiny/{index}"
            self.assertEqual(Counter(row["url"] for row in read(root / "q1.jsonl")), Counter({f"{prefix}/en/0": 2, f"{prefix}/en/2": 1, f"{prefix}/en/3": 1}))
            q2 = read(root / "q2.jsonl")
            self.assertEqual(Counter(row["url"] for row in q2), Counter({f"{prefix}/en/0": 2, f"{prefix}/en/3": 1, f"{prefix}/fr/0": 1, f"{prefix}/fr/1": 1}))
            self.assertEqual(sum(row["image"] is not None for row in q2), 3)
            self.assertEqual(read(root / "q3.jsonl"), [{"word": word} for word in (["echo", "shared"] if index == 0 else ["echo", "plume", "shared"])])
            high = ([{"word": "plume", "count": 8}] if index else []) + [{"word": "echo", "count": 3}, {"word": "shared", "count": 3}, {"word": "alpha", "count": 2}, {"word": "comet", "count": 2}]
            self.assertEqual(read(root / "q4.jsonl"), high + [{"word": word, "count": 1} for word in (tied_b if index else tied_a)])
            self.assertEqual(read(root / "q5.jsonl"), [{"url": f"{prefix}/en/4", "count": 7 if index else 5}, {"url": f"{prefix}/en/7", "count": 27}, {"url": f"{prefix}/fr/4", "count": 7 if index else 5}])
            for query in ("q1", "q2", "q3", "q4", "q5"):
                compare(query, root / f"{query}.jsonl", root / f"{query}.jsonl")

    def test_pending_runner_fails_without_docker(self):
        result = subprocess.run([sys.executable, str(Path(__file__).parent / "run.py")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("No se invocó Docker", result.stderr)
        self.assertEqual(json.loads(result.stdout)["integration"]["required_queries"], [1, 2, 3, 4, 5])

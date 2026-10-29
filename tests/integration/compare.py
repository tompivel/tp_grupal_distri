"""Comparación de resultados pequeños Q1–Q5 según tests/expected/README.md.

Esta comparación no acredita cierres ni ejecución distribuida: el futuro runner
integral también debe capturar los cinco cierres y AllFinished.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

QUERIES = tuple(f"q{index}" for index in range(1, 6))
FIELDS = {"q1": {"url", "date_modified"}, "q2": {"name", "url", "image"},
          "q3": {"word"}, "q4": {"word", "count"}, "q5": {"url", "count"}}


def read(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def image_bytes(image, root):
    if image is None:
        return None
    if image.get("status") != "available":
        raise ValueError("Q2 requiere bytes disponibles; pending/404 no equivalen a ausencia")
    content = (Path(root) / image["path"]).read_bytes()
    if len(content) != image["bytes"] or hashlib.sha256(content).hexdigest() != image["sha256"]:
        raise ValueError("Bytes de imagen inconsistentes con su descriptor")
    return content


def normalize(query, rows, root):
    result = []
    for row in rows:
        if set(row) != FIELDS[query]:
            raise ValueError(f"Campos inválidos para {query}: {set(row)}")
        for key, value in row.items():
            if key == "count":
                if type(value) is not int or value < 0:
                    raise ValueError("El conteo debe ser un entero no negativo")
            elif key != "image" and not isinstance(value, str):
                raise ValueError(f"{key} debe ser string")
        if query == "q2":
            result.append((row["name"], row["url"], image_bytes(row["image"], root)))
        else:
            result.append(tuple(row[key] for key in sorted(row)))
    if query == "q3":
        words = [row["word"] for row in rows]
        if words != sorted(set(words)):
            raise ValueError("Q3 requiere vocabulario único ordenado")
    if query == "q4":
        if (len(rows) > 20 or len({row["word"] for row in rows}) != len(rows)
                or rows != sorted(rows, key=lambda row: (-row["count"], row["word"]))):
            raise ValueError("Q4 requiere top 20 único, ordenado por (-count, word)")
    return Counter(result) if query in ("q1", "q2", "q5") else result


def compare(query, expected, actual, expected_root=None, actual_root=None):
    if query not in QUERIES:
        raise ValueError(f"Consulta desconocida: {query}")
    expected, actual = Path(expected), Path(actual)
    want = normalize(query, read(expected), expected_root or expected.parent.parent)
    got = normalize(query, read(actual), actual_root or actual.parent.parent)
    if want != got:
        raise AssertionError(f"{query}: resultados diferentes (esperados={len(read(expected))}, recibidos={len(read(actual))})")


def compare_client_results(expected, actual):
    for query in QUERIES:
        compare(query, Path(expected) / f"{query}.jsonl", Path(actual) / f"{query}.jsonl")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    args = parser.parse_args()
    compare_client_results(args.expected, args.actual)

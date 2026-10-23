"""Oráculo serial independiente de Go. La generación se inicia desde el notebook."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sys
import unicodedata
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.parquet as pq

RESOURCES = Path(__file__).parent / "resources"
WORD_REGEX = r"\b\w+\b"
NUMBER_REGEX = r"[+-]?((\d+\.?\d*)|(\.\d+))"
FIELDS = ["name", "url", "identifier", "date_modified", "in_language",
          "abstract", "sections", "image"]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def load_stopwords():
    provenance = json.loads((RESOURCES / "stopwords-provenance.json").read_text())
    words = set()
    for name, metadata in provenance["files"].items():
        path = RESOURCES / name
        if digest(path) != metadata["sha256"]:
            raise ValueError(f"Stopwords modificadas: {path}")
        words.update(path.read_text(encoding="utf-8").splitlines())
    if (RESOURCES / "stopwords-union.txt").read_text(encoding="utf-8") != "\n".join(sorted(words)) + "\n":
        raise ValueError("La unión de stopwords no coincide con las listas originales")
    return words


def contract():
    words = load_stopwords()
    return {
        "version": "wiki-serial-v1",
        "lowercase": "Python str.lower; sin quitar acentos ni aplicar stemming",
        "word_regex": WORD_REGEX, "number_regex": NUMBER_REGEX,
        "unicode_version": unicodedata.unidata_version,
        "stopwords_sha256": hashlib.sha256(
            ("\n".join(sorted(words)) + "\n").encode()).hexdigest(),
        "stopwords_count": len(words),
        "q2": "name, article url, original image bytes; explicit null if absent",
        "q3": "unique intersection en/fr, excluding stopwords and numeric tokens",
        "q4": "distinct tokens per abstract; sort by (-count, word); limit 20",
        "q5": "occurrences; historical null abstracts excluded; count*N>S",
        "no_history": "empty result with no_historical_base state",
        "timestamps": "ISO 8601 milliseconds; preserve input timezone (none in sample)",
    }


def inventory(dataset, clients=5, rows_per_file=None):
    if clients < 1 or (rows_per_file is not None and rows_per_file < 1):
        raise ValueError("clients y rows_per_file deben ser positivos")
    dataset = Path(dataset)
    paths = list(dataset.glob("*wiki/data/*_namespace_0_*.parquet"))
    paths.sort(key=lambda p: (int(p.stem.rsplit("_", 1)[1]), p.parts[-3]))
    if not paths:
        raise ValueError(f"No hay Parquet en {dataset}")
    files, offset = [], 0
    for path in paths:
        parquet = pq.ParquetFile(path)
        selected = min(parquet.metadata.num_rows, rows_per_file or parquet.metadata.num_rows)
        files.append({
            "path": path.relative_to(dataset).as_posix(),
            "sha256": digest(path), "bytes": path.stat().st_size,
            "rows": parquet.metadata.num_rows, "selected_rows": selected,
            "global_offset": offset,
            "schema_sha256": hashlib.sha256(parquet.schema_arrow.serialize()).hexdigest(),
        })
        offset += selected
    return {"assignment": "global_ordinal_modulo_clients_v1", "clients": clients,
            "rows_per_file": rows_per_file, "selected_rows": offset,
            "source_parquet_bytes": sum(f["bytes"] for f in files), "files": files}


def client_rows(dataset, inputs, client, batch_size=512):
    """Identidad de ocurrencia: (archivo, fila); el lote no afecta la asignación."""
    if not 0 <= client < inputs["clients"]:
        raise ValueError("Índice de cliente inválido")
    for file in inputs["files"]:
        start = 0
        parquet = pq.ParquetFile(Path(dataset) / file["path"])
        for batch in parquet.iter_batches(batch_size=batch_size, columns=FIELDS,
                                          use_threads=False):
            count = min(batch.num_rows, file["selected_rows"] - start)
            if count <= 0:
                break
            first = (client - file["global_offset"] - start) % inputs["clients"]
            indices = list(range(first, count, inputs["clients"]))
            selected = batch.take(pa.array(indices, type=pa.int64())).to_pylist()
            for index, row in zip(indices, selected):
                yield (file["path"], start + index), row
            start += batch.num_rows


def tokens(abstract, stopwords):
    if not isinstance(abstract, str):
        return []
    return [word for word in re.findall(WORD_REGEX, abstract.lower())
            if word not in stopwords and not re.fullmatch(NUMBER_REGEX, word)]


def serial_queries(records, stopwords):
    """Una única pasada serial. Conserva filas repetidas e independencia por cliente."""
    q1, q2, candidates = [], [], []
    vocabulary = {"en": set(), "fr": set()}
    counts, languages = Counter(), Counter()
    historical_sum = historical_count = rows = 0
    occurrence_hash = hashlib.sha256()
    for identity, row in records:
        occurrence_hash.update((json.dumps(identity, ensure_ascii=False) + "\n").encode())
        rows += 1
        language = (row["in_language"] or {}).get("identifier")
        if language not in vocabulary:
            raise ValueError(f"Idioma inesperado: {language!r} en {identity}")
        languages[language] += 1
        words = tokens(row["abstract"], stopwords)
        distinct = set(words)
        vocabulary[language].update(distinct)
        counts.update(distinct)  # Q4: una unidad por palabra y abstract.
        date = row["date_modified"]
        if date is None:
            raise ValueError(f"date_modified ausente: falta definir el contrato para {identity}")
        if date.year <= 2020:
            if language == "en":
                q1.append({"url": row["url"],
                           "date_modified": date.isoformat(timespec="milliseconds")})
            sections = json.loads(row["sections"]) if row["sections"] is not None else []
            if not isinstance(sections, list):
                raise ValueError(f"sections debe codificar una lista: {identity}")
            if any(section.get("name", "").lower() in ("biography", "biographie")
                   for section in sections):
                url = (row["image"] or {}).get("content_url")
                q2.append({"name": row["name"], "url": row["url"],
                           "image": {"source_url": url, "status": "pending"} if url else None})
            if row["abstract"] is not None:
                historical_sum += len(words)  # Q5: ocurrencias, incluidas repeticiones.
                historical_count += 1
        else:
            candidates.append({"url": row["url"], "count": len(words)})
    q1.sort(key=lambda r: (r["url"], r["date_modified"]))
    q2.sort(key=lambda r: (r["name"], r["url"],
                           (r["image"] or {}).get("source_url", "")))
    q3 = [{"word": word} for word in sorted(vocabulary["en"] & vocabulary["fr"])]
    q4 = [{"word": word, "count": count}
          for word, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:20]]
    q5 = sorted((r for r in candidates if historical_count and
                 r["count"] * historical_count > historical_sum),
                key=lambda r: (r["url"], r["count"]))
    return {"q1": q1, "q2": q2, "q3": q3, "q4": q4, "q5": q5}, {
        "input_rows": rows, "languages": dict(sorted(languages.items())),
        "input_occurrences_sha256": occurrence_hash.hexdigest(),
        "historical_sum": historical_sum, "historical_count": historical_count,
        "q5_state": "complete" if historical_count else "no_historical_base",
    }


def write_jsonl(path, records):
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def create_bundle(output, inputs, notebook):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)  # Nunca sobreescribir referencias existentes.
    nb = json.loads(Path(notebook).read_text(encoding="utf-8"))
    source = [{"cell_type": c["cell_type"], "source": c["source"]} for c in nb["cells"]]
    manifest = {
        "format_version": 1, "status": "generating", "input": inputs,
        "semantics": contract(), "created_at": datetime.now(timezone.utc).isoformat(),
        "generator": {"notebook_source_sha256": hashlib.sha256(
            json.dumps(source, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "reference_sha256": digest(__file__), "python": platform.python_version(),
            "packages": {name: importlib.metadata.version(name) for name in
                         ["pyarrow", "nbformat", "nbclient", "ipykernel"]}},
        "clients": [],
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def export_client(output, manifest, client, results, stats):
    output = Path(output)
    name = f"client-{client}"
    directory = output / name
    directory.mkdir()
    entry = {"id": name, **stats, "queries": {}}
    for query, records in results.items():
        path = directory / f"{query}.jsonl"
        write_jsonl(path, records)
        pending = query == "q2" and any(r["image"] for r in records)
        entry["queries"][query] = {
            "path": path.relative_to(output).as_posix(), "sha256": digest(path),
            "rows": len(records), "status": "incomplete_images" if pending else "complete"}
    manifest["clients"].append(entry)
    finish_bundle(output, manifest)
    return entry


def finish_bundle(output, manifest):
    all_clients = len(manifest["clients"]) == manifest["input"]["clients"]
    complete = all(q["status"] == "complete" for c in manifest["clients"]
                   for q in c["queries"].values())
    manifest["status"] = ("generating" if not all_clients else
                          "complete" if complete else "incomplete_images")
    write_json(Path(output) / "manifest.json", manifest)


def verify_bundle(output, dataset=None, require_images=True):
    """Audita archivos e identidad de entrada; nunca recalcula las consultas."""
    output = Path(output)
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["semantics"] != contract():
        raise ValueError("Contrato o stopwords incompatibles")
    inputs = manifest["input"]
    if dataset is not None:
        for file in inputs["files"]:
            if digest(Path(dataset) / file["path"]) != file["sha256"]:
                raise ValueError(f"Entrada modificada: {file['path']}")
    if len(manifest["clients"]) != inputs["clients"]:
        raise ValueError("Faltan clientes")
    pending = 0
    for index, client in enumerate(manifest["clients"]):
        expected_rows = len(range(index, inputs["selected_rows"], inputs["clients"]))
        if client["id"] != f"client-{index}" or client["input_rows"] != expected_rows:
            raise ValueError("Asignación o cantidad de filas incorrecta")
        if set(client["queries"]) != {"q1", "q2", "q3", "q4", "q5"}:
            raise ValueError("Faltan consultas")
        for query, info in client["queries"].items():
            path = output / info["path"]
            records = read_jsonl(path)
            if digest(path) != info["sha256"] or len(records) != info["rows"]:
                raise ValueError(f"Salida modificada: {path}")
            if query == "q2":
                query_pending = 0
                for record in records:
                    image = record["image"]
                    if image is None:
                        continue
                    if image["status"] != "available":
                        query_pending += 1
                        continue
                    blob = output / image["path"]
                    if digest(blob) != image["sha256"] or blob.stat().st_size != image["bytes"]:
                        raise ValueError(f"Imagen modificada: {blob}")
                pending += query_pending
                expected = "incomplete_images" if query_pending else "complete"
                if info["status"] != expected:
                    raise ValueError("Estado de Q2 inconsistente con sus imágenes")
            elif info["status"] != "complete":
                raise ValueError(f"Consulta incompleta: {query}")
    expected_state = "incomplete_images" if pending else "complete"
    if manifest["status"] != expected_state:
        raise ValueError("Estado global inconsistente")
    if pending and require_images:
        raise ValueError(f"Q2 INCOMPLETA: faltan bytes de {pending} registros; ejecutar capture-images")
    return {"status": manifest["status"], "clients": len(manifest["clients"]),
            "input_rows": inputs["selected_rows"], "q2_pending_records": pending}


def capture_images(output, timeout=30, max_bytes=64 * 1024 * 1024):
    """Captura manual explícita: una descarga serial por URL, sin reintentos."""
    output = Path(output)
    verify_bundle(output, require_images=False)
    manifest = json.loads((output / "manifest.json").read_text())
    blobs = output / "images"
    blobs.mkdir(exist_ok=True)
    captured = {}
    for client in manifest["clients"]:
        for row in read_jsonl(output / client["queries"]["q2"]["path"]):
            image = row["image"]
            if image and image["status"] == "available":
                captured[image["source_url"]] = image
    for client in manifest["clients"]:
        info = client["queries"]["q2"]
        rows = read_jsonl(output / info["path"])
        error = None
        for row in rows:
            image = row["image"]
            if image is None or image["status"] == "available":
                continue
            url = image["source_url"]
            try:
                if url not in captured:
                    if urlsplit(url).scheme != "https":
                        raise ValueError("Se esperaba una URL HTTPS original")
                    request = Request(url, headers={
                        "User-Agent": "WikiAnalyticsSerialOracle/1.0 (educational reference capture)",
                        "Accept-Encoding": "identity"})
                    temporary = blobs / "download.part"
                    try:
                        with urlopen(request, timeout=timeout) as response, temporary.open("wb") as target:
                            if urlsplit(response.url).scheme != "https":
                                raise ValueError("Redirección sin HTTPS")
                            length = 0
                            while chunk := response.read(128 * 1024):
                                length += len(chunk)
                                if length > max_bytes:
                                    raise ValueError(f"Imagen excede el límite de {max_bytes} bytes")
                                target.write(chunk)
                            mime = response.headers.get_content_type()
                            if not length or (not mime.startswith("image/") and
                                              mime != "application/octet-stream"):
                                raise ValueError(f"Respuesta no válida como imagen: {mime}, {length} bytes")
                            headers = {key: response.headers.get(key) for key in
                                       ["ETag", "Last-Modified", "Content-Type"]}
                            final_url = response.url
                        sha = digest(temporary)
                        blob = blobs / f"{sha}.bin"
                        temporary.replace(blob)
                    finally:
                        temporary.unlink(missing_ok=True)
                    captured[url] = {"source_url": url, "status": "available",
                                     "path": blob.relative_to(output).as_posix(),
                                     "sha256": sha, "bytes": length, "resolved_url": final_url,
                                     "captured_at": datetime.now(timezone.utc).isoformat(),
                                     "http_headers": headers}
                    print(f"Imagen {len(captured)}: {length} bytes", flush=True)
                row["image"] = captured[url]
            except (OSError, ValueError) as exc:
                error = {"source_url": url, "error": str(exc),
                         "at": datetime.now(timezone.utc).isoformat()}
                break
        path = output / info["path"]
        write_jsonl(path, rows)
        info["sha256"] = digest(path)
        info["status"] = ("incomplete_images" if any(
            r["image"] and r["image"]["status"] != "available" for r in rows) else "complete")
        manifest["image_capture_error"] = error
        finish_bundle(output, manifest)
        if error:
            raise RuntimeError(f"Q2 sigue incompleta; descarga detenida: {error}")
    return verify_bundle(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("verify", help="Verificar archivos sin regenerar resultados")
    check.add_argument("output", type=Path)
    check.add_argument("--dataset", type=Path)
    check.add_argument("--allow-incomplete-q2", action="store_true")
    capture = sub.add_parser("capture-images", help="Descargar explícitamente imágenes originales de Q2")
    capture.add_argument("output", type=Path)
    capture.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    try:
        result = (capture_images(args.output, args.timeout) if args.command == "capture-images" else
                  verify_bundle(args.output, args.dataset, not args.allow_incomplete_q2))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()

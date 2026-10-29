"""Oráculo serial independiente de Go. La generación se inicia desde el notebook."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import dotenv_values

RESOURCES = Path(__file__).parent / "resources"
WORD_REGEX = r"\b\w+\b"
NUMBER_REGEX = r"[+-]?((\d+\.?\d*)|(\.\d+))"
FIELDS = ["name", "url", "identifier", "date_modified", "in_language",
          "abstract", "sections", "image"]
MAX_IMAGE_BYTES = 64 * 1024 * 1024
IMAGE_MODES = ("defer", "network", "fixture")


def validate_image_mode(mode, image_file=None):
    if mode not in IMAGE_MODES:
        raise ValueError(f"Modo de imágenes inválido: {mode}")
    if mode != "fixture":
        if image_file is not None:
            raise ValueError("image_file requiere image_mode=fixture")
        return None
    if image_file is None:
        raise ValueError("image_mode=fixture requiere image_file")
    path = Path(image_file).resolve()
    if not path.is_file():
        raise ValueError(f"Imagen fixture inexistente o no regular: {path}")
    with path.open("rb"):
        if not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
            raise ValueError("La imagen fixture debe tener entre 1 byte y 64 MiB")
    return path


def notebook_config(root, env=None, **overrides):
    """CLI explícita > entorno > defaults; configuración común con Jupyter."""
    env = os.environ if env is None else env
    if "WIKI_ORACLE_DOWNLOAD_IMAGES" in env:
        raise ValueError("WIKI_ORACLE_DOWNLOAD_IMAGES fue retirado; usar WIKI_ORACLE_IMAGE_MODE")
    root = Path(root)
    defaults = {"dataset": root / "dataset", "clients": 5,
                "output": root / "tests/expected/full-5clients-v1",
                "rows_per_file": None, "image_mode": "defer", "image_file": None}
    config = {key: overrides.get(key) if overrides.get(key) is not None else
              env.get(f"WIKI_ORACLE_{key.upper()}") or default
              for key, default in defaults.items()}
    for key in ("clients", "rows_per_file"):
        if config[key] is not None:
            config[key] = int(config[key])
            if config[key] < 1:
                raise ValueError(f"{key} debe ser positivo")
    for key in ("dataset", "output"):
        config[key] = Path(config[key]).resolve()
    if not config["dataset"].is_dir():
        raise ValueError(f"Dataset inexistente: {config['dataset']}")
    config["image_file"] = validate_image_mode(config["image_mode"], config["image_file"])
    return config


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def capture_user_agent(env_file=None):
    """El contacto sale del .env local o del entorno; nunca se escribe en artefactos."""
    config = dotenv_values(env_file or Path(__file__).resolve().parents[2] / ".env",
                           interpolate=False)
    name = os.environ.get("WIKIMEDIA_OPERATOR_NAME", config.get("WIKIMEDIA_OPERATOR_NAME") or "").strip()
    email = os.environ.get("WIKIMEDIA_OPERATOR_EMAIL", config.get("WIKIMEDIA_OPERATOR_EMAIL") or "").strip()
    if (not name or not email or any(ord(c) < 32 or ord(c) == 127 for c in name + email)
            or parseaddr(email)[1] != email or "@" not in email):
        raise ValueError("Configurar WIKIMEDIA_OPERATOR_NAME y WIKIMEDIA_OPERATOR_EMAIL válidos en .env")
    return f"WikiAnalyticsSerialOracle/1.0 ({name}; mailto:{email})"


def retry_after_deadline(value, now):
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        try:
            return now + timedelta(seconds=int(value))
        except OverflowError:
            return None
    try:
        date = parsedate_to_datetime(value)
        return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
    except (ValueError, TypeError, OverflowError):
        return None


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


def verify_image(output, image):
    """La referencia del escenario, no el índice de URLs, fija los bytes esperados."""
    blob = Path(output) / image["path"]
    if digest(blob) != image["sha256"] or blob.stat().st_size != image["bytes"]:
        raise ValueError(f"Imagen modificada: {blob}")
    return blob


def load_image_index(blobs):
    path = blobs / "index.json"
    index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(index, dict):
        raise ValueError("Índice de imágenes inválido")
    for url, image in index.items():
        if (not isinstance(image, dict) or image.get("source_url") != url
                or image.get("status") != "available"
                or not isinstance(image.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", image["sha256"])
                or image.get("path") != f"../images/{image['sha256']}.bin"
                or type(image.get("bytes")) is not int or image["bytes"] <= 0):
            raise ValueError(f"Entrada inválida en el índice de imágenes: {url}")
    return index


def write_image_index(blobs, index):
    """Una sola captura a la vez; reemplazar el índice sólo cuando esté completo."""
    temporary = blobs / "index.json.tmp"
    try:
        write_json(temporary, dict(sorted(index.items())))
        temporary.replace(blobs / "index.json")
    finally:
        temporary.unlink(missing_ok=True)


def store_image(output, source, image):
    """Una copia por contenido, compartida por los escenarios hermanos."""
    if not re.fullmatch(r"[0-9a-f]{64}", image["sha256"]):
        raise ValueError("SHA-256 de imagen inválido")
    shared = {**image, "path": f"../images/{image['sha256']}.bin"}
    blob = Path(output) / shared["path"]
    blob.parent.mkdir(parents=True, exist_ok=True)
    if blob.exists():
        verify_image(output, shared)  # Nunca reemplazar contenido ya capturado.
    else:
        os.link(source, blob)
    return shared


def create_bundle(output, inputs, notebook):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)  # Nunca sobreescribir referencias existentes.
    (output / "generator").mkdir()
    shutil.copy2(__file__, output / "generator" / "reference.py")
    nb = json.loads(Path(notebook).read_text(encoding="utf-8"))
    source = [{"cell_type": c["cell_type"], "source": c["source"]} for c in nb["cells"]]
    manifest = {
        "format_version": 1, "status": "generating", "input": inputs,
        "semantics": contract(), "created_at": datetime.now(timezone.utc).isoformat(),
        "generator": {"notebook_source_sha256": hashlib.sha256(
            json.dumps(source, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "reference_sha256": digest(__file__),
            "reference_snapshot_path": "generator/reference.py", "python": platform.python_version(),
            "packages": {name: importlib.metadata.version(name) for name in
                         ["pyarrow", "nbformat", "nbclient", "ipykernel", "python-dotenv"]}},
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
    source = manifest["generator"].get("reference_snapshot_path")
    if source and digest(output / source) != manifest["generator"]["reference_sha256"]:
        raise ValueError("Fuente archivada del generador modificada")
    if manifest["semantics"] != contract():
        raise ValueError("Contrato o stopwords incompatibles")
    inputs = manifest["input"]
    if dataset is not None:
        for file in inputs["files"]:
            if digest(Path(dataset) / file["path"]) != file["sha256"]:
                raise ValueError(f"Entrada modificada: {file['path']}")
    if len(manifest["clients"]) != inputs["clients"]:
        raise ValueError("Faltan clientes")
    pending = not_found = 0
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
                query_pending = query_not_found = 0
                for record in records:
                    image = record["image"]
                    if image is None:
                        continue
                    if image["status"] == "pending":
                        query_pending += 1
                        continue
                    if image["status"] == "not_found":
                        if image.get("error", {}).get("http_status") != 404:
                            raise ValueError("Imagen not_found sin diagnóstico HTTP 404")
                        query_not_found += 1
                        continue
                    if image["status"] != "available":
                        raise ValueError(f"Estado de imagen inválido: {image['status']}")
                    verify_image(output, image)
                pending += query_pending
                not_found += query_not_found
                expected = "incomplete_images" if query_pending or query_not_found else "complete"
                if info["status"] != expected:
                    raise ValueError("Estado de Q2 inconsistente con sus imágenes")
            elif info["status"] != "complete":
                raise ValueError(f"Consulta incompleta: {query}")
    log = manifest.get("image_404_log")
    if log:
        if (digest(output / log["path"]) != log["sha256"] or
                read_jsonl(output / log["path"]) != manifest["image_404_errors"]):
            raise ValueError("Registro de errores HTTP 404 modificado")
    expected_state = "incomplete_images" if pending or not_found else "complete"
    if manifest["status"] != expected_state:
        raise ValueError("Estado global inconsistente")
    if (pending or not_found) and require_images:
        raise ValueError(f"Q2 INCOMPLETA: {pending} pendientes y {not_found} con HTTP 404")
    return {"status": manifest["status"], "clients": len(manifest["clients"]),
            "input_rows": inputs["selected_rows"], "q2_pending_records": pending,
            "q2_not_found_records": not_found}


def handle_images(output, mode="defer", image_file=None):
    """Resuelve Q2 con una política explícita, sin fallback entre modos."""
    image_file = validate_image_mode(mode, image_file)
    output = Path(output)
    verify_bundle(output, require_images=False)
    manifest = json.loads((output / "manifest.json").read_text())
    if mode == "fixture":
        # No sustituir capturas ni ocultar errores anteriores.
        for client in manifest["clients"]:
            for row in read_jsonl(output / client["queries"]["q2"]["path"]):
                if row["image"] is not None and row["image"]["status"] != "pending":
                    raise ValueError("fixture sólo puede completar imágenes pending")
        blobs = output.parent / "images"
        blobs.mkdir(exist_ok=True)
        # store_image enlaza su fuente: usar una copia temporal independiente
        # para que editar el fixture no modifique las referencias congeladas.
        with tempfile.TemporaryDirectory(prefix=".fixture-", dir=blobs) as temporary:
            source = Path(temporary) / "image"
            shutil.copyfile(image_file, source)
            validate_image_mode(mode, source)
            image = store_image(output, source, {
                "status": "available", "sha256": digest(source),
                "bytes": source.stat().st_size, "provenance": "synthetic_fixture"})
        for client in manifest["clients"]:
            info = client["queries"]["q2"]
            path = output / info["path"]
            rows = read_jsonl(path)
            for row in rows:
                if row["image"] is not None:
                    row["image"] = {**image, "source_url": row["image"]["source_url"]}
            write_jsonl(path, rows)
            info.update(sha256=digest(path), status="complete")
        manifest["image_handling"] = {"mode": mode, "sha256": image["sha256"],
                                      "bytes": image["bytes"]}
        # No indexar URLs: estos bytes sintéticos no son capturas de red.
    else:
        manifest["image_handling"] = {"mode": mode}
    finish_bundle(output, manifest)
    if mode == "network":
        return capture_images(output)
    return verify_bundle(output, require_images=mode == "fixture")


def require_network_image(image):
    if image.get("provenance") == "synthetic_fixture":
        raise ValueError("network no puede reutilizar bytes synthetic_fixture")


def capture_images(output, timeout=30, max_bytes=MAX_IMAGE_BYTES, interval=3):
    """Captura serial: registra y salta 404; otros errores detienen, sin reintentos."""
    output = Path(output)
    verify_bundle(output, require_images=False)
    manifest = json.loads((output / "manifest.json").read_text())
    if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(interval) or interval < 0:
        raise ValueError("timeout debe ser positivo e interval finito y no negativo")
    previous = manifest.get("image_capture_error") or {}
    not_before = previous.get("retry_not_before")
    if not_before and datetime.now(timezone.utc) < datetime.fromisoformat(not_before):
        raise RuntimeError(f"Respetar Retry-After: no solicitar antes de {not_before}")
    user_agent = None  # El contacto sólo hace falta al realizar solicitudes de red.
    session = {"started_at": datetime.now(timezone.utc).isoformat(),
               "attempted": 0, "downloaded": 0, "reused_from_store": 0,
               "not_found": 0, "timeout_seconds": timeout,
               "interval_seconds": interval, "source_sha256": digest(__file__),
               "uv_lock_sha256": digest(Path(__file__).parent / "uv.lock")
               if (Path(__file__).parent / "uv.lock").exists() else None}
    manifest.setdefault("image_capture_sessions", []).append(session)
    next_request = None
    blobs = output.parent / "images"
    blobs.mkdir(parents=True, exist_ok=True)
    image_index = load_image_index(blobs)
    captured = {}
    unavailable = {}
    for client in manifest["clients"]:
        for row in read_jsonl(output / client["queries"]["q2"]["path"]):
            image = row["image"]
            if image and image["status"] == "available":
                require_network_image(image)
                captured[image["source_url"]] = image
            elif image and image["status"] == "not_found":
                unavailable[image["source_url"]] = image
    session["previously_available_urls"] = len(captured)
    for client_index, client in enumerate(manifest["clients"]):
        info = client["queries"]["q2"]
        rows = read_jsonl(output / info["path"])
        error = None
        for row in rows:
            image = row["image"]
            if image is None or image["status"] in ("available", "not_found"):
                continue
            url = image["source_url"]
            if url in unavailable:
                row["image"] = unavailable[url]
                continue
            try:
                if url not in captured and url in image_index:
                    require_network_image(image_index[url])
                    verify_image(output, image_index[url])
                    captured[url] = image_index[url]
                    session["reused_from_store"] += 1
                if url not in captured:
                    if urlsplit(url).scheme != "https":
                        raise ValueError("Se esperaba una URL HTTPS original")
                    if user_agent is None:
                        user_agent = capture_user_agent()
                    request = Request(url, headers={
                        "User-Agent": user_agent,
                        "Accept-Encoding": "identity"})
                    if next_request is not None:
                        delay = next_request - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                    session["attempted"] += 1
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
                        image = {"source_url": url, "status": "available",
                                 "sha256": sha, "bytes": length, "resolved_url": final_url,
                                 "captured_at": datetime.now(timezone.utc).isoformat(),
                                 "http_headers": headers}
                        captured[url] = store_image(output, temporary, image)
                        image_index.setdefault(url, captured[url])
                        write_image_index(blobs, image_index)
                    finally:
                        temporary.unlink(missing_ok=True)
                    session["downloaded"] += 1
                    next_request = time.monotonic() + interval
                    print(f"Imagen {len(captured)}: {length} bytes", flush=True)
                row["image"] = captured[url]
            except (OSError, ValueError) as exc:
                failure = {"source_url": url, "error": str(exc),
                           "at": datetime.now(timezone.utc).isoformat()}
                if isinstance(exc, HTTPError):
                    failure["http_status"] = exc.code
                    failure["retry_after"] = exc.headers.get("Retry-After") if exc.headers else None
                    deadline = retry_after_deadline(failure["retry_after"], datetime.now(timezone.utc))
                    if deadline:
                        failure["retry_not_before"] = deadline.isoformat()
                    exc.close()
                    if exc.code == 404:
                        row["image"] = {"source_url": url, "status": "not_found", "error": failure}
                        unavailable[url] = row["image"]
                        manifest.setdefault("image_404_errors", []).append(failure)
                        session["not_found"] += 1
                        next_request = time.monotonic() + interval
                        print(f"HTTP 404 registrado; continúa la captura: {url}", flush=True)
                        continue
                error = failure
                session["error"] = error
                break
        path = output / info["path"]
        write_jsonl(path, rows)
        info["sha256"] = digest(path)
        info["status"] = ("incomplete_images" if any(
            r["image"] and r["image"]["status"] != "available" for r in rows) else "complete")
        manifest["image_capture_error"] = error
        if manifest.get("image_404_errors"):
            log_path = output / "image-404-errors.jsonl"
            write_jsonl(log_path, manifest["image_404_errors"])
            manifest["image_404_log"] = {"path": log_path.name, "sha256": digest(log_path)}
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        if error or client_index == len(manifest["clients"]) - 1:
            session["finished_at"] = session["updated_at"]
        finish_bundle(output, manifest)
        if error:
            raise RuntimeError(f"Q2 sigue incompleta; descarga detenida: {error}")
    # Haber agotado las descargas pendientes no convierte los 404 en referencias completas.
    return verify_bundle(output, require_images=False)


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
    capture.add_argument("--interval", type=float, default=3,
                         help="Pausa mínima entre descargas nuevas, en segundos (default: 3)")
    args = parser.parse_args()
    try:
        result = (capture_images(args.output, args.timeout, interval=args.interval)
                  if args.command == "capture-images" else
                  verify_bundle(args.output, args.dataset, not args.allow_incomplete_q2))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()

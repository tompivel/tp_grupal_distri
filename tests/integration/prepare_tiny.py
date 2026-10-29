"""Preparación manual e independiente de tiny; nunca se invoca desde el runner."""
import argparse
import json
import os
import shutil
import struct
import sys
import zlib
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "oracle"))
import reference
from run_notebook import execute_notebook
IMAGE_URL = "https://images.tiny.invalid/pixel.png"
VOCABULARY = "amber birch cedar dune ember fern grove hazel iris jade kelp lotus moss north opal pine quartz reed stone tide umber vale willow xenon yarrow zenith"


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0\xff")) + chunk(b"IEND", b""))


def rows(schema, client, language):
    historical = {
        "en": ["alpha alpha shared comet the", "alpha alpha shared comet the",
               "beta beta echo orbit and", "gamma gamma delta echo"],
        "fr": ["shared lune lune étoile le", "echo onde onde soleil et",
               "rivage rivage flocon flocon", "brume brume nuage nuage"],
    }
    average = 4 if client == 0 else 6
    abstracts = [text + (" plume plume" if client else "") for text in historical[language]]
    if language == "en":
        abstracts += [" ".join(["spark"] * (average + 1)), " ".join(["equal"] * average),
                      " ".join(["low"] * (average - 1)),
                      VOCABULARY + (" bridge" if client == 0 else " east")]
    else:
        abstracts += [" ".join(["wave"] * (average + 1)), " ".join(["egal"] * average),
                      " ".join(["bas"] * (average - 1)), "isole" if client == 0 else "bridge"]
    result = []
    for index, abstract in enumerate(abstracts):
        # en/1 deliberately repeats the complete en/0 occurrence.
        identity = 0 if language == "en" and index == 1 else index
        date = ("2020-12-31T23:59:59.999" if language == "en" else "2019-06-01T12:30:00.123") if index < 4 else "2021-01-01T00:00:00.000"
        section = ("Biography" if language == "en" else "Biographie") if index in (0, 1, 4) else ""
        if language == "en" and index == 3:
            section = "BIOGRAPHY"
        if index == 2:
            section = "Biography overview" if language == "en" else "Biographie annexe"
        image = {"content_url": IMAGE_URL, "height": 1, "width": 1} if index in ((0, 1, 4) if language == "en" else (0, 4)) else None
        row = dict.fromkeys(schema.names)
        row.update(name=f"tiny-{client}-{language}-{identity}", identifier=client * 100 + identity,
                   url=f"https://example.invalid/tiny/{client}/{language}/{identity}",
                   date_modified=datetime.fromisoformat(date), in_language={"identifier": language},
                   abstract=abstract, sections=json.dumps([{"name": section}] if section else []), image=image)
        result.append(row)
    return result


def prepare(fixtures, output):
    if fixtures.exists() or output.exists():
        raise ValueError("Usar destinos nuevos; no sobrescribir escenarios existentes")
    fixtures.mkdir(parents=True)
    for language in ("en", "fr"):
        schema_path = ROOT / "dataset" / f"{language}wiki" / "schema.json"
        metadata = json.loads(schema_path.read_text())
        schema = pa.ipc.read_schema(pa.BufferReader(bytes.fromhex(metadata["arrow_ipc_hex"])))
        language_dir = fixtures / f"{language}wiki"
        (language_dir / "data").mkdir(parents=True)
        shutil.copy2(schema_path, language_dir / "schema.json")
        clients = [rows(schema, client, language) for client in range(2)]
        # Each file has 16 rows; (global_offset + physical_row) % 2 selects client.
        interleaved = [clients[client][index] for index in range(8) for client in range(2)]
        pq.write_table(pa.Table.from_pylist(interleaved, schema=schema),
                       language_dir / "data" / f"{language}wiki_namespace_0_00000.parquet")
    services = fixtures / "services"
    services.mkdir()
    (services / "pixel.png").write_bytes(png())
    (services / "metadata.json").write_text(json.dumps({"query": {"pages": [{
        "pageid": 1, "title": "File:Tiny.png", "imageinfo": [{"url": IMAGE_URL,
        "mime": "image/png", "width": 1, "height": 1}]}]}}, indent=2) + "\n")


    execute_notebook(output=output, dataset=fixtures, clients=2,
                     image_mode="fixture", image_file=services / "pixel.png",
                     env={**os.environ, "WIKI_ORACLE_ROWS_PER_FILE": ""})
    manifest = json.loads((output / "manifest.json").read_text())
    manifest["scenario"] = output.name
    manifest["synthetic"] = True
    manifest["fixture_files"] = {str(p.relative_to(fixtures)): reference.digest(p)
                                 for p in sorted(fixtures.rglob("*")) if p.is_file()}
    manifest["integration"] = {"status": "pending", "required_queries": [1, 2, 3, 4, 5],
        "blockers": ["Ingesta completa y captura Q1–Q5 del cliente oficial",
                     "Disponibilidad y cierres de todas las etapas Q1–Q5",
                     "Agregación de los cinco cierres en ResultCollector",
                     "Endpoint local de metadatos/contenido compatible con ImageFetcher",
                     "Evidencia de solapamiento y formato de captura de cierres"]}
    recipe = Path(__file__).resolve()
    shutil.copy2(recipe, output / "generator" / "prepare_tiny.py")
    manifest["generator"].update(preparation_snapshot_path="generator/prepare_tiny.py",
                                 preparation_sha256=reference.digest(recipe))
    reference.finish_bundle(output, manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=ROOT / "tests/fixtures/tiny-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "tests/expected/tiny-v1")
    args = parser.parse_args()
    prepare(args.fixtures.resolve(), args.output.resolve())

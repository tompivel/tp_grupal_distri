"""Verifica tiny sin Docker. La ejecución integral espera los contratos pendientes."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "oracle"))
import reference

FIXTURES = ROOT / "tests" / "fixtures" / "tiny-v1"
EXPECTED = ROOT / "tests" / "expected" / "tiny-v1"


def check():
    result = reference.verify_bundle(EXPECTED, FIXTURES)
    manifest = json.loads((EXPECTED / "manifest.json").read_text())
    if manifest.get("scenario") != "tiny-v1" or manifest.get("synthetic") is not True:
        raise ValueError("Se esperaba el escenario sintético tiny-v1")
    if manifest["integration"]["required_queries"] != list(range(1, 6)):
        raise ValueError("tiny requiere las cinco consultas")
    for name, digest in manifest["fixture_files"].items():
        if reference.digest(FIXTURES / name) != digest:
            raise ValueError(f"Fixture modificada: {name}")
    recipe = manifest["generator"]
    if reference.digest(EXPECTED / recipe["preparation_snapshot_path"]) != recipe["preparation_sha256"]:
        raise ValueError("Preparador archivado modificado")
    return {"scenario": "tiny-v1", "references": result, "integration": manifest["integration"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Auditar fixtures y referencias; no ejecutar el sistema")
    args = parser.parse_args(argv)
    try:
        result = check()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.check:
            parser.exit(2, "Integración tiny pendiente. No se invocó Docker; ver tests/integration/README.md.\n")
    except (OSError, ValueError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()

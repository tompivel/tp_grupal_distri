"""Ejecución manual del notebook para generar resultados esperados; las pruebas automatizadas no ejecutan este script."""

import argparse
import os
import sys
import tempfile
from pathlib import Path

import nbformat
from jupyter_client import AsyncKernelManager
from nbclient import NotebookClient


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directorio nuevo donde guardar las referencias",
    )
    parser.add_argument(
        "--rows-per-file", type=int, help="Limitar filas por archivo para un piloto"
    )
    parser.add_argument("--download-images", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error(
            "El destino ya existe. Usar otro para no sobreescribir referencias."
        )
    if args.rows_per_file is not None and args.rows_per_file < 1:
        parser.error("--rows-per-file debe ser positivo")
    notebook = nbformat.read(root / "wikipedia-article-analysis.ipynb", as_version=4)
    env = dict(os.environ)
    env["WIKI_ORACLE_OUTPUT"] = str(output)
    env["WIKI_ORACLE_ROWS_PER_FILE"] = str(args.rows_per_file or "")
    env["WIKI_ORACLE_DOWNLOAD_IMAGES"] = "1" if args.download_images else "0"
    with tempfile.TemporaryDirectory(prefix="wiki-oracle-kernel-") as runtime:
        env["IPYTHONDIR"] = str(Path(runtime) / "ipython")
        manager = AsyncKernelManager(
            kernel_name="python3", connection_file=str(Path(runtime) / "kernel.json")
        )
        manager.kernel_spec.argv = [
            sys.executable,
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ]
        client = NotebookClient(
            notebook,
            km=manager,
            timeout=1800,
            resources={"metadata": {"path": str(root)}},
            on_cell_executed=lambda cell_index, **_: print(
                f"Celda {cell_index} completada", flush=True
            ),
        )
        try:
            client.execute(env=env, cleanup_kc=True)
        finally:
            if output.is_dir():
                nbformat.write(notebook, output / "executed.ipynb")
    print(f"Notebook ejecutado: {output / 'executed.ipynb'}", flush=True)


if __name__ == "__main__":
    main()

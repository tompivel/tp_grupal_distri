"""Ejecución manual del notebook común; no se invoca desde el runner de integración."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

import nbformat
from jupyter_client import AsyncKernelManager
from nbclient import NotebookClient

import reference

ROOT = Path(__file__).resolve().parents[2]


def execute_notebook(*, output, dataset=None, clients=None, rows_per_file=None,
                     image_mode=None, image_file=None, env=None):
    env = dict(os.environ if env is None else env)
    config = reference.notebook_config(
        ROOT, env, output=output, dataset=dataset, clients=clients,
        rows_per_file=rows_per_file, image_mode=image_mode, image_file=image_file)
    output = config["output"]
    if output.exists():
        raise ValueError("El destino ya existe. Usar otro para no sobreescribir referencias.")
    for key, value in config.items():
        env[f"WIKI_ORACLE_{key.upper()}"] = str(value) if value is not None else ""
    notebook = nbformat.read(ROOT / "wikipedia-article-analysis.ipynb", as_version=4)
    with tempfile.TemporaryDirectory(prefix="wiki-oracle-kernel-") as runtime:
        env["IPYTHONDIR"] = str(Path(runtime) / "ipython")
        manager = AsyncKernelManager(
            kernel_name="python3", connection_file=str(Path(runtime) / "kernel.json"))
        manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        client = NotebookClient(
            notebook, km=manager, timeout=1800,
            resources={"metadata": {"path": str(ROOT)}},
            on_cell_executed=lambda cell_index, **_: print(f"Celda {cell_index} completada", flush=True))
        try:
            client.execute(env=env, cleanup_kc=True)
        finally:
            if output.is_dir():
                nbformat.write(notebook, output / "executed.ipynb")
    print(f"Notebook ejecutado: {output / 'executed.ipynb'}", flush=True)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    argv = sys.argv[1:] if argv is None else argv
    if "--download-images" in argv:
        parser.error("--download-images fue retirado; usar --image-mode network")
    parser.add_argument("--output", type=Path, required=True, help="Directorio nuevo para las referencias")
    parser.add_argument("--dataset", type=Path, help="Raíz de Parquet; por defecto dataset/")
    parser.add_argument("--clients", type=int, help="Cantidad de clientes; por defecto 5")
    parser.add_argument("--rows-per-file", type=int, help="Limitar filas por archivo")
    parser.add_argument("--image-mode", choices=reference.IMAGE_MODES, help="defer (default), network o fixture")
    parser.add_argument("--image-file", type=Path, help="Archivo local obligatorio sólo para fixture")
    args = parser.parse_args(argv)
    try:
        execute_notebook(**vars(args))
    except (OSError, ValueError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Empaquetar, descargar, instalar y verificar una captura fija del dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "tompivel/tp_grupal_distri"
CHUNK = 1024 * 1024
ASSET_LIMIT = 2 * 1024**3


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(CHUNK):
            checksum.update(chunk)
    return checksum.hexdigest()


def payload_path(name):
    """Sólo rutas relativas canónicas; nunca enlaces ni archivos de configuración."""
    if not isinstance(name, str) or not name or any(c in name for c in "\\:\x00"):
        raise ValueError(f"Ruta inválida: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
        raise ValueError(f"Ruta inválida: {name!r}")
    if path.suffix != ".parquet" and path.name != "schema.json":
        raise ValueError(f"Archivo fuera del dataset: {name}")
    return path


def plain_path(root, name):
    path = root
    if path.is_symlink():
        raise ValueError(f"No se admiten enlaces simbólicos: {path}")
    for part in payload_path(name).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"No se admiten enlaces simbólicos: {path}")
    return path


def inventory(root):
    if root.is_symlink():
        raise ValueError(f"No se admiten enlaces simbólicos: {root}")
    if not root.exists():
        return []
    if not root.is_dir():
        raise ValueError(f"No es un directorio: {root}")
    names = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"No se admiten enlaces simbólicos: {path}")
        if path.suffix == ".parquet" or path.name == "schema.json":
            name = path.relative_to(root).as_posix()
            payload_path(name)
            if not path.is_file():
                raise ValueError(f"No es un archivo regular: {path}")
            names.append(name)
    return names


def release_names(version, repository):
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", version):
        raise ValueError("La versión debe ser un tag simple, por ejemplo test-data-v1")
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("El repositorio debe tener formato OWNER/REPO")
    return f"dataset-{version}.tar"


def read_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["format_version"] != 1:
        raise ValueError("Versión de manifiesto no soportada")
    name = release_names(manifest["version"], manifest["repository"])
    archive = manifest["archive"]
    if archive["name"] != name:
        raise ValueError("El nombre del paquete no coincide con su versión")
    entries = manifest["files"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("El manifiesto no contiene archivos")
    names = set()
    for entry in [archive, *entries]:
        if type(entry["bytes"]) is not int or entry["bytes"] < 0:
            raise ValueError("Tamaño inválido en el manifiesto")
        if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("SHA-256 inválido en el manifiesto")
    for entry in entries:
        name = entry["path"]
        payload_path(name)
        if name in names:
            raise ValueError(f"Ruta duplicada en el manifiesto: {name}")
        names.add(name)
    if not any(name.endswith(".parquet") for name in names):
        raise ValueError("El manifiesto no contiene Parquet")
    return manifest


def matches(path, entry):
    return path.is_file() and path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"]


def inspect_local(dataset, manifest):
    """Devuelve faltantes; un conflicto o un archivo de datos extra siempre falla."""
    expected = {entry["path"]: entry for entry in manifest["files"]}
    extras = set(inventory(dataset)) - expected.keys()
    if extras:
        raise ValueError("Datos locales fuera del manifiesto: " + ", ".join(sorted(extras))
                         + ". Usar un destino nuevo con --dataset o guardar la captura anterior aparte.")
    missing = []
    for name, entry in expected.items():
        path = plain_path(dataset, name)
        if not path.exists():
            missing.append(name)
        elif not matches(path, entry):
            raise ValueError(f"Archivo local distinto: {path}. No se sobrescribe; usar otro --dataset.")
    return missing


class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.checksum = hashlib.sha256()

    def read(self, size):
        chunk = self.stream.read(size)
        self.checksum.update(chunk)
        return chunk


def pack(dataset, manifest_path, output_dir, version, repository):
    name = release_names(version, repository)
    previous = read_manifest(manifest_path) if manifest_path.exists() else None
    rebuilding = previous is not None and previous["version"] == version
    names = inventory(dataset)
    if not any(item.endswith(".parquet") for item in names):
        raise ValueError(f"No hay Parquet en {dataset}")
    if any(plain_path(dataset, item).resolve() == manifest_path.resolve() for item in names):
        raise ValueError("El manifiesto no puede reemplazar un archivo del dataset")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / name
    if archive_path.exists():
        raise ValueError(f"El paquete ya existe: {archive_path}. Elegir otra versión o directorio de salida.")
    with tempfile.TemporaryDirectory(prefix=".pack-", dir=output_dir) as temporary:
        staged = Path(temporary) / name
        entries = []
        with tarfile.open(staged, "w", format=tarfile.PAX_FORMAT) as archive:
            for item in names:
                path = plain_path(dataset, item)
                with path.open("rb") as source:
                    before = os.fstat(source.fileno())
                    reader = HashingReader(source)
                    info = tarfile.TarInfo(item)
                    info.size = before.st_size
                    info.mode = 0o644
                    archive.addfile(info, reader)
                    after = os.fstat(source.fileno())
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError(f"El archivo cambió mientras se empaquetaba: {path}")
                entries.append({"path": item, "bytes": info.size,
                                "sha256": reader.checksum.hexdigest()})
        if staged.stat().st_size >= ASSET_LIMIT:
            raise ValueError("El paquete alcanza 2 GiB, el límite por asset de la release. Dividir la captura.")
        manifest = {"format_version": 1, "version": version, "repository": repository,
                    "archive": {"name": name, "bytes": staged.stat().st_size,
                                "sha256": digest(staged)}, "files": entries}
        if rebuilding and manifest != previous:
            raise ValueError(f"La versión {version} ya está fijada y los datos o el paquete cambiaron. "
                             "Elegir un tag nuevo y conservar el anterior.")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        # Publicar sólo archivos terminados. No reemplazar un paquete anterior.
        os.link(staged, archive_path)
        if rebuilding:
            return archive_path, manifest  # El pin existente queda intacto.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=manifest_path.parent,
                                         prefix=".manifest-", delete=False) as stream:
            pending = Path(stream.name)
            try:
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.close()
                pending.replace(manifest_path)
            finally:
                pending.unlink(missing_ok=True)
    return archive_path, manifest


def unpack(archive_path, dataset, manifest):
    if not matches(archive_path, manifest["archive"]):
        raise ValueError(f"Paquete corrupto o de otra versión: {archive_path}")
    inspect_local(dataset, manifest)
    expected = {entry["path"]: entry for entry in manifest["files"]}
    dataset.parent.mkdir(parents=True, exist_ok=True)
    # El staging queda en el mismo filesystem para instalar sin sobrescrituras.
    with tempfile.TemporaryDirectory(prefix=".dataset-", dir=dataset.parent) as temporary:
        staging = Path(temporary)
        seen = set()
        with tarfile.open(archive_path, "r:") as archive:
            for member in archive:
                payload_path(member.name)
                if member.name in seen or member.name not in expected:
                    raise ValueError(f"Archivo duplicado o inesperado en el paquete: {member.name}")
                entry = expected[member.name]
                if member.type != tarfile.REGTYPE or member.size != entry["bytes"]:
                    raise ValueError(f"Tipo o tamaño inválido: {member.name}")
                target = staging / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, CHUNK)
                if not matches(target, entry):
                    raise ValueError(f"Contenido distinto del manifiesto: {member.name}")
                seen.add(member.name)
        if seen != expected.keys():
            raise ValueError("Faltan archivos en el paquete: " + ", ".join(sorted(expected.keys() - seen)))
        # Revisar otra vez antes de instalar; todos los bytes ya están validados.
        missing = inspect_local(dataset, manifest)
        for name in missing:
            target = plain_path(dataset, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(staging / name, target)
    return len(missing)


def download_asset(version, repository, name, directory):
    if not shutil.which("gh"):
        raise ValueError("Instalar GitHub CLI (gh) para descargar, o usar unpack con un paquete local.")
    subprocess.run(["gh", "release", "download", version, "--repo", repository,
                    "--pattern", name, "--dir", str(directory)], check=True)


def fetch_release_manifest(version, repository, cache_dir):
    """Obtener sólo el manifiesto pequeño; nunca modificar el pin del checkout."""
    release_names(version, repository)  # Validar antes de construir rutas o solicitar assets.
    directory = cache_dir / version
    manifest_path = directory / "manifest.json"

    def checked(path):
        manifest = read_manifest(path)
        if manifest["version"] != version or manifest["repository"] != repository:
            raise ValueError("El manifiesto no corresponde a la release y al repositorio solicitados. "
                             "Si pertenece a otro fork, usar otro --cache-dir.")
        return manifest

    if manifest_path.exists():
        return manifest_path, checked(manifest_path)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=directory) as temporary:
        download_asset(version, repository, "manifest.json", temporary)
        downloaded = Path(temporary) / "manifest.json"
        manifest = checked(downloaded)
        os.link(downloaded, manifest_path)
    return manifest_path, manifest


def fetch(dataset, manifest, cache_dir):
    if not inspect_local(dataset, manifest):
        print("El dataset local ya coincide; no se descarga nada.")
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = cache_dir / manifest["archive"]["name"]
    if not archive_path.exists():
        with tempfile.TemporaryDirectory(prefix=".download-", dir=cache_dir) as temporary:
            download_asset(manifest["version"], manifest["repository"], archive_path.name, temporary)
            downloaded = Path(temporary) / archive_path.name
            if not matches(downloaded, manifest["archive"]):
                raise ValueError("La descarga no coincide con el hash/tamaño del manifiesto.")
            os.link(downloaded, archive_path)
    installed = unpack(archive_path, dataset, manifest)
    print(f"Instalados {installed} archivos desde {archive_path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("pack", "fetch", "unpack", "verify"):
        help_text = {"pack": "Crear un paquete y fijar su manifiesto",
                     "fetch": "Descargar una release elegida o la fijada en el checkout",
                     "unpack": "Instalar un paquete local verificando su manifiesto",
                     "verify": "Verificar la captura local sin descargar"}[command]
        child = sub.add_parser(command, help=help_text)
        child.add_argument("--dataset", type=Path, default=ROOT / "dataset")
        if command == "fetch":
            source = child.add_mutually_exclusive_group()
            source.add_argument("--manifest", type=Path, default=ROOT / "dataset/manifest.json",
                                help="Manifiesto local; por defecto el fijado en el checkout")
            source.add_argument("--release", help="Tag a descargar; obtiene primero su manifest.json")
            child.add_argument("--repo", help=f"Repositorio de --release (default: {DEFAULT_REPO})")
        else:
            child.add_argument("--manifest", type=Path, default=ROOT / "dataset/manifest.json")
        if command == "pack":
            child.add_argument("--version", required=True, help="Tag nuevo, por ejemplo test-data-v1")
            child.add_argument("--repo", default=DEFAULT_REPO)
            child.add_argument("--output-dir", type=Path, default=ROOT / "dist/dataset")
        elif command == "unpack":
            child.add_argument("archive", type=Path)
        elif command == "fetch":
            child.add_argument("--cache-dir", type=Path, default=ROOT / "dist/dataset")
    args = parser.parse_args(argv)
    if args.command == "fetch" and args.repo is not None and args.release is None:
        parser.error("--repo en fetch requiere --release; un manifiesto local ya fija su repositorio")
    try:
        if args.command == "pack":
            archive, manifest = pack(args.dataset, args.manifest, args.output_dir, args.version, args.repo)
            print(f"Paquete: {archive} ({manifest['archive']['bytes']} bytes)")
            print(f"Manifiesto: {args.manifest} ({len(manifest['files'])} archivos)")
        else:
            if args.command == "fetch" and args.release is not None:
                manifest_path, manifest = fetch_release_manifest(
                    args.release, args.repo or DEFAULT_REPO, args.cache_dir)
                print(f"Manifiesto de la release: {manifest_path}")
            else:
                manifest = read_manifest(args.manifest)
            if args.command == "fetch":
                fetch(args.dataset, manifest, args.cache_dir)
            elif args.command == "unpack":
                count = unpack(args.archive, args.dataset, manifest)
                print(f"Instalados {count} archivos.")
            else:
                missing = inspect_local(args.dataset, manifest)
                if missing:
                    raise ValueError("Faltan archivos: " + ", ".join(missing))
            print(f"Dataset verificado: {manifest['version']} ({len(manifest['files'])} archivos).")
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()

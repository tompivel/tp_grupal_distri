"""Integridad, actualización e instalación sin red ni dependencias externas."""

from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dataset as ds


class DatasetReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.write("enwiki/data/enwiki_namespace_0_00000.parquet", b"PAR1-en-original")
        self.write("frwiki/data/frwiki_namespace_0_00000.parquet", b"PAR1-fr-original")
        self.write("enwiki/schema.json", b'{"language":"en"}\n')
        self.write("frwiki/schema.json", b'{"language":"fr"}\n')
        self.write("README.md", b"Documentacion local")
        self.write(".env", b"not part of the dataset")
        self.manifest_path = self.root / "manifest.json"
        self.output = self.root / "dist"
        self.archive, self.manifest = ds.pack(
            self.source, self.manifest_path, self.output, "test-data-v1", "owner/repo")
        self.target = self.root / "target"

    def write(self, name, data):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def forged_archive(self, members):
        """Hash exterior válido, para ejercitar las verificaciones interiores."""
        archive = self.root / "forged.tar"
        with tarfile.open(archive, "w") as stream:
            for name, content, kind in members:
                member = tarfile.TarInfo(name)
                member.type = kind
                if kind == tarfile.REGTYPE:
                    member.size = len(content)
                    stream.addfile(member, io.BytesIO(content))
                else:
                    member.linkname = "../../outside"
                    stream.addfile(member)
        manifest = deepcopy(self.manifest)
        manifest["archive"].update(bytes=archive.stat().st_size, sha256=ds.digest(archive))
        return archive, manifest

    def test_roundtrip_preserves_bytes_metadata_and_local_documentation(self):
        self.target.mkdir()
        readme = self.target / "README.md"
        readme.write_text("conservar", encoding="utf-8")
        self.assertEqual(ds.unpack(self.archive, self.target, self.manifest), 4)
        self.assertEqual(ds.inspect_local(self.target, self.manifest), [])
        self.assertEqual(readme.read_text(), "conservar")
        self.assertFalse((self.target / ".env").exists())
        for entry in self.manifest["files"]:
            self.assertEqual((self.source / entry["path"]).read_bytes(),
                             (self.target / entry["path"]).read_bytes())
        self.assertEqual(ds.unpack(self.archive, self.target, self.manifest), 0)
        self.assertEqual(ds.read_manifest(self.manifest_path), self.manifest)

    def test_archive_is_deterministic(self):
        other, manifest = ds.pack(self.source, self.root / "other.json", self.root / "other",
                                  "test-data-v1", "owner/repo")
        self.assertEqual(ds.digest(other), ds.digest(self.archive))
        self.assertEqual(manifest, self.manifest)

    def test_new_version_discovers_added_parquet_and_retains_old_archive(self):
        before = ds.digest(self.archive)
        self.write("enwiki/data/enwiki_namespace_0_00005.parquet", b"new input")
        archive, manifest = ds.pack(self.source, self.manifest_path, self.output,
                                    "test-data-v2", "owner/repo")
        self.assertEqual(len(manifest["files"]), 5)
        self.assertEqual(ds.digest(self.archive), before)
        ds.unpack(archive, self.target, manifest)
        self.assertEqual(ds.inspect_local(self.target, manifest), [])
        self.assertEqual(ds.read_manifest(self.manifest_path)["version"], "test-data-v2")

    def test_same_version_and_existing_archive_are_not_replaced(self):
        before = self.manifest_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "paquete ya existe"):
            ds.pack(self.source, self.manifest_path, self.output, "test-data-v1", "owner/repo")
        with self.assertRaisesRegex(ValueError, "paquete ya existe"):
            ds.pack(self.source, self.root / "other.json", self.output, "test-data-v1", "owner/repo")
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_rebuild_pinned_version_without_changing_manifest(self):
        before = self.manifest_path.read_bytes()
        rebuilt, manifest = ds.pack(self.source, self.manifest_path, self.root / "rebuilt",
                                     "test-data-v1", "owner/repo")
        self.assertEqual(ds.digest(rebuilt), ds.digest(self.archive))
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_rebuild_pinned_version_rejects_changed_data(self):
        self.write("enwiki/data/enwiki_namespace_0_00005.parquet", b"new input")
        before = self.manifest_path.read_bytes()
        output = self.root / "rebuilt"
        with self.assertRaisesRegex(ValueError, "ya está fijada"):
            ds.pack(self.source, self.manifest_path, output, "test-data-v1", "owner/repo")
        self.assertFalse((output / self.archive.name).exists())
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_corrupt_archive_does_not_create_destination(self):
        with self.archive.open("ab") as stream:
            stream.write(b"corruption")
        with self.assertRaisesRegex(ValueError, "Paquete corrupto"):
            ds.unpack(self.archive, self.target, self.manifest)
        self.assertFalse(self.target.exists())

    def test_conflict_prevents_installing_even_missing_files(self):
        path = self.target / self.manifest["files"][-1]["path"]
        path.parent.mkdir(parents=True)
        path.write_bytes(b"local changes")
        with self.assertRaisesRegex(ValueError, "Archivo local distinto"):
            ds.unpack(self.archive, self.target, self.manifest)
        self.assertEqual(path.read_bytes(), b"local changes")
        self.assertEqual(ds.inventory(self.target), [self.manifest["files"][-1]["path"]])

    def test_extra_parquet_is_rejected_instead_of_mixing_versions(self):
        self.target.mkdir()
        (self.target / "extra.parquet").write_bytes(b"stale")
        with self.assertRaisesRegex(ValueError, "fuera del manifiesto"):
            ds.unpack(self.archive, self.target, self.manifest)

    def test_existing_matching_files_allow_partial_install(self):
        entry = self.manifest["files"][0]
        path = self.target / entry["path"]
        path.parent.mkdir(parents=True)
        shutil.copyfile(self.source / entry["path"], path)
        self.assertEqual(ds.unpack(self.archive, self.target, self.manifest), 3)

    def test_symlink_in_destination_or_source_is_rejected(self):
        self.target.mkdir()
        (self.target / "enwiki").symlink_to(self.source / "enwiki", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "enlaces simbólicos"):
            ds.unpack(self.archive, self.target, self.manifest)
        (self.source / "linked.parquet").symlink_to(self.source / self.manifest["files"][0]["path"])
        with self.assertRaisesRegex(ValueError, "enlaces simbólicos"):
            ds.pack(self.source, self.root / "new.json", self.output, "test-data-v2", "owner/repo")

    def test_invalid_manifest_paths_and_duplicates(self):
        for name in ("../outside.parquet", "/outside.parquet", "a/../outside.parquet",
                     "a\\outside.parquet", "a//outside.parquet", "./outside.parquet"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Ruta inválida"):
                ds.payload_path(name)
        manifest = deepcopy(self.manifest)
        manifest["files"].append(manifest["files"][0])
        self.manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "duplicada"):
            ds.read_manifest(self.manifest_path)

    def test_tar_traversal_links_duplicates_and_missing_files(self):
        name = self.manifest["files"][0]["path"]
        content = (self.source / name).read_bytes()
        cases = [([("../outside.parquet", b"outside", tarfile.REGTYPE)], "Ruta inválida"),
                 ([(name, b"", tarfile.SYMTYPE)], "Tipo o tamaño"),
                 ([(name, content, tarfile.REGTYPE)] * 2, "duplicado"),
                 ([(name, content, tarfile.REGTYPE)], "Faltan archivos"),
                 ([(name, b"X" * len(content), tarfile.REGTYPE)], "Contenido distinto"),
                 ([("unexpected.parquet", b"x", tarfile.REGTYPE)], "inesperado")]
        for members, error in cases:
            with self.subTest(error=error):
                archive, manifest = self.forged_archive(members)
                with self.assertRaisesRegex(ValueError, error):
                    ds.unpack(archive, self.target, manifest)
                self.assertFalse(self.target.exists())
                self.assertFalse((self.root / "outside.parquet").exists())

    def test_fetch_pins_tag_and_repo_then_skips_network_when_installed(self):
        calls = []

        def download(command, check):
            calls.append(command)
            self.assertTrue(check)
            self.assertEqual(command[:7], ["gh", "release", "download", "test-data-v1",
                                          "--repo", "owner/repo", "--pattern"])
            destination = Path(command[command.index("--dir") + 1]) / self.archive.name
            shutil.copyfile(self.archive, destination)

        with patch.object(ds.shutil, "which", return_value="gh"), \
                patch.object(ds.subprocess, "run", side_effect=download):
            ds.fetch(self.target, self.manifest, self.root / "cache")
            ds.fetch(self.target, self.manifest, self.root / "cache")
        self.assertEqual(len(calls), 1)
        self.assertEqual(ds.inspect_local(self.target, self.manifest), [])

    def test_corrupt_download_is_not_cached_or_installed(self):
        def download(command, check):
            target = Path(command[command.index("--dir") + 1]) / self.archive.name
            target.write_bytes(b"broken transfer")

        cache = self.root / "cache"
        with patch.object(ds.shutil, "which", return_value="gh"), \
                patch.object(ds.subprocess, "run", side_effect=download):
            with self.assertRaisesRegex(ValueError, "descarga no coincide"):
                ds.fetch(self.target, self.manifest, cache)
        self.assertEqual(list(cache.iterdir()), [])
        self.assertFalse(self.target.exists())

    def release_download(self, command, check):
        self.assertTrue(check)
        name = command[command.index("--pattern") + 1]
        directory = Path(command[command.index("--dir") + 1])
        source = self.manifest_path if name == "manifest.json" else self.archive
        self.assertEqual(source.name, name)
        shutil.copyfile(source, directory / name)

    def release_args(self, cache):
        return ["fetch", "--release", "test-data-v1", "--repo", "owner/repo",
                "--cache-dir", str(cache), "--dataset", str(self.target)]

    def test_release_with_installed_files_downloads_only_manifest_then_works_offline(self):
        ds.unpack(self.archive, self.target, self.manifest)
        cache = self.root / "cache"
        with patch.object(ds.shutil, "which", return_value="gh"), \
                patch.object(ds.subprocess, "run", side_effect=self.release_download) as download:
            ds.main(self.release_args(cache))
        self.assertEqual(download.call_count, 1)
        self.assertIn("manifest.json", download.call_args.args[0])
        self.assertFalse((cache / self.archive.name).exists())
        cached = cache / "test-data-v1/manifest.json"
        self.assertEqual(ds.read_manifest(cached), self.manifest)
        with patch.object(ds.shutil, "which", return_value=None), \
                patch.object(ds.subprocess, "run") as download:
            ds.main(self.release_args(cache))
            ds.main(["verify", "--manifest", str(cached), "--dataset", str(self.target)])
            download.assert_not_called()

    def test_release_fetch_gets_manifest_before_archive_without_reading_or_changing_git_pin(self):
        pinned = self.root / "dataset/manifest.json"
        pinned.parent.mkdir()
        pinned.write_text("Este archivo no se debe leer ni sobrescribir.\n")
        before = pinned.read_bytes()
        cache = self.root / "cache"
        with patch.object(ds, "ROOT", self.root), \
                patch.object(ds.shutil, "which", return_value="gh"), \
                patch.object(ds.subprocess, "run", side_effect=self.release_download) as download:
            ds.main(self.release_args(cache))
        calls = [call.args[0] for call in download.call_args_list]
        self.assertEqual([c[c.index("--pattern") + 1] for c in calls],
                         ["manifest.json", self.archive.name])
        for command in calls:
            self.assertEqual(command[3], "test-data-v1")
            self.assertEqual(command[command.index("--repo") + 1], "owner/repo")
        self.assertEqual(pinned.read_bytes(), before)
        self.assertEqual(ds.inspect_local(self.target, self.manifest), [])

    def test_release_fetch_uses_existing_tar_cache(self):
        cache = self.root / "cache"
        cache.mkdir()
        shutil.copyfile(self.archive, cache / self.archive.name)
        with patch.object(ds.shutil, "which", return_value="gh"), \
                patch.object(ds.subprocess, "run", side_effect=self.release_download) as download:
            ds.main(self.release_args(cache))
        self.assertEqual(download.call_count, 1)
        self.assertIn("manifest.json", download.call_args.args[0])
        self.assertEqual(ds.inspect_local(self.target, self.manifest), [])

    def test_release_upgrade_adds_files_without_replacing_existing_input(self):
        ds.unpack(self.archive, self.target, self.manifest)
        original = {entry["path"]: ds.digest(self.target / entry["path"])
                    for entry in self.manifest["files"]}
        self.write("enwiki/data/enwiki_namespace_0_00005.parquet", b"new input")
        self.archive, expanded = ds.pack(self.source, self.manifest_path, self.output,
                                         "test-data-v2", "owner/repo")
        cache = self.root / "cache"
        with patch.object(ds.shutil, "which", return_value="gh"), \
                patch.object(ds.subprocess, "run", side_effect=self.release_download) as download:
            ds.main(["fetch", "--release", "test-data-v2", "--repo", "owner/repo",
                     "--cache-dir", str(cache), "--dataset", str(self.target)])
        self.assertEqual(download.call_count, 2)
        self.assertEqual(ds.inspect_local(self.target, expanded), [])
        for name, checksum in original.items():
            self.assertEqual(ds.digest(self.target / name), checksum)

    def test_release_rejects_wrong_version_or_repo_before_caching_manifest(self):
        for i, (version, repository) in enumerate([
                ("other-version", "owner/repo"), ("test-data-v1", "other/repo")]):
            with self.subTest(version=version, repository=repository):
                remote = deepcopy(self.manifest)
                remote.update(version=version, repository=repository)
                remote["archive"]["name"] = f"dataset-{version}.tar"
                self.manifest_path.write_text(json.dumps(remote))
                cache = self.root / f"cache-{i}"
                with patch.object(ds.shutil, "which", return_value="gh"), \
                        patch.object(ds.subprocess, "run", side_effect=self.release_download) as download:
                    with self.assertRaisesRegex(ValueError, "no corresponde"):
                        ds.fetch_release_manifest("test-data-v1", "owner/repo", cache)
                self.assertEqual(download.call_count, 1)
                self.assertFalse((cache / "test-data-v1/manifest.json").exists())
                self.assertFalse(self.target.exists())

    def test_release_local_conflict_is_detected_before_downloading_archive(self):
        ds.unpack(self.archive, self.target, self.manifest)
        modified = self.target / self.manifest["files"][0]["path"]
        modified.write_bytes(b"local changes")
        cache = self.root / "cache"
        with patch.object(ds.shutil, "which", return_value="gh"), \
                patch.object(ds.subprocess, "run", side_effect=self.release_download) as download, \
                patch("sys.stderr", new_callable=io.StringIO) as errors:
            with self.assertRaises(SystemExit) as stopped:
                ds.main(self.release_args(cache))
        self.assertEqual(stopped.exception.code, 1)
        self.assertIn("Archivo local distinto", errors.getvalue())
        self.assertEqual(download.call_count, 1)
        self.assertIn("manifest.json", download.call_args.args[0])
        self.assertFalse((cache / self.archive.name).exists())
        self.assertEqual(modified.read_bytes(), b"local changes")

    def test_cached_release_cannot_be_reused_for_another_repo(self):
        cache = self.root / "cache"
        directory = cache / "test-data-v1"
        directory.mkdir(parents=True)
        shutil.copyfile(self.manifest_path, directory / "manifest.json")
        with patch.object(ds.subprocess, "run") as download:
            with self.assertRaisesRegex(ValueError, "no corresponde"):
                ds.fetch_release_manifest("test-data-v1", "other/repo", cache)
            download.assert_not_called()

    def test_release_tag_is_validated_before_network_or_cache_writes(self):
        cache = self.root / "cache"
        with patch.object(ds.subprocess, "run") as download:
            for version in ("../v1", "/v1", "", "a/b"):
                with self.subTest(version=version), self.assertRaisesRegex(ValueError, "tag simple"):
                    ds.fetch_release_manifest(version, "owner/repo", cache)
            download.assert_not_called()
        self.assertFalse(cache.exists())

    def test_release_and_local_manifest_are_mutually_exclusive(self):
        cache = self.root / "cache"
        for arguments in [self.release_args(cache) + ["--manifest", str(self.manifest_path)],
                          ["fetch", "--repo", "owner/repo"]]:
            with self.subTest(arguments=arguments), \
                    patch.object(ds.subprocess, "run") as download, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as stopped:
                    ds.main(arguments)
                self.assertEqual(stopped.exception.code, 2)
                download.assert_not_called()

    def test_empty_dataset_and_invalid_version_fail(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "No hay Parquet"):
            ds.pack(empty, self.root / "new.json", self.output, "test-data-v2", "owner/repo")
        with self.assertRaisesRegex(ValueError, "tag simple"):
            ds.pack(self.source, self.root / "new.json", self.output, "../v2", "owner/repo")


if __name__ == "__main__":
    unittest.main()

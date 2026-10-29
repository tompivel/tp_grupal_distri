"""Configuración común de notebook, CLI y preparación sintética."""
from pathlib import Path
from contextlib import redirect_stderr
import io
import tempfile
import unittest
from unittest.mock import patch

import reference as ref
import run_notebook


class NotebookConfiguration(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "dataset").mkdir()
        self.image = self.root / "image"
        self.image.write_bytes(b"fixture")

    def test_defaults_and_cli_precedence(self):
        config = ref.notebook_config(self.root, {})
        self.assertEqual(config["clients"], 5)
        self.assertEqual(config["dataset"], self.root / "dataset")
        self.assertIsNone(config["rows_per_file"])
        self.assertEqual(config["image_mode"], "defer")
        env = {"WIKI_ORACLE_CLIENTS": "3", "WIKI_ORACLE_ROWS_PER_FILE": "10",
               "WIKI_ORACLE_IMAGE_MODE": "fixture", "WIKI_ORACLE_IMAGE_FILE": str(self.image)}
        config = ref.notebook_config(self.root, env, clients=2, rows_per_file=4)
        self.assertEqual((config["clients"], config["rows_per_file"]), (2, 4))
        self.assertEqual(config["image_file"], self.image)
        self.assertEqual(ref.notebook_config(self.root, {"WIKI_ORACLE_CLIENTS": "3"})["clients"], 3)
        config = ref.notebook_config(self.root,
            {"WIKI_ORACLE_DATASET": str(self.root / "missing"), "WIKI_ORACLE_IMAGE_MODE": "network"},
            dataset=self.root / "dataset", image_mode="fixture", image_file=self.image)
        self.assertEqual(config["dataset"], self.root / "dataset")
        self.assertEqual(config["image_mode"], "fixture")

    def test_invalid_options(self):
        for options in ({"clients": 0}, {"clients": -1}, {"rows_per_file": 0},
                        {"image_mode": "unknown"}, {"image_mode": "fixture"},
                        {"image_mode": "fixture", "image_file": self.root / "missing"},
                        {"image_mode": "fixture", "image_file": self.root},
                        {"image_mode": "network", "image_file": self.image},
                        {"image_file": self.image}, {"dataset": self.root / "missing"}):
            with self.subTest(options=options), self.assertRaises((ValueError, OSError)):
                ref.notebook_config(self.root, {}, **options)
        for content_size in (0, ref.MAX_IMAGE_BYTES + 1):
            with self.image.open("wb") as target:
                target.truncate(content_size)
            with self.assertRaises(ValueError):
                ref.validate_image_mode("fixture", self.image)

    def test_legacy_options_fail_and_validation_precedes_kernel(self):
        with self.assertRaisesRegex(ValueError, "fue retirado"):
            ref.notebook_config(self.root, {"WIKI_ORACLE_DOWNLOAD_IMAGES": "0"})
        output = self.root / "output"
        with patch.object(run_notebook, "NotebookClient") as kernel:
            with self.assertRaises(ValueError):
                run_notebook.execute_notebook(output=output, dataset=self.root / "dataset", clients=0, env={})
            kernel.assert_not_called()
        self.assertFalse(output.exists())
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            run_notebook.main(["--output", str(output), "--download-images"])
        self.assertEqual(error.exception.code, 2)
        output.mkdir()
        with self.assertRaisesRegex(ValueError, "ya existe"):
            run_notebook.execute_notebook(output=output, dataset=self.root / "dataset", env={})

    def test_cli_passes_new_options_to_shared_executor(self):
        with patch.object(run_notebook, "execute_notebook") as execute:
            run_notebook.main(["--output", str(self.root / "output"), "--dataset", str(self.root / "dataset"), "--clients", "2", "--image-mode", "fixture", "--image-file", str(self.image)])
        self.assertEqual(execute.call_args.kwargs["clients"], 2)
        self.assertEqual(execute.call_args.kwargs["image_file"], self.image)

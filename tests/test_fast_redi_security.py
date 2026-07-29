import pickle
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fast_redi import SmartCachingRestorer


class ModelPathSecurityTests(unittest.TestCase):
    def make_restorer(self, model_dir: Path) -> SmartCachingRestorer:
        with patch.object(SmartCachingRestorer, "_start_cleanup_thread"):
            return SmartCachingRestorer(
                str(model_dir),
                preload_languages=["not-preloaded"],
            )

    def test_loads_allow_listed_model_from_model_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir) / "models"
            model_dir.mkdir()
            expected_lexicon = {"zeljko": {"željko": 1.0}}
            with (model_dir / "wikitweetweb.hr.tm").open("wb") as model_file:
                pickle.dump(expected_lexicon, model_file)

            restorer = self.make_restorer(model_dir)
            restorer._load_language("hr")

            self.assertEqual(restorer.lexicons["hr"], expected_lexicon)

    def test_rejects_path_traversal_language_before_reading_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            model_dir = temp_path / "models"
            model_dir.mkdir()

            # This directory makes the old constructed path resolvable:
            # models/wikitweetweb.../../../outside.tm
            (model_dir / "wikitweetweb...").mkdir()
            outside_model = temp_path / "outside.tm"
            with outside_model.open("wb") as model_file:
                pickle.dump({"outside": {"should-not-load": 1.0}}, model_file)

            restorer = self.make_restorer(model_dir)

            with self.assertRaisesRegex(ValueError, "Unsupported language"):
                restorer._load_language("../../../outside")

            self.assertEqual(restorer.lexicons, {})

    def test_rejects_model_symlink_that_escapes_model_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            model_dir = temp_path / "models"
            model_dir.mkdir()
            outside_model = temp_path / "outside.tm"
            with outside_model.open("wb") as model_file:
                pickle.dump({"outside": {"should-not-load": 1.0}}, model_file)
            (model_dir / "wikitweetweb.hr.tm").symlink_to(outside_model)

            restorer = self.make_restorer(model_dir)

            with self.assertRaisesRegex(ValueError, "escapes model directory"):
                restorer._load_language("hr")

            self.assertEqual(restorer.lexicons, {})


if __name__ == "__main__":
    unittest.main()

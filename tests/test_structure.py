from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from setup_project import create_structure
from run_pipeline import ensure_field_raw_available


class TestProjectStructure(unittest.TestCase):
    def test_expected_input_directories_are_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_structure(root)
            expected = [
                "data/raw/PASTO/Pluviometro",
                "data/raw/PASTO/Poço",
                "data/raw/SECUNDARIA/TMS",
                "data/raw/PRIMARIA/Termohigrometro",
                "data/external/ERA5",
                "data/external/INMET",
                "data/external/CHIRPS/sat/extracted",
                "data/external/CHIRPS/rnl/extracted",
                "data/processed/climate",
                "results/figures",
                "results/report",
            ]
            for rel in expected:
                self.assertTrue((root / rel).is_dir(), rel)

    def test_raw_preflight_rejects_empty_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_structure(root)
            with self.assertRaises(SystemExit):
                ensure_field_raw_available(root)

    def test_raw_preflight_accepts_sensor_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_structure(root)
            p = root / "data/raw/PASTO/Pluviometro/example.csv"
            p.write_text("x\n1\n", encoding="utf-8")
            ensure_field_raw_available(root)


if __name__ == "__main__":
    unittest.main()

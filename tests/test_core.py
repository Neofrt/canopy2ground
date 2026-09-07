from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_pipeline import merge_missing
from modules.integrate import DataIntegrityError, assert_unique, hydro_date_from_datetime
from modules.tms import discover, parse_datetime_utc_local


class TestConfigMerge(unittest.TestCase):
    def test_user_values_are_preserved(self):
        defaults = {"timezone": "America/Belem", "tms": {"timestamp_basis": "UTC", "x": 1}}
        current = {"timezone": "Custom/Zone", "tms": {"x": 99}}
        merged = merge_missing(defaults, current)
        self.assertEqual(merged["timezone"], "Custom/Zone")
        self.assertEqual(merged["tms"]["x"], 99)
        self.assertEqual(merged["tms"]["timestamp_basis"], "UTC")


class TestTimeConventions(unittest.TestCase):
    def test_tms_utc_to_belem(self):
        raw = pd.Series(["01.08.2026 15:30"])
        utc, local, offset = parse_datetime_utc_local(raw, "America/Belem")
        self.assertEqual(str(utc.iloc[0]), "2026-08-01 15:30:00+00:00")
        self.assertEqual(local.iloc[0], pd.Timestamp("2026-08-01 12:30:00"))
        self.assertEqual(float(offset.iloc[0]), -3.0)

    def test_hydrologic_noon_boundary(self):
        s = pd.Series(pd.to_datetime([
            "2026-08-01 11:30:00",
            "2026-08-01 12:00:00",
            "2026-08-01 12:30:00",
        ]))
        result = list(hydro_date_from_datetime(s))
        self.assertEqual(str(result[0]), "2026-08-01")
        self.assertEqual(str(result[1]), "2026-08-01")
        self.assertEqual(str(result[2]), "2026-08-02")


class TestIntegrityGuards(unittest.TestCase):
    def test_duplicate_key_is_rejected(self):
        df = pd.DataFrame({"datetime": ["a", "a"], "value": [1, 2]})
        with self.assertRaises(DataIntegrityError):
            assert_unique(df, ["datetime"], "synthetic")

    def test_empty_tms_discovery_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            selected, audit = discover(Path(tmp), None)
            self.assertEqual(selected, [])
            self.assertTrue(audit.empty)


if __name__ == "__main__":
    unittest.main()

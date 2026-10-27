from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_figures import _eligible_precip_months


class TestPrecipitationFigureCoverage(unittest.TestCase):
    def test_months_use_90_percent_coverage(self):
        monthly = pd.DataFrame({
            "source": ["ERA5-Land", "INMET", "ERA5-Land"],
            "calendar_days": [31, 31, 31],
            "n_field_valid_days": [29, 29, 20],
            "paired_field_coverage": [0.94, 0.91, 1.0],
            "month": ["2026-08", "2026-08", "2026-09"],
        })
        out = _eligible_precip_months(monthly, ["ERA5-Land", "INMET"], min_coverage=0.90)
        self.assertEqual(set(out["month"]), {"2026-08"})
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()

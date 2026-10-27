from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from scripts.generate_results_report import significance_label, significance_clause, fmt_signed, _difference_sentence


class TestDynamicReportLanguage(unittest.TestCase):
    def test_significance_is_not_hardcoded(self):
        self.assertEqual(significance_label(0.01), "significativa")
        self.assertEqual(significance_label(0.05), "não significativa")
        self.assertEqual(significance_label(0.20), "não significativa")
        self.assertEqual(significance_clause(0.01), "foi significativa")
        self.assertEqual(significance_clause(0.20), "não foi significativa")

    def test_difference_sentence_uses_current_p_value(self):
        row = pd.Series({"bias_ar1": 0.2, "p_holm_within_variable": 0.01})
        text = _difference_sentence("ERA5-Land", row, "°C")
        self.assertIn("foi significativa", text)
        self.assertNotIn("foi foi", text)
        row["p_holm_within_variable"] = 0.20
        text = _difference_sentence("ERA5-Land", row, "°C")
        self.assertIn("não foi significativa", text)
        self.assertNotIn("foi não foi", text)

    def test_signed_values_are_explicit(self):
        self.assertEqual(fmt_signed(0.124, 3), "+0,124")
        self.assertEqual(fmt_signed(-0.249, 3), "-0,249")


if __name__ == "__main__":
    unittest.main()

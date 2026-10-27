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

from climate.harmonization import apply_harmonization, build_daily_era5
from climate.fit_harmonization_models import (
    build_current_model,
    evaluate_cv,
    fit_full_models,
    loeo_predictions,
    update_history,
)


SYNTHETIC_MODEL = {
    "schema_version": 2,
    "model_id": "synthetic",
    "generated_at_utc": "2026-10-09T00:00:00+00:00",
    "reference_site": "pasto",
    "temporal_scale": "daily_24h",
    "validation_design": {"n_days": 10},
    "variables": {
        "temperature": {"operational_method": "linear", "intercept": 8.0, "slope": 0.68},
        "rh": {"operational_method": "linear", "intercept": 40.0, "slope": 0.6, "clip_min": 0.0, "clip_max": 100.0},
        "vpd": {"operational_method": "linear", "intercept": 0.02, "slope": 0.61, "clip_min": 0.0},
    },
}


class TestOperationalHarmonization(unittest.TestCase):
    def test_temperature_uses_current_linear_model(self):
        daily = pd.DataFrame({
            "date": ["2026-04-01"], "era5_temp_C_raw": [25.0], "era5_rh_pct_raw": [80.0],
            "era5_vpd_kPa_raw": [0.8], "n_hours": [24], "use_for_harmonization": [True],
        })
        out = apply_harmonization(daily, SYNTHETIC_MODEL)
        self.assertAlmostEqual(float(out.loc[0, "temp_C_final"]), 8.0 + 0.68 * 25.0, places=8)
        self.assertAlmostEqual(float(out.loc[0, "temp_C_harmonized"]), 8.0 + 0.68 * 25.0, places=8)
        self.assertEqual(out.loc[0, "temp_method"], "linear")

    def test_rh_and_vpd_use_current_linear_model(self):
        daily = pd.DataFrame({
            "date": ["2026-04-01"], "era5_temp_C_raw": [25.0], "era5_rh_pct_raw": [80.0],
            "era5_vpd_kPa_raw": [0.8], "n_hours": [24], "use_for_harmonization": [True],
        })
        out = apply_harmonization(daily, SYNTHETIC_MODEL)
        self.assertAlmostEqual(float(out.loc[0, "rh_pct_harmonized"]), 40.0 + 0.6 * 80.0, places=7)
        self.assertAlmostEqual(float(out.loc[0, "vpd_kPa_harmonized"]), 0.02 + 0.61 * 0.8, places=7)
        self.assertEqual(out.loc[0, "model_id"], "synthetic")

    def test_daily_minimum_coverage_is_enforced(self):
        times = pd.date_range("2026-04-01 00:00", periods=17, freq="h")
        hourly = pd.DataFrame({"datetime_local": times, "temp_C": [25.0] * 17, "rh_pct": [80.0] * 17, "vpd_kPa": [0.6] * 17})
        daily = build_daily_era5(hourly, min_hours=18)
        self.assertFalse(bool(daily.loc[0, "use_for_harmonization"]))
        out = apply_harmonization(daily, SYNTHETIC_MODEL)
        self.assertTrue(pd.isna(out.loc[0, "rh_pct_harmonized"]))


class TestDynamicModelUpdate(unittest.TestCase):
    def _daily(self) -> pd.DataFrame:
        dates = pd.date_range("2026-04-01", periods=12, freq="D")
        era_t = pd.Series(range(12), dtype=float) * 0.2 + 25
        era_rh = pd.Series(range(12), dtype=float) * 0.5 + 78
        era_vpd = pd.Series(range(12), dtype=float) * 0.02 + 0.5
        return pd.DataFrame({
            "date": dates,
            "ERA5_temperature": era_t,
            "FIELD_temperature": 8.0 + 0.68 * era_t,
            "ERA5_rh": era_rh,
            "FIELD_rh": 40.0 + 0.60 * era_rh,
            "ERA5_vpd": era_vpd,
            "FIELD_vpd": 0.02 + 0.61 * era_vpd,
        })

    def test_current_model_is_built_from_available_data(self):
        df = self._daily()
        pred = loeo_predictions(df, embargo_days=1)
        cv = evaluate_cv(pred)
        full = fit_full_models(df)
        policy = json.loads((ROOT / "config" / "harmonization_policy.json").read_text(encoding="utf-8"))
        model = build_current_model(df, cv, full, policy, embargo_days=1)
        self.assertEqual(model["validation_design"]["n_days"], 12)
        self.assertEqual(model["variables"]["temperature"]["operational_method"], "linear")
        self.assertAlmostEqual(model["variables"]["temperature"]["slope"], 0.68, places=6)
        self.assertAlmostEqual(model["variables"]["rh"]["slope"], 0.60, places=6)
        self.assertAlmostEqual(model["variables"]["vpd"]["slope"], 0.61, places=6)

    def test_history_does_not_duplicate_same_model_id(self):
        df = self._daily()
        pred = loeo_predictions(df, embargo_days=1)
        cv = evaluate_cv(pred)
        full = fit_full_models(df)
        policy = json.loads((ROOT / "config" / "harmonization_policy.json").read_text(encoding="utf-8"))
        model = build_current_model(df, cv, full, policy, embargo_days=1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model_history.csv"
            update_history(path, model)
            update_history(path, model)
            hist = pd.read_csv(path)
            self.assertEqual(len(hist), 3)
            self.assertEqual(hist["model_id"].nunique(), 1)


if __name__ == "__main__":
    unittest.main()

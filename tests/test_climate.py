from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from climate.common import hydrologic_date, regression_metrics
from climate.inmet import normalize_inmet
from climate.chirps import normalize_chirps
from climate.download_era5 import build_request
from climate.download_chirps import final_cog_url, prelim_tif_url, download_chirps_point_series
from climate.era5 import _merge_hourly_parts
from climate.validation import monthly_pairs, validate_hourly_rain


class TestClimateTime(unittest.TestCase):
    def test_hydrologic_boundary(self):
        s = pd.Series(pd.to_datetime(['2026-05-01 12:00:00', '2026-05-01 12:00:01']))
        got = list(hydrologic_date(s, 12))
        self.assertEqual(str(got[0]), '2026-05-01')
        self.assertEqual(str(got[1]), '2026-05-02')


class TestInmet(unittest.TestCase):
    def test_inmet_utc_to_belem(self):
        text = '"Data";"Hora (UTC)";"Temp. Ins. (C)";"Umi. Ins. (%)";"Pto Orvalho Ins. (C)";"Chuva (mm)"\n"01/04/2026";"0300";"24,0";"80,0";"20,0";"1,2"\n'
        cfg = {'columns': {}}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'inmet.csv'; p.write_text(text, encoding='utf-8')
            h, d = normalize_inmet(p, cfg, 'America/Belem')
            self.assertEqual(str(h.iloc[0]['datetime_local']), '2026-04-01 00:00:00')
            self.assertAlmostEqual(float(h.iloc[0]['rain_mm']), 1.2, places=6)
            self.assertEqual(set(d['window']), {'utc_calendar', 'local_calendar', 'hydrologic_12_12_local'})


class TestChirps(unittest.TestCase):
    def test_chirps_point_csv(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'sat.csv'
            pd.DataFrame({'date': ['2026-04-01', '2026-04-02'], 'chirps_sat_mm': [3.0, 4.0], 'chirps_release': ['final', 'final']}).to_csv(p, index=False)
            x = normalize_chirps([p], 'sat', {})
            self.assertEqual(len(x), 2)
            self.assertAlmostEqual(float(x['chirps_sat_mm'].sum()), 7.0)

    def test_manifest_csv_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            p = td / 'chirps_v3_sat_point.csv'
            m = td / 'chirps_v3_sat_download_manifest.csv'
            pd.DataFrame({'date': ['2026-04-01'], 'chirps_sat_mm': [3.0], 'chirps_release': ['final']}).to_csv(p, index=False)
            pd.DataFrame({'date': ['2026-04-01'], 'status': ['ok']}).to_csv(m, index=False)
            x = normalize_chirps([p, m], 'sat', {})
            self.assertEqual(len(x), 1)

    def test_final_cog_url(self):
        u = final_cog_url('sat', '2026-03-24')
        self.assertTrue(u.endswith('/final/sat/cogs/2026/chirps-v3.0.sat.2026.03.24.cog'))

    def test_prelim_url(self):
        u = prelim_tif_url('2026-09-01')
        self.assertTrue(u.endswith('/prelim/sat/2026/chirps-v3.0.prelim.2026.09.01.tif'))

    def test_one_failed_final_day_does_not_skip_later_dates(self):
        import climate.download_chirps as dc
        calls = []
        original = dc._sample_raster
        def fake(url, lat, lon):
            calls.append(url)
            if '2026.03.25' in url:
                raise OSError('temporary failure')
            return 1.0, -1.775, -47.175
        dc._sample_raster = fake
        try:
            with tempfile.TemporaryDirectory() as td:
                cfg = {
                    'site_coordinates': {'latitude': -1.760388, 'longitude': -47.190124},
                    'chirps_v3': {'download': {'include_preliminary_sat': False}},
                }
                info = download_chirps_point_series(Path(td), cfg, 'sat', '2026-03-24', '2026-03-26')
                self.assertEqual(info['n_days'], 2)
                self.assertEqual(len(calls), 3)
        finally:
            dc._sample_raster = original


class TestEra5Download(unittest.TestCase):
    def test_timeseries_request(self):
        r = build_request(-1.760388, -47.190124, '2026-03-24', '2026-09-10', ['2m_temperature'])
        self.assertEqual(r['location']['latitude'], -1.760388)
        self.assertEqual(r['date'], ['2026-03-24/2026-09-10'])
        self.assertEqual(r['data_format'], 'netcdf')

    def test_group_files_are_merged_horizontally(self):
        t = pd.to_datetime(['2026-04-01T00:00:00Z', '2026-04-01T01:00:00Z'])
        a = pd.DataFrame({'datetime_utc': t, 'temp_C': [25.0, 26.0]})
        b = pd.DataFrame({'datetime_utc': t, 'precip_mm': [1.0, 0.0]})
        out = _merge_hourly_parts([a, b], 'America/Belem')
        self.assertEqual(len(out), 2)
        self.assertIn('temp_C', out.columns)
        self.assertIn('precip_mm', out.columns)


class TestValidationCoverage(unittest.TestCase):
    def test_monthly_pairs_report_paired_coverage(self):
        field = pd.DataFrame({'date': ['2026-04-01', '2026-04-02', '2026-04-03']})
        paired = pd.DataFrame({
            'date': ['2026-04-01', '2026-04-02'],
            'field_rain_mm': [1.0, 2.0],
            'product_rain_mm': [1.1, 1.9],
            'source': ['X', 'X'],
            'window': ['hydrologic', 'hydrologic'],
            'shift_days': [0, 0],
        })
        out = monthly_pairs(field, paired)
        self.assertEqual(int(out.iloc[0]['n_field_valid_days']), 3)
        self.assertEqual(int(out.iloc[0]['n_paired_days']), 2)
        self.assertFalse(bool(out.iloc[0]['complete_paired_field_coverage']))

    def test_hourly_rain_uses_only_complete_field_hours_and_tests_shifts(self):
        field = pd.DataFrame({
            'datetime_local': pd.to_datetime(['2026-04-01 10:00', '2026-04-01 11:00']),
            'field_rain_mm': [2.0, 5.0],
            'use_for_hourly_validation': [True, False],
        })
        inmet = pd.DataFrame({
            'datetime_local': pd.to_datetime(['2026-04-01 10:00']),
            'rain_mm': [2.0],
        })
        metrics, _ = validate_hourly_rain(field, inmet, pd.DataFrame(), shifts_hours=[0])
        self.assertEqual(int(metrics.iloc[0]['n']), 1)
        self.assertEqual(int(metrics.iloc[0]['shift_hours']), 0)



class TestMetrics(unittest.TestCase):
    def test_perfect_metrics(self):
        m = regression_metrics([1, 2, 3], [1, 2, 3])
        self.assertAlmostEqual(m['r'], 1.0, places=7)
        self.assertAlmostEqual(m['RMSE'], 0.0, places=7)
        self.assertAlmostEqual(m['NSE'], 1.0, places=7)
        self.assertAlmostEqual(m['KGE'], 1.0, places=7)


if __name__ == '__main__':
    unittest.main()

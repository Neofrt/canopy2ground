# Canopy2Ground v2 — code validation status

## Checks completed for Canopy2Ground v2.0.0

- Python source compilation: **PASS** (`python -m compileall -q .`)
- Unit tests: **26/26 PASS**
- Field-processing modules retained from the validated v1 baseline.
- Climate normalization tests cover INMET, ERA5-Land and CHIRPS-v3 conventions.
- Precipitation validation tests cover hydrologic-day boundaries, paired coverage, hourly shifts and separation of event detection from wet-day magnitude diagnostics.
- Operational harmonization tests verify:
  - temperature uses the current dynamically refitted linear model;
  - RH uses the current dynamically refitted linear model;
  - VPD uses the current dynamically refitted linear model;
  - repeated runs with unchanged paired data do not duplicate model-history entries;
  - the minimum daily coverage criterion is enforced.
- Figure generation smoke test: **PASS** for Figures 1–4 using the existing validation outputs; additional smoke test confirmed that missing INMET skips only Figure 1 while Figures 2–4 remain independent.
- Results architecture simplified to:
  - `results/validation/field/`
  - `results/validation/climate/`
  - `results/harmonization/`
  - `results/figures/`
  - `results/tables/`
- Dependency management consolidated in a single `requirements.txt` and isolated by `.venv` through `setup_env.ps1`/`run.ps1` or the Linux/macOS equivalents.

## Validation still required on the field-data workstation

A release should only be tagged after a complete run against the current field `data/raw/` and the intended external climate inputs. The expected Windows workflow is:

```powershell
.\run.bat
```

ERA5-Land and CHIRPS-v3 are updated by default; use `--no-download-climate` only when reusing local climate inputs.

A field validation must end with `VALIDAÇÃO CONCLUÍDA: PASS`. Climate, harmonization and final figures are generated only when the required external products are available. INMET acquisition may still require a previously obtained file or the earlier acquisition routine, as documented in the README.

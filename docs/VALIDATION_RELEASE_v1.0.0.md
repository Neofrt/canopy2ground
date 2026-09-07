# Canopy2Ground v1.0.0 — Validation summary

**Validation date:** 2026-09-07  
**Status:** PASS

The first GitHub release candidate was executed against the current field-data workspace and passed the automated integrity checks.

## Processed outputs

| Product | Records | Available period |
|---|---:|---|
| External daily precipitation | 164 | 2026-03-24 to 2026-09-03 |
| Daily microclimate | 371 | 2026-03-26 to 2026-09-03 |
| Daily hydrological TMS | 1,557 | 2026-03-15 to 2026-09-03 |
| Daily well pressure | 78 | 2026-07-18 to 2026-09-03 |
| Integrated daily site × depth metrics | 1,557 | 2026-03-15 to 2026-09-03 |
| Integrated 30-min timestamps | 8,284 | 2026-03-14 to 2026-09-03 |

## Automated checks

- Core processed files present: **PASS**
- Unique external rainfall date: **PASS**
- Unique microclimate `site × datetime`: **PASS**
- Unique TMS `site × depth × datetime`: **PASS**
- Unique daily TMS `date × site × depth`: **PASS**
- Unique integrated 30-min `datetime`: **PASS**
- Unique integrated daily `date × site × depth`: **PASS**
- TOMST/TMS UTC → `America/Belem` alignment: **PASS** (`max_abs_seconds = 0.0`)
- Large `|Δθ|` events retained rather than automatically masked: **PASS**
- Observed RH saturation in old-growth forest not flagged as suspect: **PASS**

## Notes

The validation reports integrity and implementation consistency. It does not replace future sensor-specific calibration, particularly the provisional TMS volumetric-water-content calibration and absolute groundwater-level conversion, which requires confirmed sensor installation depth and barometric compensation.

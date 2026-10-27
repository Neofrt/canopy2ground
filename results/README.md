# Canopy2Ground results

`results/` contains only derived outputs. It can be deleted and rebuilt from the field RAW files, external climate inputs and the versioned code/configuration.

```text
results/
├── validation/
│   ├── field/                  # integrity checks for processed field products
│   └── climate/
│       └── microclimate/       # common hourly/daily data and GLSAR contrasts
├── harmonization/              # current dynamic model, cross-validation diagnostics and model history
├── figures/                    # final figures used by the current analysis/manuscript
├── tables/                     # tables supporting the final figures
└── report/                     # automatic results report + REPORT_INPUTS.csv audit trail
```

No legacy `figuras`, `modelos`, `v2_microclimate`, `precipitacao`, `microclima`, `tms`, `poco` or `integrated` result folders are created by the refined v2 workflow.

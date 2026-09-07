# Canopy2Ground — Code validation status

## Checks completed before GitHub packaging

- Python source compilation: **PASS** (`python -m compileall -q .`)
- Unit tests: **5/5 PASS**
  - configuration merge preserves user-defined values;
  - TMS UTC → `America/Belem` conversion;
  - hydrologic-day noon boundary;
  - duplicate-key integration guard;
  - empty TMS discovery handling.
- Repository structure: **PASS** — only one `modules/` directory is present.
- Integration guard tested against the previously supplied processed dataset: **PASS**
  - 8,284 integrated 30-min rows;
  - 1,419 daily site × depth rows;
  - zero duplicate `datetime` keys in the 30-min integrated output;
  - zero duplicate `date + site + depth_cm` keys in the daily integrated output.

## Still required on the field-data workstation

The complete pipeline must be rerun from the actual `data/raw/` directory after replacing the code. This is required because the updated TMS module changes the time-axis interpretation to explicit UTC → `America/Belem` conversion. The automatic `scripts/validate_outputs.py` step will then check the newly generated outputs and stop the pipeline if a core integrity condition fails.

A successful full run should end with:

```text
VALIDAÇÃO CONCLUÍDA: PASS
PIPELINE CONCLUÍDO
```

Only after that run should the generated scientific outputs be treated as the current validated Canopy2Ground products.

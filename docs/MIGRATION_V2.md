# Migração Canopy2Ground v1 → v2

## Objetivo

Tornar a v2 autônoma, partindo diretamente de `data/raw/` e eliminando qualquer dependência operacional de executar uma release anterior.

## Preservado da v1

- `modules/precipitation.py`
- `modules/microclimate.py`
- `modules/tms.py`
- `modules/wells.py`
- `modules/integrate.py`
- salvaguardas de integridade e política de RAW imutável
- configuração não destrutiva
- validação central das saídas de campo

## Incorporado da etapa de desenvolvimento da camada climática

- `climate/field_reference.py`
- `climate/inmet.py`
- `climate/era5.py`
- `climate/chirps.py`
- aquisição ERA5-Land e CHIRPS-v3
- validação climática diária/horária
- testes climáticos

## Novo na v2

- `climate/harmonization.py`: aplicação do modelo corrente
- `climate/fit_harmonization_models.py`: ajuste cumulativo automático com os dias pareados disponíveis
- `config/harmonization_policy.json`: método operacional versionado; coeficientes permanecem dinâmicos
- `results/harmonization/current_model.json`: parâmetros correntes
- `results/harmonization/model_history.csv`: histórico auditável dos ajustes
- `scripts/compare_microclimate_sources.py`: GLSAR-AR(1), Holm e métricas de concordância
- `scripts/generate_figures.py`: gera as quatro figuras finais e as tabelas de suporte em uma única etapa
- `tests/test_harmonization.py`
- `run_pipeline.py` como orquestrador único RAW → produtos finais

## Decisões metodológicas versionadas para v2

- temperatura final: ERA5-Land harmonizado por regressão linear dinâmica;
- RH final: regressão linear localmente harmonizada;
- VPD final: regressão linear localmente harmonizada;
- comparação microclimática principal: médias diárias de 24 h;
- mínimo de 18 horas simultaneamente disponíveis para comparações FIELD/INMET/ERA5;
- inferência: diferenças pareadas + GLSAR AR(1) + Holm;
- validação da harmonização: leave-one-day-out com embargo de ±1 dia;
- precipitação: QA strict como validação primária; relaxed apenas como sensibilidade;
- CHIRPS preliminar excluído da validação primária;
- RAW nunca é modificado.

## Critério para tag v2.0.0

A tag só deve ser criada após:

1. `python -m compileall -q .` PASS;
2. `python -m unittest discover -s tests -v` PASS;
3. execução completa a partir do `data/raw/` real;
4. `VALIDAÇÃO CONCLUÍDA: PASS` nos dados de campo;
5. geração de `climate_daily_harmonized.csv`;
6. inspeção das figuras/tabelas v2;
7. CI verde no GitHub.

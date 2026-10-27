# Canopy2Ground v2.0.0 — Climate Acquisition + Validation

## Objetivo

A camada `CLIMATE` consome os produtos já validados do Canopy2Ground e integra **INMET**, **ERA5-Land** e **CHIRPS-v3 SAT/RNL** sem alterar `data/raw` nem reinterpretar o pipeline de campo.

A etapa está dividida em duas ações:

1. **aquisição automática** dos produtos externos;
2. **alinhamento e validação** contra as observações de campo.

A correção de viés permanece desativada. A harmonização só será implementada depois que a validação indicar o produto, a janela temporal e a estrutura de erro mais adequados.

Pergunta central para a precipitação diária:

> **A distribuição intrapentadal baseada em satélite (CHIRPS-v3 SAT) ou em reanálise (CHIRPS-v3 RNL) representa melhor a ocorrência diária da precipitação observada em campo?**

---

## 1. Referência espacial

O ponto oficial de referência climática é o pluviômetro externo do pasto:

```text
latitude  = -1.760388
longitude = -47.190124
```

Essas coordenadas devem ficar somente em `config/climate_config.json`, que é local e ignorado pelo Git.

Para gravá-las sem editar JSON manualmente:

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe .\run_climate_pipeline.py --root . --latitude -1.760388 --longitude -47.190124
```

---

## 2. Dependências climáticas

No computador atual, em que `python` não está no PATH:

```powershell
.\setup_env.ps1
```

A v2.0.0 usa, além de NumPy/Pandas:

- `xarray` e `netCDF4` para NetCDF;
- `cdsapi>=0.7.7` para ERA5-Land;
- `rasterio` para extração pontual remota dos COGs do CHIRPS-v3.

---

## 3. ERA5-Land — configuração única do CDS

O download automático usa o dataset oficial:

```text
reanalysis-era5-land-timeseries
```

É uma série temporal horária em ponto, com seleção do ponto de grade mais próximo. O catálogo do ECMWF classifica essa entrada de séries temporais como um serviço de acesso experimental/alternativo ao ERA5-Land; por isso o Canopy2Ground grava o dataset, a solicitação e os arquivos retornados no manifest. A fonte científica continua sendo ERA5-Land; se a estrutura desse endpoint mudar, o downloader deve ser versionado antes de reprocessar a série.

### 3.1 Conta e licença

1. Entre em `https://cds.climate.copernicus.eu/`.
2. Abra o dataset **ERA5 Land hourly time-series data from 1950 to present**.
3. Aceite manualmente os termos/licença do dataset na página de download.

O CDS exige essa aceitação antes do primeiro download via API.

### 3.2 Arquivo `.cdsapirc`

No Windows, crie:

```text
C:\Users\bruno\.cdsapirc
```

com o conteúdo fornecido pelo seu perfil no CDS:

```text
url: https://cds.climate.copernicus.eu/api
key: <SEU-PERSONAL-ACCESS-TOKEN>
```

Não coloque esse token no repositório.

Confira apenas a existência do arquivo:

```powershell
Test-Path "$HOME\.cdsapirc"
```

O esperado é `True`.

---

## 4. Download automático

Depois de configurar o CDS, rode:

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe .\run_climate_pipeline.py --root . --download --latitude -1.760388 --longitude -47.190124
```

O comando:

1. lê a série diária canônica do campo;
2. determina automaticamente a primeira e a última data disponível;
3. solicita ERA5-Land horário para o ponto do pasto;
4. extrai CHIRPS-v3 SAT e RNL diretamente dos COGs diários no ponto;
5. normaliza INMET, ERA5 e CHIRPS;
6. executa as validações diária, horária e mensal;
7. grava manifests de aquisição para auditoria.

Com os dados de campo atuais, o intervalo automático é **24/03/2026 a 10/09/2026**. Se novos dados forem adicionados depois, o intervalo muda automaticamente.

Para forçar novo download mesmo quando já há um produto correspondente:

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe .\run_climate_pipeline.py --root . --download --force-download
```

Para limitar manualmente um intervalo:

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe .\run_climate_pipeline.py --root . --download --start-date 2026-04-01 --end-date 2026-08-31
```

ERA5 e CHIRPS são independentes: uma falha no CDS não impede a tentativa do CHIRPS, e vice-versa.

---

## 5. ERA5-Land — variáveis baixadas

A solicitação padrão inclui:

```text
2m_temperature
2m_dewpoint_temperature
total_precipitation
surface_solar_radiation_downwards
surface_pressure
10m_u_component_of_wind
10m_v_component_of_wind
volumetric_soil_water_layer_1
volumetric_soil_water_layer_2
volumetric_soil_water_layer_3
volumetric_soil_water_layer_4
soil_temperature_level_1
soil_temperature_level_2
soil_temperature_level_3
soil_temperature_level_4
```

O parser converte:

- temperatura: K → °C;
- precipitação: m → mm;
- radiação: J m⁻² → MJ m⁻² e W m⁻² para o intervalo horário;
- T + ponto de orvalho → RH e VPD;
- componentes U/V → velocidade do vento.

As quatro camadas de solo do ERA5-Land são tratadas explicitamente:

```text
L1:   0–7 cm
L2:   7–28 cm
L3:  28–100 cm
L4: 100–289 cm
```

As comparações primárias do Canopy2Ground são:

```text
TMS 15 cm  ↔ ERA5 L2 (7–28 cm)
TMS 50 cm  ↔ ERA5 L3 (28–100 cm)
```

O sensor de 100 cm está na fronteira das camadas; por isso o código calcula a sensibilidade contra **L3 e L4**, sem tratá-las como equivalentes ao ponto medido.

---

## 6. CHIRPS-v3 SAT e RNL

O CHIRPS-v3 é fundamentalmente um produto pentadal/mensal. Os produtos diários usam informação externa para repartir o total do pentad:

```text
SAT → razões diárias do NASA IMERG Late V07
RNL → razões diárias do ERA5
```

A v2.0.0 não baixa rasters globais completos para o período inteiro. Ela abre os COGs finais remotamente e extrai apenas a célula que contém o ponto do pasto.

Saídas e auditoria:

```text
data/external/CHIRPS/sat/extracted/
data/external/CHIRPS/rnl/extracted/
```

Cada data é consultada independentemente. Uma falha de rede ou arquivo ausente em um dia é registrada no manifest e **não faz o código pular silenciosamente as datas seguintes**.

### Final x preliminary

Por padrão:

```json
"include_preliminary_sat": false,
"chirps_final_only_primary": true
```

Portanto, a análise principal usa apenas o CHIRPS final. Datas recentes ainda sem produto final permanecem ausentes e são registradas no manifest.

Se for necessário acompanhar dados recentes, pode-se mudar localmente:

```json
"include_preliminary_sat": true
```

Nesse caso, o fallback preliminar é permitido somente para SAT e recebe `chirps_release = preliminary`. Ele continua excluído da validação principal enquanto `chirps_final_only_primary = true`.

---

## 7. Escalas temporais

### Microclima e solo

O dado de campo de 30 min é usado para construir a referência horária. A comparação ocorre contra INMET e ERA5-Land em escala horária, mantendo o ciclo diurno.

### Precipitação horária

A validação horária é mais restritiva que a diária.

São usados apenas modos subdiários em que a grade seca/úmida está explicitamente representada em `02_registros_normalizados.csv`:

```text
tip_counts_15min
interval_mm
```

Horas incompletas recebem `use_for_hourly_validation = false`.

O modo `event_cumulative_mm` permanece válido para o total diário canônico, mas não entra automaticamente na validação horária porque o arquivo normalizado contém apenas incrementos positivos e não representa sozinho todos os intervalos secos. Isso evita criar zeros artificiais.

Para chuva horária são avaliados:

```text
-1 h
 0 h
+1 h
```

para detectar possíveis diferenças na convenção temporal dos acumulados.

### Precipitação diária

A referência principal continua sendo o dia hidrológico do campo:

```text
12:00 → 12:00, America/Belem
```

INMET e ERA5 são avaliados em:

```text
UTC calendar
00:00–24:00 local
12:00–12:00 local
```

E os produtos diários são testados com:

```text
t-1, t, t+1
```

O objetivo é diagnosticar o alinhamento; o código não desloca datas silenciosamente.

---

## 8. Saídas principais

```text
data/processed/climate/
├── field_rain_daily_hydrologic.csv
├── field_rain_hourly_available.csv
├── field_microclimate_hourly.csv
├── field_soil_hourly.csv
├── inmet_hourly.csv
├── inmet_daily_windows.csv
├── era5_land_hourly.csv
├── era5_land_daily_windows.csv
├── chirps_v3_sat_daily_point.csv
└── chirps_v3_rnl_daily_point.csv
```

Auditoria dos downloads:

```text
data/external/ERA5/cds_timeseries/download_manifest.json
data/external/CHIRPS/sat/extracted/*download_manifest*.csv
data/external/CHIRPS/rnl/extracted/*download_manifest*.csv
```

Resultados:

```text
results/validation/climate/
├── precip_metrics_daily.csv
├── precip_event_detection.csv
├── precip_paired_daily.csv
├── precip_monthly_paired.csv
├── precip_metrics_hourly.csv
├── precip_event_detection_hourly.csv
├── microclimate_metrics_hourly.csv
├── soil_metrics_hourly.csv
├── best_temporal_alignment.csv
└── HARMONIZATION_GATE.txt
```

`precip_monthly_paired.csv` informa explicitamente `n_paired_days`, `n_field_valid_days`, `paired_field_coverage`, `complete_paired_field_coverage` e se o mês de campo é completo no calendário. Assim, um total mensal externo nunca é tratado como diretamente comparável a um mês parcial sem que isso fique registrado.

---

## 9. Métricas

A validação usa:

```text
r
R²
MAE
RMSE
PBIAS
NSE
KGE
slope
intercept
```

Para ocorrência de chuva:

```text
hits
misses
false alarms
correct dry
POD
FAR
CSI
```

O limiar padrão de evento é 0,2 mm e pode ser alterado em `config/climate_config.json`.

---

## 10. Stage gate para harmonização

A v2.0.0 mantém o diagnóstico documentado como parte da camada de validação climática.

A v1.2.0 só deve aplicar correção de viés depois de responder:

1. qual produto apresenta melhor desempenho;
2. qual janela temporal é mais coerente;
3. se há deslocamento sistemático de data/hora;
4. se o erro depende da magnitude do evento ou da sazonalidade;
5. quais períodos possuem cobertura pareada suficiente;
6. se SAT ou RNL representa melhor a distribuição diária do CHIRPS-v3.

Até lá, `harmonization.enabled` permanece `false`.

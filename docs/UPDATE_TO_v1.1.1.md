# Atualização para Canopy2Ground v1.1.1

Esta atualização automatiza a aquisição de **ERA5-Land horário** e a extração pontual de **CHIRPS-v3 SAT/RNL** e mantém a harmonização desativada até a validação.

## 1. Copiar a atualização

Extraia o ZIP da v1.1.1 diretamente sobre a raiz do repositório:

```text
C:\Users\bruno\OneDrive\Documentos\vscode\canopy2ground
```

Aceite substituir os arquivos de código presentes no pacote.

Não apague:

```text
data/raw/
data/external/
config/project_config.json
config/climate_config.json
```

Esses arquivos/pastas não fazem parte do patch.

## 2. Instalar dependências

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe -m pip install -r .\requirements-climate.txt
```

## 3. Testar

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe -m compileall -q .
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe -m unittest discover -s tests -v
```

A versão entregue foi validada com **17 testes**.

## 4. Gravar a coordenada exata do pasto

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe .\run_climate_pipeline.py --root . --latitude -1.760388 --longitude -47.190124
```

Isso atualiza somente o `config/climate_config.json` local.

## 5. Configurar ERA5-Land uma única vez

O CDS requer conta, aceitação da licença do dataset e o arquivo:

```text
C:\Users\bruno\.cdsapirc
```

com:

```text
url: https://cds.climate.copernicus.eu/api
key: <SEU-PERSONAL-ACCESS-TOKEN>
```

## 6. Baixar e validar

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python314\python.exe .\run_climate_pipeline.py --root . --download
```

O intervalo é inferido automaticamente da série de chuva de campo. Com o conjunto atual: **24/03/2026–10/09/2026**.

O CHIRPS final é usado na validação principal. Datas ainda sem versão final ficam registradas como indisponíveis; nenhum zero é inventado.

## 7. Depois da execução

Os arquivos mais importantes para a primeira auditoria são:

```text
results/climate_validation/best_temporal_alignment.csv
results/climate_validation/precip_metrics_daily.csv
results/climate_validation/precip_event_detection.csv
results/climate_validation/precip_metrics_hourly.csv
results/climate_validation/precip_monthly_paired.csv
results/climate_validation/microclimate_metrics_hourly.csv
results/climate_validation/soil_metrics_hourly.csv
```

Não fazer `git commit` antes de revisar esses resultados e `git status`. `data/external`, `data/processed`, `results/*` e os configs locais permanecem ignorados pelo Git.

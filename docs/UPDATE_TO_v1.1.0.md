# Atualização do Canopy2Ground v1.0.0 → v1.1.0

## 1. Trabalhe em uma branch

Na raiz do clone local:

```powershell
git checkout -b feature/climate-validation
```

## 2. Copie os arquivos da v1.1.0

Substitua/adicione o código e a documentação do pacote v1.1.0, mas **não apague**:

```text
data/raw/
config/project_config.json
```

Também mantenha seus dados locais em `data/external/`, que continua fora do Git.

## 3. Instale as dependências climáticas

```powershell
python -m pip install -r requirements-climate.txt
```

## 4. Rode os testes

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

Esperado: 9 testes `OK`.

## 5. Rode novamente o pipeline de campo

Isso atualiza os aliases explícitos de 06–18 h:

```powershell
python .\run_pipeline.py --root .
```

Campos antigos como `temp_luz_C` continuam existindo. A v1.1.0 acrescenta `temp_06_18_C`, `rh_06_18_pct`, `vpd_06_18_kPa`, `par_06_18_umol` e `soil_temp_06_18_C`.

## 6. Coloque os dados externos

```text
data/external/INMET/    <- export horário INMET
data/external/ERA5/     <- CSV ou NetCDF ERA5-Land
data/external/CHIRPS/sat/
data/external/CHIRPS/rnl/
```

O arquivo INMET já usado no projeto (`generatedBy_react-csv (1).csv`) é compatível com o parser desta versão.

## 7. Crie a configuração climática

```powershell
python .\run_climate_pipeline.py --root .
```

Na primeira execução será criado:

```text
config/climate_config.json
```

Edite o arquivo e informe **latitude e longitude exatas do pluviômetro do pasto** antes de extrair CHIRPS/ERA5-Land em grade.

## 8. Rode a validação climática

```powershell
python .\run_climate_pipeline.py --root .
```

A ausência de CHIRPS não interrompe INMET/ERA5; o pipeline informa qual fonte ainda não foi encontrada.

## 9. Não faça bias correction ainda

A v1.1.0 gera o diagnóstico necessário para escolher:

- CHIRPS SAT ou RNL;
- ERA5-Land;
- janela diária;
- deslocamento -1/0/+1 dia;
- comportamento de eventos.

A correção de viés só deve entrar após essa auditoria.

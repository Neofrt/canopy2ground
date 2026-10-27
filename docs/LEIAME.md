# Canopy2Ground v2.0.0 — LEIAME

**Bruno Moreira Felippe**  
*Integrated monitoring of microclimate, soil water and precipitation*  
Capitão Poço, Pará, Amazônia brasileira


Canopy2Ground é um pipeline reproduzível para ingestão, controle de qualidade, integração e análise de séries eco-hidrológicas e microclimáticas. A versão 2 foi estruturada para ser **autônoma**: o fluxo operacional parte diretamente dos arquivos de campo em `data/raw/`, integra produtos climáticos externos e produz séries validadas e harmonizadas sem depender da execução prévia de uma versão anterior.

> **Status:** **Canopy2Ground v2.0.0**.  
> **Repositório:** `https://github.com/Neofrt/canopy2ground`  
> **Princípio central:** dados RAW são imutáveis; todo produto derivado é reconstruível pelo pipeline.

O fluxo integra cinco grupos principais de informação. Os quatro primeiros correspondem às observações de campo já consolidadas na primeira versão do projeto; o quinto reúne a camada climática incorporada na v2:

- **Precipitação**;
- **Microclima**;
- **Umidade e temperatura do solo (TMS)**;
- **Pressão/nível relativo de água em poços**;
- **Produtos climáticos externos e séries harmonizadas**.

Essa organização é mantida ao longo do processamento, das tabelas derivadas e das rotinas de controle de qualidade, permitindo rastrear cada variável desde o arquivo RAW até os produtos científicos finais.

## 1. Fluxo completo

O fluxo completo é descrito no `README.md` e executado a partir de `run_pipeline.py`.

O comando operacional principal no Windows é:

```powershell
.\run.bat
```

O `run.bat` contorna a política de execução de scripts do PowerShell e chama o `run.ps1` internamente. Na primeira execução, o ambiente virtual `.venv/` é criado, as dependências são instaladas e os testes são executados antes do pipeline.

Por padrão, o fluxo completo também tenta **atualizar ERA5-Land e CHIRPS-v3** até a última data disponível nos dados de campo. Se a execução precisar ser feita sem acesso à internet ou sem atualizar os produtos climáticos, use:

```powershell
.\run.bat --no-download-climate
```

A CDS API deve estar configurada para downloads do ERA5-Land.

> **Observação sobre o INMET.** A integração dos dados do INMET está implementada na v2, porém sua aquisição ainda pode depender de um arquivo previamente obtido ou da rotina de aquisição utilizada nas etapas anteriores de desenvolvimento do Canopy2Ground. Diferentemente de ERA5-Land e CHIRPS-v3, a disponibilidade do INMET não deve ser presumida apenas pela execução de `run_pipeline.py` ou `run_climate_pipeline.py --download`. Quando nenhum arquivo compatível for encontrado em `data/external/INMET/`, o pipeline registra a ausência, preserva a execução das demais etapas e não substitui valores ausentes por estimativas.

## 2. Política de dados

`data/raw/` é gerenciado pelo usuário e tratado como **somente leitura**. O Canopy2Ground cria automaticamente apenas a **estrutura de diretórios** esperada (`PASTO`, `SECUNDARIA`, `PRIMARIA` e suas subpastas), mas nunca cria, altera, move, renomeia ou sobrescreve arquivos RAW.

Novos downloads de sensores devem ser adicionados às respectivas pastas sem apagar os anteriores. Sobreposições temporais são auditadas e deduplicadas durante o processamento.

```text
data/
+-- raw/          # observações originais de campo; imutáveis
+-- external/     # INMET, ERA5-Land e CHIRPS-v3
+-- processed/    # produtos derivados e reconstruíveis
```

`data/raw/`, `data/external/`, `data/processed/`, `results/` e configurações locais não são versionados no GitHub por padrão.

## 3. Organização dos dados RAW

```text
data/raw/
+-- PASTO/
|   +-- Pluviometro/
|   +-- Poço/
|   +-- Termohigrometro/
|   +-- TMS/
+-- SECUNDARIA/
|   +-- Pluviometro/
|   +-- Poço/
|   +-- Termohigrometro/
|   +-- TMS/
+-- PRIMARIA/
    +-- Pluviometro/
    +-- Termohigrometro/
    +-- TMS/
```

Mapeamento interno:

| Pasta de campo | Código interno |
|---|---|
| `PASTO` | `pasto` |
| `SECUNDARIA` | `cap` |
| `PRIMARIA` | `ref` |

### 3.1 Sensores principais

**Pluviômetros**

- `22376831`: floresta primária (`ref`)
- `22376832`: pasto inicialmente; transferido posteriormente para floresta secundária
- `22094687`: novo pluviômetro externo do pasto; tipping bucket de 0,2 mm por tombamento

**Termohigrômetros MX**

- `22378330`: floresta primária
- `22473389`: pasto
- `22475755`: floresta secundária

**TMS**

| Local | 15 cm | 50 cm | profundidade maior |
|---|---|---|---|
| Primária | 95329567 | 95329562 | 95329551 (100 cm) |
| Pasto | 95329559 | 95329570 | 95329552 (100 cm) |
| Secundária | 95329563 | 95329558 | 95329566 (80 cm) |

**Poços**

- `22428978`: pasto
- `22428973`: floresta secundária

As profundidades totais dos poços permanecem provisórias. O pipeline não converte automaticamente pressão para profundidade absoluta do lençol freático sem confirmação da posição do sensor e compensação barométrica.

## 4. Estrutura do repositório v2

A v2 mantém separadas as rotinas de campo, clima, validação e produtos finais. O pacote já contém a estrutura de `data/raw/`, `data/external/`, `data/processed/` e `results/`; `setup_project.py` também a recria quando necessário sem modificar arquivos existentes.

```text
canopy2ground/
+-- climate/                 # aquisição, normalização, validação e harmonização climática
+-- config/                  # templates e política metodológica de harmonização
+-- modules/                 # precipitação, microclima, TMS, poços e integração
+-- scripts/
|   +-- validate_outputs.py
|   +-- compare_microclimate_sources.py
|   +-- generate_figures.py
|   +-- generate_status.py
+-- tests/
+-- docs/
+-- data/
|   +-- raw/                 # fornecido pelo usuário; somente leitura
|   +-- external/            # ERA5-Land, CHIRPS-v3 e INMET
|   +-- processed/           # produtos reconstruíveis
+-- results/
|   +-- validation/
|   |   +-- field/
|   |   +-- climate/
|   +-- harmonization/
|   +-- figures/
|   +-- tables/
+-- run_pipeline.py
+-- run_climate_pipeline.py
+-- setup_project.py
+-- setup_env.ps1
+-- run.ps1
+-- setup_env.sh
+-- run.sh
+-- requirements.txt
+-- README.md
```

As pastas legadas `results/figuras`, `results/modelos`, `results/tabelas`, `results/v2_microclimate` e equivalentes não fazem parte da estrutura operacional da v2 refinada.

## 5. Ambiente virtual

O fluxo recomendado utiliza um ambiente virtual local em `.venv/`. O usuário não precisa instalar manualmente as bibliotecas do projeto.

No Windows, a primeira execução deve ser feita preferencialmente com:

```powershell
.\run.bat
```

O `run.ps1` permanece disponível, mas pode ser bloqueado pela `ExecutionPolicy` do Windows.

Se `.venv/` ainda não existir, o script procura primeiro pelo comando `python` já funcional no sistema, depois pela instalação padrão do Python 3.12 e, por último, pelo `py -3.12`. Somente após localizar de fato um Python 3.12 ele cria o ambiente, instala `requirements.txt`, executa os testes e inicia o pipeline. Uma falha na criação do ambiente interrompe imediatamente a execução; o script não continua com um `.venv` incompleto. Nas execuções seguintes, o mesmo comando reutiliza o ambiente existente.

Também é possível preparar apenas o ambiente:

```powershell
.\setup_env.ps1
```

No Linux/macOS:

```bash
./run.sh
```

A criação do ambiente exige **Python 3.12 instalado no sistema** e acesso à internet na primeira instalação das dependências. O ambiente virtual evita instalações globais e elimina a instalação manual de bibliotecas, mas não substitui o próprio Python nem elimina os downloads da primeira preparação. A pasta `.venv/` não deve ser versionada nem distribuída, pois é específica do sistema operacional e da máquina.

Se houver mais de uma instalação de Python no Windows, o executável pode ser informado explicitamente:

```powershell
$env:C2G_PYTHON = "C:\Users\usuario\AppData\Local\Programs\Python\Python312\python.exe"
.\run.bat
```

Para ERA5-Land, a CDS API continua exigindo configuração das credenciais do Copernicus Climate Data Store.

## 6. Execução

### Fluxo completo recomendado

```powershell
.\run.bat
```

O fluxo completo atualiza ERA5-Land e CHIRPS-v3 por padrão. Para reutilizar somente os arquivos climáticos já existentes, sem nova tentativa de download:

```powershell
.\run.bat --no-download-climate
```

O fluxo executa, na ordem:

1. verificação das dependências e configuração;
2. criação/verificação da estrutura de `data/raw`, `data/external`, `data/processed` e `results`, sem modificar arquivos RAW;
3. processamento da precipitação;
4. processamento do microclima;
5. processamento dos TMS;
6. processamento dos poços, quando houver RAW;
7. integração das bases de campo;
8. validação automática das saídas de campo;
9. construção da referência climática da pastagem;
10. normalização de INMET, ERA5-Land e CHIRPS-v3;
11. validação climática;
12. comparação diária de temperatura, RH e VPD entre Pastagem, INMET e ERA5-Land;
13. aplicação dos modelos operacionais de harmonização;
14. geração das quatro figuras e tabelas de suporte;
15. atualização do status da base.

O comando Python direto continua disponível para uso avançado dentro de um ambiente já preparado:

```powershell
.\.venv\Scripts\python.exe .\run_pipeline.py --root .
```

### Apenas dados de campo

```powershell
.\run.bat --field-only
```

### Apenas camada climática

```powershell
.\run.bat --climate-only
```

### Atualização automática de ERA5-Land e CHIRPS-v3

A atualização é o comportamento padrão de `run.bat`. O argumento explícito continua aceito por compatibilidade:

```powershell
.\run.bat --download-climate
```

INMET é lido de `data/external/INMET/`. Sua aquisição ainda pode exigir um arquivo previamente obtido ou a rotina de aquisição usada nas etapas anteriores de desenvolvimento. A ausência de INMET não impede o processamento de campo nem a ingestão de ERA5-Land e CHIRPS-v3; análises que exigem simultaneamente Pastagem + INMET + ERA5-Land só são executadas quando as três fontes estão disponíveis.

## 7. Convenções temporais

Fuso horário local:

```text
America/Belem
```

### Microclima e TMS

A resolução analítica contínua principal é de **30 minutos**.

A janela operacional de luminosidade permanece documentada como:

```text
06:00 <= horário < 18:00
```

Ela é utilizada quando uma análise diurna específica exige essa janela. A comparação climática principal da v2 para temperatura, RH e VPD utiliza médias de **24 horas**.

### Precipitação

A precipitação diária de campo utiliza a janela hidrológica:

```text
12:00 → 12:00
```

### TMS

Os timestamps TOMST/TMS são interpretados como UTC e convertidos explicitamente para `America/Belem`. `tz_q` é preservado apenas para auditoria e não desloca a série.

## 8. Processamento de campo

### Precipitação

O pipeline reconstrói a série canônica de precipitação do pasto preservando mudanças de equipamento e lacunas reais. Ausências não são convertidas em zero nem interpoladas automaticamente.

O novo pluviômetro `22094687` possui resolução nominal de 0,2 mm por tombamento. A rotina identifica a estrutura do arquivo antes de aplicar conversão para evitar dupla multiplicação quando o export já está em milímetros.

O QA distingue dias completos, quase completos, parciais e ausentes. Para validação climática de precipitação, a v2 utiliza o critério **strict** como análise principal; o critério relaxed permanece como sensibilidade documentada.

Variáveis centrais:

| Variável | Unidade | Descrição |
|---|---:|---|
| `rain_ext_mm` | mm | Precipitação diária no pasto; referência climática externa |
| `rain_local_mm` | mm | Precipitação registrada no próprio local |
| `coverage` | proporção | Fração do período diário efetivamente coberta |
| `status` | texto | Classificação de completude do registro |
| `use_for_calibration_strict` | lógico | Dia elegível para a validação principal |
| `use_for_calibration_relaxed` | lógico | Dia elegível para análise de sensibilidade |

### Microclima

São processados temperatura do ar, umidade relativa, VPD e PAR. A elevada umidade relativa observada na floresta primária é preservada como condição ambiental real e não recebe filtro automático de saturação.

Variáveis centrais:

| Variável | Unidade | Descrição |
|---|---:|---|
| `temp_C` | °C | Temperatura do ar |
| `rh_pct` | % | Umidade relativa |
| `vpd_kPa` | kPa | Déficit de pressão de vapor |
| `par_umol` | $\mu\mathrm{mol\,m^{-2}\,s^{-1}}$ | Radiação fotossinteticamente ativa |
| `dli_mol_m2` | $\mathrm{mol\,m^{-2}\,d^{-1}}$ | Integral diária de luz |
| `delta_temp_C` | °C | Diferença de temperatura em relação ao pasto |
| `delta_rh_pp` | p.p. | Diferença de RH em relação ao pasto |
| `delta_vpd_kPa` | kPa | Diferença de VPD em relação ao pasto |
| `fractional_cover_daily` | 0-1 | Cobertura fracionária estimada a partir da atenuação de PAR |

### TMS

São preservados sinal bruto, água volumétrica, temperatura do solo e mudanças diárias. Valores elevados de $|\Delta\theta| > 0{,}10\ \mathrm{m^3\,m^{-3}}$ não são excluídos automaticamente; são mantidos como eventos diagnósticos de grande secagem ou umedecimento.

Variáveis centrais:

| Variável | Unidade | Descrição |
|---|---:|---|
| `tms_signal` | sinal bruto | Sinal original do sensor |
| `vwc_m3m3` | $\mathrm{m^3\,m^{-3}}$ | Conteúdo volumétrico de água |
| `swc_pct` | % v/v | Conteúdo volumétrico expresso em porcentagem |
| `soil_temp_C` | °C | Temperatura do solo |
| `delta_theta_m3m3` | $\mathrm{m^3\,m^{-3}}$ | Mudança diária de conteúdo de água no solo |
| `delta_theta_pp` | p.p. | Mudança diária em porcentagem volumétrica |
| `delta_theta_event_class` | categoria | Classificação descritiva de grandes mudanças |

### Poços

A pressão absoluta é mantida como observação primária. Eventos conhecidos de manuseio podem ser marcados para revisão, sem exclusão automática.

Variáveis centrais:

| Variável | Unidade | Descrição |
|---|---:|---|
| `pressure_abs_kPa` | kPa | Pressão absoluta registrada pelo logger |
| `temperature_C` | °C | Temperatura associada ao logger |
| `delta_pressure_abs_kPa` | kPa | Mudança relativa de pressão |
| `qa_review` | lógico | Registro que requer inspeção |

A conversão para profundidade absoluta do lençol freático depende da confirmação da posição real de cada sensor e da compensação barométrica; por isso, a pressão absoluta permanece como variável observacional primária.

## 8.1 Principais tabelas processadas

A v2 mantém as tabelas centrais de campo da primeira versão e acrescenta produtos climáticos e de harmonização. As tabelas abaixo formam o núcleo das análises científicas; arquivos auxiliares de QA e auditoria são gerados adicionalmente pelo pipeline.

| Arquivo | Uso principal |
|---|---|
| `metricas_diarias_integradas.csv` | Tabela analítica diária principal (`data × site × profundidade`); integra precipitação, água no solo, microclima, poços e QA |
| `dados_integrados_30min.csv` | Base de 30 min para eventos, defasagens temporais e respostas rápidas após chuva |
| `04_precipitacao_diaria_pasto_externo.csv` | Série canônica de precipitação externa do pasto e referência para validação climática |
| `microclima_diario_integrado.csv` | Síntese diária de temperatura, RH, VPD, PAR/DLI e métricas relativas ao pasto |
| `tms_30min_long.csv` | Água e temperatura do solo em resolução de 30 min |
| `tms_diario_hidrologico.csv` | VWC/SWC, $\Delta\theta$, cobertura e classificação de eventos hídricos no dia hidrológico |
| `climate_daily_harmonized.csv` | ERA5-Land bruto e harmonizado, identificador do modelo e metadados do ajuste |

Os arquivos são gravados nas respectivas subpastas de `data/processed/` (`integrated`, `precipitacao`, `microclima`, `tms` e `climate`). Também são preservadas tabelas de apoio, como `microclima_30min_long.csv`, `tms_native.csv` e os produtos normalizados de poços. A biblioteca completa de variáveis e datasets permanece documentada em `docs/`, enquanto as tabelas científicas específicas das figuras são gravadas em `results/tables/`.

## 9. Produtos climáticos externos

```text
data/external/
+-- ERA5/
+-- INMET/
+-- CHIRPS/
    +-- sat/
    +-- rnl/
```

### ERA5-Land

A v2 normaliza temperatura, ponto de orvalho/RH, VPD, precipitação, radiação, vento, pressão, água no solo e temperatura do solo quando disponíveis. O ponto espacial de referência do pasto é:

```text
latitude  = -1.760388
longitude = -47.190124
```

### INMET

Os horários de origem são tratados como UTC e convertidos para `America/Belem` antes do pareamento com o campo.

**Limitação conhecida da v2:** a integração do INMET está operacional, mas a aquisição ainda pode depender de um arquivo previamente obtido ou da rotina de aquisição utilizada nas etapas anteriores de desenvolvimento. O comando de download climático não deve ser interpretado como garantia de aquisição automática do INMET. Se `data/external/INMET/` não contiver um arquivo compatível, o pipeline registra a fonte como indisponível e segue com as demais etapas possíveis, sem preencher artificialmente os dados ausentes.

### CHIRPS-v3

São suportados os produtos `sat` e `rnl`. Dados preliminares não entram na validação primária por padrão. Ausências de dias ainda não publicados permanecem ausentes; não são interpretadas como chuva zero.

## 10. Validação microclimática

O pareamento **Pastagem + ERA5-Land** é produzido sempre que essas duas fontes estão disponíveis. Ele utiliza horários simultâneos, agrega médias diárias de 24 horas e exige pelo menos 18 horas comuns por dia. Esse pareamento alimenta as regressões, a validação cruzada e a atualização dos modelos de harmonização, sem depender da disponibilidade do INMET.

Quando o INMET também está disponível, o pipeline produz adicionalmente a comparação de três fontes (Pastagem, ERA5-Land e INMET). Para cada variável são avaliados os contrastes:

```text
ERA5 - Campo
INMET - Campo
ERA5 - INMET
```

A inferência utiliza diferenças diárias pareadas com GLSAR e estrutura AR(1). Os três p-valores de cada variável são ajustados por Holm. O pipeline também reporta Pearson `r`, `R²`, CCC de Lin, MAE, RMSE, viés, inclinação e intercepto.

Os boxplots científicos recebem letras derivadas desses mesmos contrastes. A ausência de INMET impede apenas os produtos que dependem explicitamente das três fontes; não bloqueia as regressões Pastagem × ERA5-Land, a atualização dos modelos ou as figuras independentes do INMET.

### 10.1 Precipitação

A precipitação diária é tratada separadamente das variáveis atmosféricas contínuas. O pipeline utiliza a comparação temporal entre a precipitação observada na pastagem e os produtos ERA5-Land e INMET, mantendo o melhor alinhamento temporal documentado para cada fonte. A avaliação quantitativa continua baseada em `r`, RMSE, PBIAS, NSE e KGE. A Figura 4 não utiliza regressão linear de precipitação: apresenta a série diária e os totais mensais dos meses com pelo menos 90% de cobertura válida no campo e 90% de cobertura pareada com o respectivo produto. CHIRPS-v3 permanece disponível na validação técnica, mas não integra a figura principal.

## 11. Harmonização ERA5-Land

A v2 distingue **método de harmonização** e **coeficientes do modelo**. O método é versionado; os coeficientes são atualizados cumulativamente à medida que novos dias pareados entre Pastagem e ERA5-Land entram na base. Assim, o pipeline não mantém uma equação permanentemente congelada enquanto a série de monitoramento continua crescendo.

A política metodológica está registrada em:

```text
config/harmonization_policy.json
```

Na configuração atual, temperatura, RH e VPD utilizam regressão linear. Essa decisão foi adotada após a validação cruzada indicar redução consistente do erro também para temperatura. Em cada execução com novos dados pareados, o pipeline: (1) reconstrói a série diária Pastagem + ERA5-Land; (2) executa validação cruzada *leave-one-day-out* com embargo temporal de um dia; (3) reestima os coeficientes com toda a série disponível; (4) grava o modelo corrente; e (5) aplica esse modelo à série ERA5-Land. Os valores brutos permanecem preservados em paralelo.

O modelo corrente é salvo em:

```text
results/harmonization/current_model.json
```

A evolução dos modelos é registrada em:

```text
results/harmonization/model_history.csv
```

O histórico inclui período usado no ajuste, número de dias, intercepto, inclinação, `R²`, RMSE e CCC. Se os dados pareados não mudarem, uma nova execução não duplica o mesmo `model_id` no histórico.

As equações não são fixadas no README, pois os coeficientes mudam com a expansão da série observacional. O modelo vigente, incluindo intercepto, inclinação, período e número de dias utilizados, é registrado em `results/harmonization/current_model.json`; a evolução completa permanece em `results/harmonization/model_history.csv`.

A série ERA5-Land original é sempre preservada. O pipeline cria novas colunas para o produto harmonizado em vez de sobrescrever valores brutos.

## 12. Produto climático diário final

Arquivo:

```text
data/processed/climate/climate_daily_harmonized.csv
```

Campos centrais:

```text
date
era5_temp_C_raw
era5_rh_pct_raw
era5_vpd_kPa_raw
temp_C_final
temp_C_harmonized
rh_pct_harmonized
vpd_kPa_harmonized
n_hours
use_for_harmonization
model_id
model_generated_at_utc
model_n_days
reference_site
temporal_scale
```

## 13. Figuras científicas da v2

As figuras são geradas **independentemente**, de acordo com os dados realmente disponíveis. A ausência de uma fonte não impede figuras que não dependem dela. O arquivo `results/figures/FIGURE_STATUS.csv` registra `GENERATED` ou `SKIPPED` para cada produto.

1. **Figura 1 — condições atmosféricas:** requer Pastagem + ERA5-Land + INMET e os contrastes GLSAR-AR(1)+Holm;
2. **Figura 2 — relação ERA5-Land × Pastagem:** requer somente Pastagem + ERA5-Land e apresenta regressões diárias de temperatura, RH e VPD, linha 1:1, equação, `R²` e número de dias;
3. **Figura 3 — harmonização:** requer o modelo corrente e apresenta redução percentual do RMSE e CCC obtidos por validação cruzada;
4. **Figura 4 — precipitação:** apresenta (A) a série diária de precipitação da Pastagem, ERA5-Land e INMET para os alinhamentos temporais selecionados e (B) os totais mensais dos meses com pelo menos 90% de cobertura válida no campo e 90% de cobertura pareada. A figura não utiliza regressão linear. CHIRPS-v3 continua na validação técnica, mas não integra a figura principal.

Saídas finais:

```text
results/figures/
+-- figure_01_microclimate_sources.png
+-- figure_02_era5_pasture_regressions.png
+-- figure_03_harmonization_performance.png
+-- figure_04_precipitation_comparison.png
+-- FIGURE_CAPTIONS.md
+-- FIGURE_STATUS.csv

results/tables/
+-- table_01_microclimate_daily_summary.csv
+-- table_02_microclimate_significance_letters.csv
+-- table_03_microclimate_glsar_contrasts.csv
+-- table_04_era5_pasture_regressions.csv
+-- table_05_harmonization_performance.csv
+-- table_06_precipitation_selected_metrics.csv
+-- table_07_precipitation_complete_months.csv
```

## 14. Controle de qualidade e integridade

O pipeline interrompe a execução quando condições centrais de integridade falham. Entre os testes estão:

- existência das principais tabelas processadas;
- unicidade das chaves temporais e espaciais;
- alinhamento UTC → `America/Belem` dos TMS;
- preservação de eventos extremos de $\Delta\theta$;
- ausência de classificação automática da saturação de RH na floresta primária como erro;
- testes de normalização climática;
- testes dos modelos operacionais de harmonização.

Executar manualmente:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

O GitHub Actions executa compilação e testes em Windows e Linux.

## 15. Reprodutibilidade e rastreabilidade

Sempre que disponível, o pipeline preserva:

```text
site
sensor
serial
datetime
source_file
valor_original
valor_processado
QA
```

Os dados de entrada originais permanecem separados dos produtos derivados. A configuração local é atualizada apenas pela adição de campos ausentes; valores definidos pelo usuário não são substituídos automaticamente.

## 16. Atualização contínua dos modelos

A atualização dos modelos faz parte da execução operacional. Não é necessário editar equações manualmente nem substituir um arquivo de configuração quando novos dados são incorporados.

Sempre que existe pareamento diário Pastagem + ERA5-Land, `run_pipeline.py` executa automaticamente:

```text
climate/fit_harmonization_models.py
```

A rotina compara ERA5 bruto, correção aditiva, regressão linear e, para VPD, a reconstrução física como diagnóstico. A política operacional atual utiliza regressão linear para temperatura, RH e VPD. Os coeficientes são reestimados com todos os dias disponíveis em cada atualização, enquanto as séries ERA5-Land brutas permanecem preservadas.

A separação entre **política metodológica** e **parâmetros ajustados** evita duas situações indesejáveis: manter indefinidamente coeficientes obtidos com uma série curta e, no extremo oposto, mudar silenciosamente a família do modelo a cada execução. A série pode refinar os coeficientes continuamente, enquanto mudanças no método devem continuar sendo uma decisão científica explícita.

## 17. Arquivos versionados e não versionados

Versionados:

```text
README.md
modules/
climate/
scripts/
tests/
config/*.example.json
config/harmonization_policy.json
run_pipeline.py
run_climate_pipeline.py
setup_project.py
requirements.txt
docs/
CHANGELOG.md
```

Não versionados por padrão:

```text
data/raw/
data/external/
data/processed/
results/
config/project_config.json
config/climate_config.json
```

## 18. Versionamento

A v1.0.0 permanece como referência histórica da primeira versão validada de processamento de campo. A v2 incorpora esse fluxo e adiciona aquisição/normalização climática, validação, harmonização ERA5-Land e geração padronizada de resultados. A v2 não exige a execução da v1.

Consulte `CHANGELOG.md` para decisões de cada release e `docs/` para documentação metodológica complementar.

## Relatório automático de resultados

Ao final da camada climática, a v2 gera um relatório automático para conferência, auditoria e interpretação científica:

```text
results/report/
└── REPORT_INPUTS.csv
```

O diretório também contém os documentos automáticos em DOCX e PDF gerados pela versão 2.0.0.

O texto é reconstruído a partir dos resultados da própria execução. Assim, número de dias pareados, coeficientes das regressões, R², RMSE, CCC, contrastes GLSAR e métricas de precipitação acompanham automaticamente a expansão da série. A significância dos contrastes não é descrita por frases fixas: o relatório consulta o `p` ajustado por Holm da execução corrente e escreve automaticamente se cada diferença foi significativa ou não. Isso evita manter interpretações antigas quando a série cresce e o resultado inferencial muda.

Além dos arquivos DOCX e PDF, `results/report/REPORT_INPUTS.csv` registra os arquivos usados pelo relatório, suas datas de modificação, número de linhas e o `model_id` corrente quando aplicável, permitindo auditar se o texto foi produzido com os resultados mais recentes.

A Figura 2 contém temperatura, RH e VPD, todas submetidas à harmonização operacional. A Figura 4 compara a precipitação da pastagem somente com ERA5-Land e INMET por meio da série diária e dos totais mensais elegíveis, sem regressão linear. CHIRPS-v3 continua sendo processado e auditado nas tabelas técnicas, mas não é incluído nessa figura.
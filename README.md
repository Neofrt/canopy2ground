# Canopy2Ground

*Integrated monitoring of microclimate, soil water and precipitation*
<img width="1376" height="768" alt="image_f578f320" src="https://github.com/user-attachments/assets/b62d3d39-c0c9-4ae5-b1a4-5bf9d5d4c7a0" />

**Capitão Poço, Pará, Amazônia brasileira**

Documentação técnica, operacional e de dados.

- [Documentação em PDF](docs/Canopy2Ground_Documentacao.pdf)
- [Biblioteca de variáveis](docs/BIBLIOTECA_VARIAVEIS.md)
- [Status da base](docs/STATUS_DADOS.md)
- [Guia de publicação no GitHub](GITHUB_SETUP.md)
- [Identidade do projeto](docs/PROJECT_IDENTITY.md)

## 1. Visão geral

**Canopy2Ground** é uma plataforma integrada de processamento e organização de dados desenvolvida para o monitoramento de microclima, água no solo e precipitação em áreas de pastagem, floresta secundária e floresta primária na Amazônia oriental. O sistema automatiza a ingestão, padronização, controle de qualidade e integração de séries temporais provenientes de diferentes sensores de campo, preservando os dados brutos e garantindo rastreabilidade ao longo de todo o fluxo de processamento. A plataforma gera bases consolidadas e reproduzíveis para análises eco-hidrológicas e microclimáticas, permite a incorporação contínua de novos dados e foi estruturada para futura integração com produtos climáticos externos e disponibilização de dados e resultados em ambiente online.

O objetivo operacional do pipeline é transformar arquivos brutos de diferentes sensores em bases padronizadas, auditáveis e prontas para análise científica, mantendo rastreabilidade completa desde o arquivo original até as tabelas finais.

O fluxo integra quatro grupos principais de dados:

- **Precipitação**
- **Microclima**
- **Umidade e temperatura do solo (TMS)**
- **Pressão/nível relativo de água em poços**

Os dados são atualizados aproximadamente a cada **10 dias**.



> **Status:** primeira versão tecnicamente validada — **Canopy2Ground v1.0.0**.  
> **Repositório:** `https://github.com/Neofrt/canopy2ground`  
> **Versionamento:** código e documentação são mantidos no GitHub; dados RAW permanecem fora do repositório.

O repositório foi estruturado para funcionar como **documentação viva do projeto**. Novas versões do código, mudanças metodológicas e atualizações da biblioteca de variáveis podem ser registradas progressivamente sem substituir o histórico anterior.

---

## 2. Princípios do pipeline

O processamento segue cinco princípios:

1. **Os arquivos brutos nunca são alterados.**
2. Novos downloads podem ser adicionados sem apagar os anteriores.
3. Downloads cumulativos e registros sobrepostos são identificados e deduplicados.
4. As transformações são documentadas e reproduzíveis.
5. Informações de qualidade e cobertura dos dados são preservadas juntamente com os valores processados.

A pasta:

```text
data/raw/
```

é tratada como **somente leitura**.

Todos os resultados derivados são gravados em:

```text
data/processed/
```

e os diagnósticos e auditorias em:

```text
results/
```

---

## 3. Estrutura do projeto

```text
canopy2ground/
│
├── data/
│   ├── raw/
│   │   ├── PASTO/
│   │   │   ├── Pluviometro/
│   │   │   ├── Poço/
│   │   │   ├── Termohigrometro/
│   │   │   └── TMS/
│   │   │
│   │   ├── SECUNDARIA/
│   │   │   ├── Pluviometro/
│   │   │   ├── Poço/
│   │   │   ├── Termohigrometro/
│   │   │   └── TMS/
│   │   │
│   │   └── PRIMARIA/
│   │       ├── Pluviometro/
│   │       ├── Termohigrometro/
│   │       └── TMS/
│   │
│   ├── processed/
│   │   ├── precipitacao/
│   │   ├── microclima/
│   │   ├── tms/
│   │   ├── poco/
│   │   └── integrated/
│   │
│   └── external/
│       ├── CHIRPS/
│       └── INMET/
│
├── modules/
│   ├── precipitation.py
│   ├── microclimate.py
│   ├── tms.py
│   ├── wells.py
│   └── integrate.py
├── scripts/
│   ├── validate_outputs.py
│   └── generate_status.py
├── tests/
│   └── test_core.py
├── config/
│   └── project_config.example.json
├── docs/
├── results/
├── run_pipeline.py
├── setup_project.py
├── requirements.txt
└── README.md
```

---

## 4. Como atualizar os dados

### 4.1 Inserir novos arquivos

A cada nova coleta/download, os arquivos devem ser adicionados à pasta correspondente.

Exemplo:

```text
data/raw/PASTO/Pluviometro/
data/raw/PASTO/TMS/
data/raw/PASTO/Termohigrometro/
data/raw/PASTO/Poço/
```

Os arquivos anteriores **não devem ser apagados ou sobrescritos**.

Recomenda-se manter a data do download no nome do arquivo quando possível.

---

## 5. Como executar o pipeline

No PowerShell, entre na **raiz do repositório**, onde está `run_pipeline.py`:

```powershell
cd C:\Users\bruno\OneDrive\Documents\posdoc_cp
```

Executar:

```powershell
& C:\Users\bruno\AppData\Local\Programs\Python\Python312\python.exe .\run_pipeline.py --root .
```

> Existe apenas uma implementação dos módulos científicos: `modules/`. Não deve existir uma segunda cópia em `scripts/modules/`.

O pipeline executa sequencialmente:

```text
1. Verificação da estrutura
2. Processamento da precipitação
3. Processamento do microclima
4. Processamento dos TMS
5. Processamento dos poços
6. Integração das bases
7. Validação automática de integridade das saídas
8. Geração/atualização do status da base
```

Ao final, os arquivos brutos permanecem intactos e todas as tabelas processadas são atualizadas.

---

## 6. Escalas temporais

### Microclima e TMS

A resolução analítica principal é de **30 minutos**.

O período luminoso utilizado para métricas diurnas é:

```text
06:00 <= horário < 18:00
```

### Precipitação

A precipitação é agregada em escala diária utilizando a janela hidrológica:

```text
12:00 → 12:00
```

Essa definição preserva a compatibilidade com a série histórica de precipitação e permite alinhamento com métricas diárias de água no solo.

### TMS e horário

Os timestamps dos sensores TMS exigem tratamento específico de fuso horário. Os timestamps TOMST são interpretados como **UTC** e convertidos explicitamente para `America/Belem`. O campo `tz_q` é preservado apenas como metadado de auditoria e não é utilizado para deslocar a série temporal. Essa decisão evita que configurações antigas de fuso gravadas no logger alterem silenciosamente o alinhamento científico entre TMS, precipitação e microclima.

---

## 7. Principais grupos de variáveis

### 7.1 Precipitação

| Variável | Unidade | Descrição |
|---|---:|---|
| `rain_ext_mm` | mm | Precipitação diária no pasto; referência climática externa |
| `rain_local_mm` | mm | Precipitação do próprio local |
| `coverage` | proporção | Fração do período diário efetivamente coberta |
| `status` | texto | Classificação de completude do registro |
| `use_for_calibration_strict` | lógico | Dia completo para validações externas |
| `use_for_calibration_relaxed` | lógico | Dia com cobertura aceitável para análise de sensibilidade |

O novo pluviômetro do pasto é um tipping bucket com resolução de **0,2 mm por tombamento**. O pipeline reconhece o formato de exportação antes da conversão para evitar dupla conversão de valores que já estejam em milímetros.

---

### 7.2 Microclima

| Variável | Unidade | Descrição |
|---|---:|---|
| `temp_C` | °C | Temperatura do ar |
| `rh_pct` | % | Umidade relativa |
| `vpd_kPa` | kPa | Déficit de pressão de vapor |
| `par_umol` | µmol m⁻² s⁻¹ | Radiação fotossinteticamente ativa |
| `dli_mol_m2` | mol m⁻² d⁻¹ | Integral diária de luz |
| `delta_temp_C` | °C | Diferença de temperatura em relação ao pasto |
| `delta_rh_pp` | p.p. | Diferença de RH em relação ao pasto |
| `delta_vpd_kPa` | kPa | Diferença de VPD em relação ao pasto |
| `fractional_cover_daily` | 0–1 | Cobertura fracionária estimada a partir da atenuação de PAR |

A elevada umidade relativa observada na floresta primária foi verificada em campo e é tratada como **condição ambiental real**, não como erro automático de sensor.

---

### 7.3 TMS — água e temperatura do solo

| Variável | Unidade | Descrição |
|---|---:|---|
| `tms_signal` | sinal bruto | Sinal original do sensor |
| `vwc_m3m3` | m³ m⁻³ | Conteúdo volumétrico de água |
| `swc_pct` | % v/v | Conteúdo volumétrico expresso em porcentagem |
| `soil_temp_C` | °C | Temperatura do solo |
| `delta_theta_m3m3` | m³ m⁻³ | Mudança diária de conteúdo de água no solo |
| `delta_theta_pp` | pontos percentuais | Mudança diária em % v/v |
| `delta_theta_event_class` | categoria | Classificação descritiva de grandes mudanças |

Valores elevados de `|Δθ|` não são removidos automaticamente. Eles podem representar respostas eco-hidrológicas reais e são mantidos para investigação.

---

### 7.4 Poços

| Variável | Unidade | Descrição |
|---|---:|---|
| `pressure_abs_kPa` | kPa | Pressão absoluta registrada pelo logger |
| `temperature_C` | °C | Temperatura associada ao logger |
| `delta_pressure_abs_kPa` | kPa | Mudança relativa de pressão |
| `qa_review` | lógico | Registro que requer inspeção |

A conversão para profundidade absoluta do lençol freático ainda depende da compensação barométrica e da confirmação da posição real de instalação de cada logger.

---

## 8. Principais tabelas

### `metricas_diarias_integradas.csv`

Tabela analítica principal.

Unidade de observação:

```text
data × site × profundidade
```

Integra:

- precipitação;
- água no solo;
- microclima;
- cobertura fracionária;
- pressão dos poços;
- métricas de QA.

---

### `dados_integrados_30min.csv`

Base de alta resolução temporal.

Indicada para:

- análise por eventos;
- resposta do solo após chuva;
- defasagens temporais;
- conectividade vertical;
- relação entre água no solo e poço;
- respostas rápidas ao microclima.

---

### `04_precipitacao_diaria_pasto_externo.csv`

Base canônica de precipitação externa.

É a principal tabela para comparação com:

- CHIRPS;
- INMET;
- outros produtos climáticos.

---

### `microclima_diario_integrado.csv`

Resume o microclima durante o período luminoso e inclui:

- temperatura;
- RH;
- VPD;
- PAR;
- DLI;
- diferenças em relação ao pasto;
- transmitância;
- cobertura fracionária.

---

### `tms_diario_hidrologico.csv`

Resume água no solo na janela hidrológica diária.

Contém:

- VWC;
- SWC;
- Δθ;
- cobertura de dados;
- classificação de grandes eventos de mudança hídrica.

---

### `pocos_diario_pressao_absoluta.csv`

Resume a dinâmica diária da pressão registrada nos poços.

---

## 9. Controle de qualidade

O QA é utilizado para **descrever a confiabilidade e a completude da observação**, não para apagar automaticamente respostas ecológicas incomuns.

### Exemplos

**Precipitação**
- dia completo;
- dia próximo de completo;
- dia parcial;
- registro ausente.

**Microclima**
- número de observações disponíveis;
- cobertura temporal;
- preservação de condições ambientais extremas quando verificadas em campo.

**TMS**
- erros declarados pelo sensor;
- cobertura temporal;
- manutenção de eventos extremos para investigação.

**Poços**
- mudanças abruptas de pressão;
- registros compatíveis com retirada/manuseio do equipamento.

---

## 10. Salvaguardas de integridade dos dados

A integração utiliza validação explícita das chaves de `merge`. Relações esperadas como `one_to_one` e `many_to_one` são verificadas pelo `pandas`; se uma duplicata inesperada puder multiplicar linhas, o pipeline **interrompe a execução** em vez de gerar silenciosamente uma tabela incorreta.

A configuração local (`config/project_config.json`) também é preservada: atualizações do código apenas adicionam campos ausentes do esquema e **não sobrescrevem valores definidos pelo usuário**. Chaves antigas, como `project_start`, podem permanecer no arquivo por rastreabilidade, mas são ignoradas pelo processamento atual.

O módulo TMS trata explicitamente a ausência de arquivos válidos e arquivos sem mapeamento no inventário, retornando mensagens de erro descritivas antes da integração. Ao final do fluxo, `scripts/validate_outputs.py` verifica novamente chaves únicas, alinhamento UTC→horário local dos TMS, presença da classificação descritiva de Δθ e ausência de classificação indevida da saturação de RH como erro.

---

## 11. Rastreabilidade

Cada etapa preserva informação suficiente para retornar ao dado original.

Sempre que possível, são mantidos:

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

Isso permite reconstruir a origem de qualquer valor utilizado nas análises.

---

## 12. Atualização contínua

O pipeline foi desenvolvido para receber novos dados aproximadamente a cada 10 dias.

O fluxo operacional é:

```text
novo download
      ↓
data/raw
      ↓
run_pipeline.py
      ↓
data/processed
      ↓
QA / auditoria
      ↓
bases científicas atualizadas
```

Não é necessário anexar manualmente linhas a planilhas antigas.

---

## 13. Produtos externos

Produtos climáticos externos ficam separados dos dados de campo:

```text
data/external/
```

Atualmente estão previstos:

- **INMET**
- **CHIRPS**

O primeiro uso do CHIRPS será a validação e harmonização da precipitação diária e mensal em relação ao pluviômetro de referência do pasto.

---

## 14. Biblioteca completa de variáveis

A descrição detalhada das variáveis é mantida separadamente em:

```text
docs/biblioteca_variaveis.csv
docs/BIBLIOTECA_VARIAVEIS.md
docs/biblioteca_datasets.csv
docs/convencoes_projeto.csv
```

Esses documentos constituem o **dicionário oficial de dados do projeto**.

---

## 15. Reprodutibilidade

O pipeline foi estruturado para que uma nova execução utilizando os mesmos arquivos RAW produza novamente a mesma base processada.

Isso permite:

- auditoria;
- reprodução dos resultados;
- rastreamento de correções;
- atualização progressiva da série temporal;
- manutenção de uma única fonte oficial para cada variável.

---

## 16. Próximas etapas

As próximas etapas previstas são:

1. validação final do alinhamento temporal dos TMS;
2. integração da compensação barométrica dos poços;
3. validação da precipitação com CHIRPS e INMET;
4. harmonização climática;
5. desenvolvimento dos módulos analíticos;
6. disponibilização futura dos produtos processados por meio de uma interface web.

---

## 17. Versionamento e manutenção no GitHub

O GitHub será utilizado para versionar **código, documentação e convenções metodológicas**, e não como armazenamento primário dos dados brutos de campo.

### O que deve ser versionado

```text
README.md
modules/
run_pipeline.py
setup_project.py
requirements.txt
config/project_config.example.json
docs/
CHANGELOG.md
```

### O que não deve ser versionado por padrão

```text
data/raw/
data/processed/
data/external/
results/
config/project_config.json
```

Esses caminhos são protegidos pelo arquivo `.gitignore`.

### Atualizações

Cada mudança relevante pode ser registrada com um novo *commit*. Isso permite identificar:

- o que mudou;
- quando mudou;
- por que mudou;
- qual versão do pipeline gerou determinada base;
- quais decisões metodológicas estavam vigentes naquele momento.

O arquivo `CHANGELOG.md` resume alterações importantes entre versões.

O script:

```text
scripts/generate_status.py
```

pode gerar automaticamente `docs/STATUS_DADOS.md` depois de cada atualização das séries, oferecendo uma visão rápida da cobertura temporal e dos principais produtos disponíveis.

---

## 18. Visão de longo prazo

A arquitetura foi construída para permitir que os dados de campo sejam continuamente incorporados sem reconstrução manual das planilhas.

No futuro, a mesma estrutura poderá alimentar uma página web para:

- consultar séries;
- visualizar gráficos;
- acompanhar cobertura dos sensores;
- acessar documentação;
- baixar planilhas processadas e produtos harmonizados.

O site será uma camada de disponibilização; a fonte oficial continuará sendo o pipeline reproduzível descrito neste documento.

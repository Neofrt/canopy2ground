# Biblioteca de variáveis — posdoc_cp

## Convenções do projeto

- **Fuso do projeto**: America/Belem (UTC−3).
- **TMS — timestamp RAW**: TOMST registra o timestamp em UTC; converter UTC→America/Belem.
- **TMS — tz_q**: Offset local em incrementos de 15 min; usar apenas como metadado de auditoria.
- **Período luminoso**: 06:00 inclusive a 18:00 exclusive.
- **Dia hidrológico**: 12:00–12:00; o registro exatamente às 12:00 fecha o dia.
- **Precipitação externa**: PASTO.
- **Pluviômetro 22094687**: 0,2 mm por tombamento quando o export está em contagens.
- **RH elevada em PRIMARIA**: Condição real verificada; não classificar como saturação suspeita.
- **|Δθ| > 0,10 m³ m⁻³**: Evento eco-hidrológico forte a investigar; não excluir automaticamente.
- **Datas**: Sem corte global fixo; usar disponibilidade e QA de cada sensor.
- **Poços**: Pressão absoluta não é profundidade do lençol; falta compensação barométrica e posição real do sensor.
- **Profundidades dos poços**: ~14 m PASTO e ~20 m SECUNDARIA são valores provisórios.

## Principais tabelas

| Tabela | Papel | Grão/chave | Uso recomendado |
|---|---|---|---|
| `integrated/metricas_diarias_integradas.csv` | PRINCIPAL | diária; TMS/chuva 12–12; microclima 06–18 / `date + site + depth_cm` | Modelos eco-hidrológicos, sínteses e relações chuva–solo–microclima–poço. |
| `integrated/dados_integrados_30min.csv` | PRINCIPAL 30 MIN | 30 min / `datetime` | Eventos, defasagens e dinâmica subdiária. |
| `precipitacao/04_precipitacao_diaria_pasto_externo.csv` | PRINCIPAL CHIRPS | 12–12 diária / `date` | Validação/harmonização com CHIRPS e comparação com INMET. |
| `integrated/microclima_diario_integrado.csv` | PRINCIPAL MICROCLIMA | 06–18 diária / `date + site` | Regulação microclimática e estrutura. |
| `tms/tms_diario_hidrologico.csv` | PRINCIPAL TMS | 12–12 diária / `date + site + depth_cm` | VWC, Δθ e eventos de molhamento/secagem. |
| `poco/pocos_diario_pressao_absoluta.csv` | PRINCIPAL POÇO | diária / `date + site` | Dinâmica relativa dos poços antes da compensação barométrica. |
| `microclima/microclima_30min_long.csv` | SUPORTE | 30 min / `site + datetime` | Diagnóstico e análises por local. |
| `tms/tms_30min_long.csv` | SUPORTE | 30 min / `site + depth_cm + datetime` | Perfil e eventos. |
| `poco/pocos_30min.csv` | SUPORTE | 30 min / `site + datetime` | Eventos e alinhamento. |
| `precipitacao/03_precipitacao_diaria_todos_sites.csv` | SUPORTE | 12–12 diária / `date + site` | Comparações entre chuva externa e sob cobertura. |
| `microclima/microclima_native.csv` | AUDITORIA | nativa / `site + datetime` | Rastreabilidade. |
| `tms/tms_native.csv` | AUDITORIA | nativa / `site + position + datetime` | Rastreabilidade, timezone e recalibração. |
| `poco/pocos_native.csv` | AUDITORIA | nativa / `site + serial + datetime` | Rastreabilidade. |
| `precipitacao/02_registros_normalizados.csv` | AUDITORIA | nativa / `site + serial + datetime` | Auditoria de conversão/deduplicação. |
| `precipitacao/01_auditoria_arquivos.csv` | AUDITORIA | arquivo / `source_file` | Controle de ingestão. |
| `precipitacao/06_conflitos_duplicatas.csv` | AUDITORIA | registro / `site + serial + datetime` | Rastreabilidade das decisões. |
| `precipitacao/07_transicoes_e_lacunas.csv` | AUDITORIA | evento / `event` | Contexto operacional. |

## Dicionário de variáveis

| Variável | Grupo | Definição | Unidade | Escala | QA/status | Tabela principal |
|---|---|---|---|---|---|---|
| `datetime` | tempo | Data e hora local do registro processado. | America/Belem | nativa / 30 min | TMS: não usar tz_q para deslocar o timestamp. | `*_30min*.csv` |
| `datetime_utc` | tempo | Timestamp UTC preservado para os registros TMS. | UTC | nativa | Não é o horário local de análise. | `tms_native.csv` |
| `date` | tempo | Data civil/local associada ao registro ou resumo diário. | YYYY-MM-DD | diária | Sem corte global fixo de início. | `metricas_diarias_integradas.csv` |
| `hydro_date` | tempo | Data do dia hidrológico cuja janela termina às 12:00. | YYYY-MM-DD | 12:00–12:00 | Usar em métricas hidrológicas. | `dados_integrados_30min.csv` |
| `periodo_luz` | tempo | Indica o período luminoso operacional. | boolean | 30 min | Convenção fixa. | `dados_integrados_30min.csv` |
| `hora` | tempo | Hora local formatada. | HH:MM | 30 min | — | `dados_integrados_30min.csv` |
| `site` | identificador | Código analítico do ambiente. | pasto/cap/ref | todas | — | `metricas_diarias_integradas.csv` |
| `depth_cm` | identificador | Profundidade nominal do TMS. | cm | TMS | Sensor específico. | `metricas_diarias_integradas.csv` |
| `depth_m` | identificador | Profundidade nominal do TMS. | m | TMS | — | `metricas_diarias_integradas.csv` |
| `serial` | identificador | Número de série do sensor. | texto | todas | — | `vários` |
| `temp_C` | microclima | Temperatura do ar. | °C | nativa / 30 min | — | `microclima_30min_long.csv` |
| `temp_min_C` | microclima | Temperatura mínima do intervalo. | °C | 30 min | — | `microclima_30min_long.csv` |
| `temp_max_C` | microclima | Temperatura máxima do intervalo. | °C | 30 min | — | `microclima_30min_long.csv` |
| `rh_pct` | microclima | Umidade relativa do ar. | % | nativa / 30 min | RH alta em PRIMARIA foi verificada e é real. | `microclima_30min_long.csv` |
| `vpd_kPa` | microclima | Déficit de pressão de vapor. | kPa | nativa / 30 min | Não mascarar por alta RH em PRIMARIA. | `microclima_30min_long.csv` |
| `vpd_max_kPa` | microclima | VPD máximo no intervalo. | kPa | 30 min | — | `microclima_30min_long.csv` |
| `par_umol` | radiação | Radiação fotossinteticamente ativa. | µmol m⁻² s⁻¹ | nativa / 30 min | — | `microclima_30min_long.csv` |
| `dewpoint_C` | microclima | Temperatura do ponto de orvalho. | °C | nativa / 30 min | Pode estar ausente. | `microclima_30min_long.csv` |
| `temp_luz_C` | microclima | Temperatura média entre 06:00–18:00. | °C | diária | Cobertura mínima configurada. | `microclima_diario_integrado.csv` |
| `rh_luz_pct` | microclima | RH média entre 06:00–18:00. | % | diária | Saturação da PRIMARIA é mantida. | `microclima_diario_integrado.csv` |
| `vpd_luz_kPa` | microclima | VPD médio entre 06:00–18:00. | kPa | diária | Saturação da PRIMARIA não invalida o valor. | `microclima_diario_integrado.csv` |
| `par_luz_umol` | radiação | PAR médio local entre 06:00–18:00. | µmol m⁻² s⁻¹ | diária | — | `microclima_diario_integrado.csv` |
| `par_externo_luz_umol` | radiação | PAR médio simultâneo do PASTO (I0). | µmol m⁻² s⁻¹ | diária | PASTO é a referência. | `microclima_diario_integrado.csv` |
| `dli_mol_m2` | radiação | Integral diária de luz local. | mol m⁻² d⁻¹ | diária 06–18 | Cobertura mínima. | `microclima_diario_integrado.csv` |
| `dli_external_mol_m2` | radiação | DLI do PASTO usado como referência. | mol m⁻² d⁻¹ | diária 06–18 | — | `microclima_diario_integrado.csv` |
| `delta_temp_C` | buffering | Diferença de temperatura local em relação ao PASTO. | °C | 30 min / diária | PASTO=0. | `metricas_diarias_integradas.csv` |
| `delta_rh_pp` | buffering | Diferença de RH local em relação ao PASTO. | p.p. | 30 min / diária | PASTO=0. | `metricas_diarias_integradas.csv` |
| `delta_vpd_kPa` | buffering | Diferença de VPD local em relação ao PASTO. | kPa | 30 min / diária | PASTO=0. | `metricas_diarias_integradas.csv` |
| `n_rh_luz` | cobertura_dados | Número de intervalos diurnos com RH válida. | contagem | diária | — | `microclima_diario_integrado.csv` |
| `n_rh_saturado` | diagnóstico | Número de intervalos com RH ≥ 99,9%. | contagem | diária | Não é QA de exclusão. | `microclima_diario_integrado.csv` |
| `fracao_rh_saturado` | diagnóstico | Fração de registros diurnos com RH ≥ 99,9%. | 0–1 | diária | Não excluir PRIMARIA. | `microclima_diario_integrado.csv` |
| `rh_saturation_observed` | diagnóstico | Indicador descritivo de saturação frequente. | boolean | diária | Não significa erro. | `microclima_diario_integrado.csv` |
| `qa_rh_vpd` | compatibilidade | Status de disponibilidade de RH/VPD. | ok/sem_dados | diária | — | `microclima_diario_integrado.csv` |
| `rh_luz_qc_pct` | compatibilidade | Alias de rh_luz_pct. | % | diária | Não remove saturação. | `metricas_diarias_integradas.csv` |
| `vpd_luz_qc_kPa` | compatibilidade | Alias de vpd_luz_kPa. | kPa | diária | Não remove saturação. | `metricas_diarias_integradas.csv` |
| `n_par_pareado` | estrutura | Número de pares simultâneos PAR local/externo. | contagem | diária | Mínimo configurado. | `microclima_diario_integrado.csv` |
| `soma_I` | estrutura | Soma do PAR local nos pares válidos. | soma discreta | diária | — | `microclima_diario_integrado.csv` |
| `soma_I0` | estrutura | Soma do PAR externo nos pares válidos. | soma discreta | diária | — | `microclima_diario_integrado.csv` |
| `transmittance_daily` | estrutura | Transmitância diária do dossel. | 0–1 | diária | Diagnóstico fora 0–1. | `microclima_diario_integrado.csv` |
| `fractional_cover_daily` | estrutura | Cobertura fracionária diária. | 0–1 | diária | Métrica principal de estrutura. | `microclima_diario_integrado.csv` |
| `qa_fc_daily` | QA | Status da cobertura fracionária. | categoria | diária | — | `microclima_diario_integrado.csv` |
| `TMS_T1` | TMS | Temperatura T1 nativa TOMST. | °C | nativa | — | `tms_native.csv` |
| `TMS_T2` | TMS | Temperatura T2 nativa TOMST. | °C | nativa | — | `tms_native.csv` |
| `TMS_T3` | TMS | Temperatura T3 nativa TOMST. | °C | nativa | — | `tms_native.csv` |
| `TMS_moist` | TMS | Sinal bruto de umidade TOMST. | contagem | nativa | Preservar sempre. | `tms_native.csv` |
| `tms_signal` | TMS | Sinal bruto após seleção/deduplicação. | contagem | 30 min / diária | — | `tms_30min_long.csv` |
| `off_soil` | TMS_QA | Indicador de sensor fora do solo. | 0/1 | nativa | VWC=NA quando off_soil=1. | `tms_native.csv` |
| `off_soil_fraction` | TMS_QA | Fração off-soil no intervalo. | 0–1 | 30 min | — | `tms_30min_long.csv` |
| `vwc_m3m3` | água_solo | Conteúdo volumétrico de água. | m³ m⁻³ | 30 min | Calibração específica desejável. | `tms_30min_long.csv` |
| `swc_pct` | água_solo | VWC em porcentagem volumétrica. | % v/v | 30 min / diária | Mesma informação de VWC. | `tms_30min_long.csv` |
| `soil_temp_C` | TMS | Temperatura do solo associada ao TMS. | °C | 30 min | — | `tms_30min_long.csv` |
| `n_vwc` | cobertura_dados | Número de intervalos de 30 min com VWC válida no dia hidrológico. | contagem | diária 12–12 | ≥39/48 para resumo atual. | `tms_diario_hidrologico.csv` |
| `vwc_mean_m3m3` | água_solo | VWC média do dia hidrológico. | m³ m⁻³ | diária 12–12 | — | `metricas_diarias_integradas.csv` |
| `swc_mean_pct` | água_solo | SWC média do dia hidrológico. | % v/v | diária 12–12 | — | `metricas_diarias_integradas.csv` |
| `delta_theta_m3m3` | água_solo | Mudança de VWC entre dias hidrológicos consecutivos. | m³ m⁻³ d⁻¹ | diária 12–12 | Grandes valores são preservados. | `metricas_diarias_integradas.csv` |
| `delta_theta_pp` | água_solo | Δθ em pontos percentuais volumétricos. | p.p. v/v d⁻¹ | diária | — | `metricas_diarias_integradas.csv` |
| `delta_theta_event_class` | evento | Classificação descritiva de Δθ grande. | categoria | diária | Não é filtro de QA. | `metricas_diarias_integradas.csv` |
| `qa_tms_daily` | QA | Status de cobertura do resumo diário TMS. | ok/insufficient_coverage | diária | Não avalia plausibilidade ecológica. | `metricas_diarias_integradas.csv` |
| `tz_q` | tempo_TMS | Offset local reportado pelo TOMST em quartos de hora. | quartos de hora | nativa | Apenas auditoria. | `tms_native.csv` |
| `tz_offset_reported_hours` | tempo_TMS | Offset reportado convertido para horas. | h | nativa | Pode reter configuração do Reino Unido. | `tms_native.csv` |
| `tz_reported_matches_project` | tempo_TMS | Indica se offset reportado coincide com UTC−3. | boolean | nativa | Timestamp vem do UTC bruto. | `tms_native.csv` |
| `timezone_conversion` | tempo_TMS | Conversão temporal aplicada. | texto | nativa | Obrigatória na implementação atual. | `tms_native.csv` |
| `rain_mm` | precipitação | Precipitação local do dia hidrológico. | mm | diária 12–12 | 22094687: 0,2 mm/tip quando em contagens. | `03_precipitacao_diaria_todos_sites.csv` |
| `rain_local_mm` | precipitação | Precipitação do próprio site. | mm | diária 12–12 | Lacunas permanecem NA. | `metricas_diarias_integradas.csv` |
| `rain_ext_mm` | precipitação | Precipitação externa de referência do PASTO. | mm | diária 12–12 | Lacunas=NA, não zero artificial. | `metricas_diarias_integradas.csv` |
| `rain_ext_coverage` | QA_precipitação | Cobertura temporal diária do pluviômetro externo. | 0–1 | diária | 1=completo. | `04_precipitacao_diaria_pasto_externo.csv` |
| `rain_ext_status` | QA_precipitação | Classe de completude da chuva externa. | categoria | diária | — | `04_precipitacao_diaria_pasto_externo.csv` |
| `use_for_calibration_strict` | QA_precipitação | Elegível sob QA estrito. | boolean | diária | Recomendado principal. | `04_precipitacao_diaria_pasto_externo.csv` |
| `use_for_calibration_relaxed` | QA_precipitação | Elegível sob QA relaxado. | boolean | diária | — | `04_precipitacao_diaria_pasto_externo.csv` |
| `raw_value` | precipitação_auditoria | Valor bruto lido do arquivo. | unidade original | nativa | Interpretar junto com mode. | `02_registros_normalizados.csv` |
| `mode` | precipitação_auditoria | Formato interpretado do registro. | categoria | nativa | — | `02_registros_normalizados.csv` |
| `pressure_abs_kPa` | poço | Pressão absoluta do logger do poço. | kPa | nativa / 30 min | Não é profundidade do lençol. | `pocos_30min.csv` |
| `temperature_C` | poço | Temperatura registrada no poço. | °C | nativa / 30 min | — | `pocos_30min.csv` |
| `pressure_abs_mean_kPa` | poço | Pressão absoluta média diária. | kPa | diária | Sem compensação barométrica. | `metricas_diarias_integradas.csv` |
| `pressure_abs_min_kPa` | poço | Pressão absoluta mínima diária. | kPa | diária | — | `metricas_diarias_integradas.csv` |
| `pressure_abs_max_kPa` | poço | Pressão absoluta máxima diária. | kPa | diária | — | `metricas_diarias_integradas.csv` |
| `delta_pressure_abs_kPa` | poço | Mudança diária da pressão absoluta média. | kPa d⁻¹ | diária | Não equivale diretamente a Δnível. | `metricas_diarias_integradas.csv` |
| `qa_review` | QA_poço | Registro que merece revisão por possível manuseio/salto. | boolean | 30 min | Não remove automaticamente. | `pocos_30min.csv` |
| `qa_review_any` | QA_poço | Dia com algum registro do poço marcado para revisão. | boolean | diária | — | `metricas_diarias_integradas.csv` |
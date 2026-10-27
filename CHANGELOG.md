# Canopy2Ground — Changelog

## v2.0.0 — 2026-10-27

Segunda versão estável do **Canopy2Ground**, consolidando em um único fluxo o processamento de campo e a integração com produtos climáticos externos.

Principais mudanças em relação à v1:

- pipeline autônomo iniciado diretamente em `data/raw/`, sem dependência computacional da v1;
- execução simplificada em Windows (`run.bat`) e Linux/macOS (`run.sh`), com criação automática de ambiente virtual;
- integração das séries de precipitação, microclima, TMS e poços com controle de qualidade e validação estrutural;
- camada climática para ERA5-Land, INMET e CHIRPS-v3;
- comparação microclimática diária de 24 h com contrastes pareados, GLSAR AR(1) e correção de Holm;
- harmonização dinâmica de temperatura, umidade relativa e VPD do ERA5-Land por regressão linear, com validação cruzada *leave-one-day-out* e embargo temporal de um dia;
- coeficientes reestimados cumulativamente quando novos dias pareados são incorporados, mantendo histórico dos modelos;
- preservação simultânea das séries ERA5-Land brutas e harmonizadas;
- geração independente de figuras e tabelas, de modo que a ausência de uma fonte externa não bloqueie produtos que não dependem dela;
- avaliação da precipitação com ERA5-Land e INMET em escala diária e mensal, preservando CHIRPS-v3 nas rotinas técnicas de validação;
- relatório automático de resultados e arquivo `REPORT_INPUTS.csv` para auditoria das entradas utilizadas;
- remoção preventiva de saídas estatísticas antigas antes de novas comparações, evitando reutilização silenciosa de resultados residuais;
- documentação ampliada de variáveis, datasets, configuração climática, QA e migração;
- conjunto ampliado de testes automatizados;
- dados RAW permanecem imutáveis e fora do repositório.

## v1.0.0 — 2026-09-07

Primeira versão tecnicamente validada do **Canopy2Ground**.

Principais correções e decisões incorporadas antes do primeiro `push` do repositório:

- timestamps TOMST/TMS interpretados como UTC e convertidos explicitamente para `America/Belem`;
- `tz_q` preservado apenas como metadado de auditoria, sem deslocar a série temporal;
- remoção de corte temporal global: cada série usa as datas efetivamente disponíveis;
- saturação de RH na floresta primária preservada como condição observada válida;
- valores elevados de `|Δθ|` mantidos e classificados descritivamente, sem exclusão automática;
- tratamento explícito para ausência de arquivos TMS válidos e sensores TMS sem mapeamento no inventário;
- `merge` entre bases protegido com validação de cardinalidade (`one_to_one` / `many_to_one`), interrompendo o pipeline se uma duplicata puder multiplicar linhas;
- chuva local do pasto passa a usar a série externa canônica na integração, evitando ambiguidade em dias de transição de pluviômetros;
- atualização de `project_config.json` tornou-se não destrutiva: valores do usuário nunca são substituídos pelo template;
- chave legada `project_start`, se presente em configurações antigas, é ignorada pelo processamento atual;
- mensagens de progresso adicionadas à leitura dos arquivos de microclima;
- testes automatizados básicos e GitHub Actions adicionados ao repositório;
- leitura dos relatórios de validação/status ajustada para evitar `DtypeWarning` sem alterar os dados processados.

## Histórico interno anterior ao GitHub

As versões denominadas internamente como `Pipeline Python v1.x` foram etapas de desenvolvimento. O histórico público do **Canopy2Ground** começa a partir da primeira versão validada no repositório.

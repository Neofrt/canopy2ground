# Canopy2Ground — Changelog

## Unreleased

Nenhuma alteração pendente.

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

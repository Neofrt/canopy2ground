# Canopy2Ground v2.0.0 — nota de release

Data: 27 de outubro de 2026.

Esta é a segunda versão estável do Canopy2Ground. A v2 preserva o processamento de campo validado na v1 e incorpora, no mesmo pipeline, aquisição/normalização climática, validação cruzada, harmonização dinâmica do ERA5-Land, geração padronizada de figuras e tabelas e relatório automático de resultados.

A v2 opera diretamente a partir de `data/raw/` e não exige execução prévia da v1. Dados brutos, dados externos, configurações locais e resultados continuam fora do versionamento por padrão.

## Validação

- compilação Python: PASS;
- testes automatizados: 29/29 PASS na versão de fechamento;
- integridade das principais chaves e alinhamento temporal: validada pelo pipeline;
- série ERA5-Land bruta preservada em paralelo às séries harmonizadas.

## Histórico

A v1.0.0 permanece preservada no histórico Git. As revisões internas utilizadas durante o desenvolvimento da v2 não constituem releases públicas.

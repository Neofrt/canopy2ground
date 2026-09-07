# Status atual da base de dados

Atualizado automaticamente em: **2026-09-07 17:10**

Esta página é gerada a partir das saídas de `data/processed/` e pode ser atualizada após cada execução do pipeline.

| Produto | Status | Registros | Início | Fim |
|---|---|---:|---|---|
| Precipitação externa diária | disponível | 164 | 2026-03-24 | 2026-09-03 |
| Microclima diário | disponível | 371 | 2026-03-26 | 2026-09-03 |
| TMS diário hidrológico | disponível | 1.557 | 2026-03-15 | 2026-09-03 |
| Poços - pressão diária | disponível | 78 | 2026-07-18 | 2026-09-03 |
| Métricas diárias integradas | disponível | 1.557 | 2026-03-15 | 2026-09-03 |
| Dados integrados 30 min | disponível | 8.284 | 2026-03-14 | 2026-09-03 |

## Precipitação mensal disponível

| Mês | Precipitação disponível (mm) |
|---|---:|
| 2026-03 | 35.0 |
| 2026-04 | 189.6 |
| 2026-05 | 425.2 |
| 2026-06 | 81.0 |
| 2026-07 | 16.4 |
| 2026-08 | 47.8 |
| 2026-09 | 0.0 |

## Observações

- Datas refletem a disponibilidade real de cada sensor; não é aplicado um corte temporal global.
- Condições de alta umidade relativa na floresta primária são preservadas como observações válidas.
- Grandes valores de `|Δθ|` são preservados como potenciais eventos eco-hidrológicos e não são excluídos automaticamente.
- Os timestamps TMS devem ser interpretados conforme a convenção temporal documentada no pipeline.

# Dados

Esta pasta representa a estrutura de dados esperada pelo pipeline.

## Regra principal

**Os dados brutos (`data/raw`) não devem ser versionados no GitHub.**

Os arquivos RAW permanecem no armazenamento institucional/local do projeto e são tratados como somente leitura pelo pipeline.

Estrutura local esperada:

```text
data/
├── raw/
│   ├── PASTO/
│   ├── SECUNDARIA/
│   └── PRIMARIA/
├── processed/
└── external/
```

Os produtos processados também ficam fora do Git por padrão. Quando houver uma política de compartilhamento definida, versões específicas poderão ser publicadas como *releases*, em um repositório de dados ou em uma interface web.

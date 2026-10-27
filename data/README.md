# Dados

O pacote inclui a estrutura esperada pelo Canopy2Ground v2. `setup_project.py` pode recriar os diretórios ausentes, mas nunca cria ou modifica arquivos RAW de sensores.

```text
data/
├── raw/
│   ├── PASTO/
│   │   ├── Pluviometro/
│   │   ├── Poço/
│   │   ├── Termohigrometro/
│   │   └── TMS/
│   ├── SECUNDARIA/
│   │   ├── Pluviometro/
│   │   ├── Poço/
│   │   ├── Termohigrometro/
│   │   └── TMS/
│   └── PRIMARIA/
│       ├── Pluviometro/
│       ├── Termohigrometro/
│       └── TMS/
├── external/
│   ├── ERA5/
│   ├── INMET/
│   └── CHIRPS/
│       ├── sat/extracted/
│       └── rnl/extracted/
└── processed/
    ├── precipitacao/
    ├── microclima/
    ├── tms/
    ├── poco/
    ├── integrated/
    └── climate/
```

Copie os arquivos originais de campo para `data/raw/`. O INMET pode continuar dependendo de arquivo previamente obtido.

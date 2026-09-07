# Publicação do Canopy2Ground no GitHub

Repositório criado:

```text
https://github.com/Neofrt/canopy2ground.git
```

## 1. Antes do primeiro commit

Confirme que a raiz local contém apenas uma implementação dos módulos:

```text
run_pipeline.py
modules/
    precipitation.py
    microclimate.py
    tms.py
    wells.py
    integrate.py
```

Não deve existir uma segunda cópia em `scripts/modules/`.

Execute os testes estáticos e unitários:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

Depois execute o pipeline com os RAW reais:

```powershell
python .\run_pipeline.py --root .
```

Confira `data/processed/` e `results/` antes do primeiro `push`.

## 2. Inicializar o repositório local

Na raiz do projeto:

```powershell
git init
git branch -M main
git status
```

Conecte ao repositório já criado:

```powershell
git remote add origin https://github.com/Neofrt/canopy2ground.git
```

Se `origin` já existir, confira primeiro:

```powershell
git remote -v
```

## 3. Primeiro commit

```powershell
git add .
git status
git commit -m "Initial validated release of Canopy2Ground"
git push -u origin main
```

Antes do `git commit`, confira em `git status` que **não aparecem** arquivos de `data/raw`, `data/processed`, `data/external`, `results` ou `config/project_config.json`.

## 4. Criar a primeira tag

Depois de confirmar que o primeiro `push` foi aceito e que o GitHub Actions terminou com sucesso:

```powershell
git tag -a v1.0.0 -m "Canopy2Ground v1.0.0 — first validated release"
git push origin v1.0.0
```

## 5. Atualizações futuras

```powershell
git status
git add .
git commit -m "Describe update"
git push
```

O GitHub versiona o código, a documentação e as convenções metodológicas. Os dados de campo permanecem fora do repositório por padrão.

# Publicação e manutenção do Canopy2Ground no GitHub

Repositório oficial:

```text
https://github.com/Neofrt/canopy2ground.git
```

A branch pública principal é `main`. A versão histórica `v1.0.0` deve permanecer preservada por tag e no histórico Git. A versão atual é **Canopy2Ground v2.0.0**.

## 1. Antes de publicar uma versão

Na raiz do projeto, confirme que dados locais e configurações privadas continuam ignorados:

```powershell
git status --ignored
```

Não devem ser enviados dados de `data/raw/`, `data/processed/`, `data/external/`, `results/`, `config/project_config.json` ou `config/climate_config.json`.

Valide o código:

```powershell
python -m compileall -q .
python -m pytest -q
```

## 2. Atualizar a `main` sem reescrever histórico

```powershell
git checkout main
git pull --ff-only origin main
git add .
git status
git commit -m "Release Canopy2Ground v2.0.0"
git push origin main
```

Não utilizar `force push` para publicar uma release.

## 3. Tags

A tag histórica `v1.0.0` deve continuar apontando para o commit original da primeira versão validada. Para a v2:

```powershell
git tag -a v2.0.0 -m "Canopy2Ground v2.0.0"
git push origin v2.0.0
```

## 4. Release

Após o `push` e a conclusão do CI, publique uma GitHub Release associada à tag `v2.0.0`, usando `docs/RELEASE_v2.0.0.md` como base para a nota da release.

O GitHub versiona código, documentação e convenções metodológicas. Os dados de campo e resultados científicos locais permanecem fora do repositório por padrão.

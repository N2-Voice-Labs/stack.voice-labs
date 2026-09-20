# Project Structure

This repository is the workspace root for `stack.voice-labs`. The repositories under `src/` will be added later as separate submodules.

```text
stack.voice-labs/
├── .github/
├── .vscode/
├── scripts/
├── src/
│   ├── platform/
│   ├── runtime/
│   ├── web/
│   ├── infra/
│   ├── docs/
│   ├── evals/
│   └── models/
├── templates/
│   └── compose/
├── volumes/
├── .editorconfig
├── .env.example
├── .gitignore
├── .gitmodules
├── .markdownlint.json
├── .pre-commit-config.yaml
├── AUTHORS.yml
├── CHANGELOG.md
├── README.md
├── VERSION.txt
├── compose.sh
└── compose.yml
```

Planned submodule mapping:

- `src/platform` will later contain `platform.voice-labs`
- `src/runtime` will later contain `runtime.voice-labs`
- `src/web` will later contain `web.voice-labs`
- `src/infra` will later contain `infra.voice-labs`
- `src/docs` will later contain `docs.voice-labs`
- `src/evals` will later contain `evals.voice-labs`
- `src/models` will later contain `models.voice-labs`

Template mapping:

- `platform.voice-labs` → `bybatkhuu/rest-fastapi-orm-template`
- `runtime.voice-labs` → `bybatkhuu/rest-fastapi-template`
- `models.voice-labs` → `bybatkhuu/model-python-template`
- `evals.voice-labs` → `bybatkhuu/model-python-template`
- `docs.voice-labs` → `bybatkhuu/docs-zensical-template`
- FastAPI logging → reuse `bybatkhuu/module-fastapi-logging`
- `web.voice-labs` → dedicated web project structure to be selected separately

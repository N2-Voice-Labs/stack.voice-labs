# Project Structure

This repository is the shared workspace root for `stack.voice-labs`. Application projects
are staged in two sibling repositories, while the six original repositories remain
untouched. Do not add nested repositories under `src/` or configure submodules until
remotes have been manually created and reviewed.

```text
capst/
├── backend.voice-labs/   # platform/, runtime/, evals/; local staging repository
├── frontend.voice-labs/  # Next.js app; local staging repository
├── platform.voice-labs/  # unchanged source backup
├── runtime.voice-labs/   # unchanged source backup
├── web.voice-labs/       # unchanged source backup
├── evals.voice-labs/     # unchanged source backup
├── docs.voice-labs/      # unchanged source backup
├── infra.voice-labs/     # unchanged source backup
└── stack.voice-labs/     # shared Compose, configuration, docs, acceptance checks
```

The stack repository itself contains:

```text
stack.voice-labs/
├── .github/
├── .vscode/
├── scripts/
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

Future mount mapping (not configured as submodules yet):

- `backend.voice-labs` → `backend/`
- `frontend.voice-labs` → `frontend/`
- shared Compose, environment example, and documentation remain in `stack.voice-labs`
- No models repository is included in the first milestone.

Template mapping:

- `platform.voice-labs` → `bybatkhuu/rest-fastapi-orm-template`
- `runtime.voice-labs` → `bybatkhuu/rest-fastapi-template`
- `evals.voice-labs` → `bybatkhuu/model-python-template`
- `docs.voice-labs` → `bybatkhuu/docs-zensical-template`
- FastAPI logging → reuse `bybatkhuu/module-fastapi-logging`
- `web.voice-labs` → selected Next.js template

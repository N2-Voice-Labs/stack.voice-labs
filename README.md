# stack.voice-labs

`stack.voice-labs` is the main development workspace for the Voice Labs platform.

It brings together the core Voice Labs repositories as Git submodules and provides a single place for local development, environment orchestration, shared scripts, and project-wide documentation.

## Repositories

```text
stack.voice-labs/
├── services/
│   ├── platform/        -> platform.voice-labs
│   └── runtime/         -> runtime.voice-labs
│
├── apps/
│   └── web/             -> web.voice-labs
│
├── infrastructure/
│   └── infra/           -> infra.voice-labs
│
├── documentation/
│   └── docs/            -> docs.voice-labs
│
├── research/
│   └── evals/           -> evals.voice-labs
│
└── models/
    └── models/          -> models.voice-labs
```

Some repositories may be added later as the platform evolves.

## Clone

Clone the complete workspace together with all submodules:

```bash
git clone --recurse-submodules git@github.com:<organization>/stack.voice-labs.git
cd stack.voice-labs
```

If the repository was cloned without submodules:

```bash
git submodule update --init --recursive
```

## Purpose

This repository is responsible only for composing and orchestrating the Voice Labs development environment.

Application and service code should remain inside their respective repositories.

```text
stack.voice-labs
        │
        ├── platform
        ├── runtime
        ├── web
        ├── infrastructure
        ├── documentation
        ├── research
        └── models
```

The goal is to keep the workspace simple, modular, reproducible, and easy to extend as the platform grows.

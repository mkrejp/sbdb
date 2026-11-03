# Agent Guide

This repo is a Python-backed API and data service. Keep the entrypoint short and focused.

## Start here

1. `README.md`
2. `docs/agents-instructions.md` for project history and deployment topology
3. The single doc that matches the task

## Route by task

- Architecture and data model: `docs/design-overview.md` and `docs/notes-for-data-model.*`
- NPÚ sync or import flow: `docs/npu-geoportal-sync.md`
- App build/deploy: `docs/stage-seven-build-and-deploy.md`
- Evaluation and versioning: `docs/stage-eight-eval-versioning.md`

## Rules

- Keep changes stage-appropriate and minimal.
- Do not commit secrets or paste tokens into docs.
- Prefer parameterized SQL and versioned migrations.
- Run the narrowest relevant validation after code changes.

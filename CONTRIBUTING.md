# Contributing to FlowSentry

Thank you for your interest in contributing to FlowSentry!

## Guidelines
1. Inspect existing architecture (`docs/ARCHITECTURE.md`) and database conventions (`docs/DATABASE.md`) before proposing changes.
2. Keep frontend, backend, integrations, detection, and intelligence modules cleanly separated.
3. Never commit `.env` files, API keys, credentials, or database dumps.
4. All workspace-owned endpoints must enforce `require_workspace_role()` and include cross-tenant isolation tests.
5. Run backend (`pytest -v`, `ruff check app tests`) and frontend (`npm run typecheck`, `npm test`, `npm run build`) before opening a pull request.

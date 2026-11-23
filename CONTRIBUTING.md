# Contributing to FlowSentry

Thank you for your interest in contributing to **FlowSentry Community Edition**!

## Licensing & Contributor License Agreement (CLA)
- FlowSentry Community Edition is licensed under the **GNU Affero General Public License v3.0 only (`AGPL-3.0-only`)**. See [`LICENSE`](./LICENSE) and [`NOTICE`](./NOTICE).
- All contributors must review and agree to [`CLA.md`](./CLA.md) before Pull Requests can be merged, allowing maintainers to offer both `AGPL-3.0-only` Community and Commercial Cloud/Enterprise editions.

## Engineering Guidelines
1. Inspect [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) and [`docs/DATABASE.md`](./docs/DATABASE.md) before proposing changes.
2. Keep frontend, backend, detection, intelligence, notification, and integration modules cleanly separated; register new connectors or alert channels against the SPI contracts in `backend/app/core/extensions.py`.
3. Never commit `.env`, `.env.production`, API keys, credentials, TLS private keys, or database dumps.
4. All workspace-owned endpoints must enforce `require_workspace_role()` and include cross-tenant isolation tests.
5. Run backend (`pytest tests -v`, `ruff check app tests`) and frontend (`npm run typecheck`, `npm test`, `npm run lint`, `npm run build`) before opening a pull request.

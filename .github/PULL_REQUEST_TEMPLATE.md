## Summary
<!-- Describe the change and why it is needed. -->

## Type of Change
- [ ] Bug fix
- [ ] New feature / enhancement
- [ ] Documentation / ops update
- [ ] Refactoring / tests

## Verification Checklist
- [ ] Backend tests and lint pass (`pytest -v` and `ruff check app tests`)
- [ ] Frontend checks pass (`npm run typecheck`, `npm test`, `npm run lint`, `npm run build`)
- [ ] Multi-tenant endpoints enforce `require_workspace_role()` and include isolation tests (if applicable)
- [ ] No secrets, `.env` files, or credentials are included

## Contributor License Agreement (CLA)
- [ ] I have read [CLA.md](./CLA.md) and agree that my contribution is licensed under `AGPL-3.0-only` and the FlowSentry CLA.

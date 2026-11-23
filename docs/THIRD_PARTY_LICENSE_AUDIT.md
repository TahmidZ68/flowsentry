# FlowSentry — Third-Party Dependency & License Audit

**Audit Date:** 2026-11-23  
**Inspection Method:** Direct inspection of installed metadata in `backend/.venv` (`importlib.metadata`), `frontend/package.json`, and `frontend/node_modules/*/package.json`, plus repository notice/git-history scans.

---

## 1. Repository Ownership, Existing Notices & Contributor Audit

| Item | Verified Finding | Risk / Requirement |
|---|---|---|
| **`LICENSE` File** | **Absent** (`Test-Path LICENSE` -> False). [`README.md`](../README.md#L111-L112) states: *"Licensing terms are pending final confirmation by the project owner. Do not redistribute commercially until `LICENSE` is added."* | Must add chosen `LICENSE` before public release. Under copyright law, no license = "all rights reserved", blocking open-source adoption. |
| **Copyright Headers & Attribution** | Zero source-file copyright headers exist; [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`SECURITY.md`](../SECURITY.md), [`CHANGELOG.md`](../CHANGELOG.md) contain no external third-party copyright claims. | Add clear copyright ownership header/statement and `NOTICE` file before public release. |
| **Git Contributor History** | `git log --all` shows **13 commits**, **100% authored by a single contributor**: `Tahmid Zoayed <mdtahmidzoayed@gmail.com>`. | **Major advantage:** Sole author holds 100% copyright today and can adopt `AGPL-3.0-only` + Commercial dual-licensing *immediately* without seeking third-party relicensing permission—provided a **CLA** is enforced before accepting external PRs. |
| **Generated / Copied Code** | Alembic migration `56bf9a530d98_initial_schema.py` generated via Alembic Mako template (MIT); UI utility helpers (`cn` via `clsx` + `tailwind-merge`), standard FastAPI/Next.js scaffolding. No copied GPL/proprietary snippets detected. | Clean. |

---

## 2. Backend Python Dependency Licenses (`backend/.venv` + `backend/requirements.txt`)

All 17 entries in `backend/requirements.txt` and their transitive dependencies (83 installed packages total) were inspected:

| Package (`Version`) | Direct / Transitive | Verified License | AGPL-3.0 Compat | Apache-2.0 / MIT Compat | Proprietary / Commercial Compat & Notes |
|---|---|---|---|---|---|
| `fastapi` (`0.165.0`), `starlette` (`1.10.0`), `pydantic` (`2.10.3`), `pydantic-settings` (`2.6.1`), `pydantic_core` (`2.27.1`), `sqlalchemy` (`2.0.36`), `alembic` (`1.14.0`), `pyjwt` (`2.15.1`), `redis` (`7.4.1`), `PyYAML`, `Mako`, `anyio`, `h11`, `urllib3` | Direct / Core Transitive | **MIT** | **Compatible** | **Compatible** | **Compatible** (preserve copyright & MIT permission notice). |
| `uvicorn` (`0.32.1`), `celery` (`5.7.0`), `kombu` (`5.7.0`), `httpx` (`0.28.1`), `httpcore` (`1.0.9`), `idna` (`3.20`), `python-dotenv` (`1.2.4`), `websockets` (`17.4`), `click` (`8.5.1`), `MarkupSafe` (`3.0.4`), `billiard` (`4.3.2`), `amqp` (`5.4.2`) | Direct / Core Transitive | **BSD-3-Clause / BSD** | **Compatible** | **Compatible** | **Compatible** (do not use upstream names for endorsement). |
| `python-multipart` (`0.0.34`), `requests` (`2.34.2`), `CacheControl`, `tzdata`, `opentelemetry-api`, `pytest-asyncio` | Direct / Transitive | **Apache-2.0** | **Compatible** *(AGPLv3 is compatible with Apache-2.0)* | **Compatible** | **Compatible** (preserve Apache-2.0 `NOTICE` files if distributed). |
| `cryptography` (`50.0.2`), `packaging` (`26.3`) | Direct (`cryptography`) | **Apache-2.0 OR BSD-3-Clause** (dual) | **Compatible** | **Compatible** | **Compatible**. |
| `psycopg` (`3.2.3`), `psycopg-binary` (`3.2.3`) | Direct | **LGPL-3.0 (GNU Lesser GPL v3)** | **Compatible** | **Compatible** *(when used as library without copying LGPL source into Apache/MIT code)* | **Compatible as dynamically imported library.** In commercial container images distributing `psycopg-binary` (`libpq`), preserve LGPLv3 notices and do not statically lock out library replacement. |
| `certifi` (`2026.11.20`) | Transitive (via `requests` / `pip_audit`) | **MPL-2.0** | **Compatible** | **Compatible** *(separate files)* | **Compatible** (file-level copyleft; keep `certifi` unmodified). |
| `email_validator` (`2.2.0`), `dnspython` (`2.9.2`), `typing_extensions` (`4.16.0`), `defusedxml` (`0.7.1`), `greenlet` (`3.5.6`) | Direct / Transitive | **Unlicense / ISC / PSF-2.0 / MIT AND PSF-2.0** | **Compatible** | **Compatible** | **Compatible**. |
| `pytest` (`9.2.0`), `ruff` (`0.8.2`), `pip_audit` (`2.10.1`) | Dev / Test / Audit only | **MIT / Apache-2.0** | Dev only | Dev only | Excluded or test-only in dev workflows. |

**Backend Verdict:** **Zero `GPL-only` (`GPL-2.0-only` / `GPL-3.0-only`) packages found.** One runtime weak-copyleft library (`psycopg` / `psycopg-binary` under `LGPLv3`) and one transitive weak-copyleft bundle (`certifi` under `MPL-2.0`) exist; both are legally compatible with `AGPL-3.0-only`, `Apache-2.0`, `MIT`, and hosted commercial SaaS.

---

## 3. Frontend Node.js Dependency Licenses (`frontend/package.json` & `frontend/node_modules`)

Direct runtime dependencies in `frontend/package.json`:
- **MIT:** `next@16.4.6`, `react@18.3.1`, `react-dom@18.3.1`, `@supabase/supabase-js@2.109.0`, `@tanstack/react-query@5.108.2`, `@hookform/resolvers@7.0.8`, `react-hook-form@7.92.0`, `recharts@2.15.4`, `tailwind-merge@2.6.2`, `clsx@2.1.1`, `zod@4.6.7`.
- **ISC:** `lucide-react@0.468.0`.
- **Dev Dependencies:** All direct devDeps are **MIT** (`vitest`, `eslint`, `eslint-config-next`, `tailwindcss`, `jsdom`, `@testing-library/*`, `@vitejs/plugin-react`, `ajv`, `autoprefixer`, `postcss`, `@types/*`) except `typescript@5.9.3` (**Apache-2.0**).

Full recursive scan of `frontend/node_modules` (~740 package entries) identified these non-MIT/Apache/BSD transitive entries requiring explicit tracking:

| Package | Where Used | Verified License | Impact & Compliance Obligation |
|---|---|---|---|
| `@img/sharp-win32-x64` (`0.35.5`), `@img/sharp-wasm32` (`0.35.5`) *(and Linux equivalents in Docker builds)* | Transitive optional image optimizer used by `next` (`sharp`) | **`Apache-2.0 AND LGPL-3.0-or-later`** (+ MIT) | Note the **`AND`** conjunction (`libvips` native shared library is `LGPL-3.0-or-later`). Compatible with `AGPL-3.0-only`; for proprietary Docker builds redistributing `.next/standalone`, either avoid bundling sharp if unused (FlowSentry uses SVG Lucide icons, not Next Image optimization) or retain LGPLv3 notices/dynamic linking for `libvips`. |
| `next/dist/compiled/@vercel/og` (`1.0.1`) | Bundled inside `next` | **`MPL-2.0`** | File-level weak copyleft; compatible if kept unmodified with `next`'s bundled notices. |
| `axe-core` (`4.14.1`) | Transitive dev/lint dependency | **`MPL-2.0`** | Dev-only; not shipped in `.next/standalone` production bundle. |
| `caniuse-lite` (`1.0.30001826`) | Transitive CSS/browser targeting (`autoprefixer`/`next`) | **`CC-BY-4.0`** | Include attribution notice in third-party attribution/NOTICE file if distributing compiled frontend builds. |
| `@isaacs/nonrecursive-glob-match`, `minimatch` (`11.0.9`), `next/dist/compiled/tar` | Build/lint tooling | **`BlueOak-1.0.0`** | Permissive license; fully compatible with AGPL-3.0, Apache-2.0, and MIT. |
| `*-builtin`, `react-server-dom-*-builtin`, `babel-packages` (`UNSPECIFIED`) | Internal test/mock fixtures bundled inside `next/dist` / tooling | `UNSPECIFIED` | Internal Next.js fixtures (MIT upstream `vercel/next.js`). Verify `next` root `LICENSE` attribution is preserved. |

---

## 4. External APIs, SDKs & Trademark Considerations (`Category E`)

1. **OpenAI & Google Gemini REST APIs:** FlowSentry invokes `https://api.openai.com/v1/chat/completions` and `https://generativelanguage.googleapis.com/v1beta/models/...` directly over `httpx` (zero proprietary vendor SDK packages installed). Commercial SaaS use must comply with OpenAI/Google API Terms of Service, privacy disclosures (sending sanitized workflow error summaries), and data retention settings.
2. **Supabase (`@supabase/supabase-js` MIT + REST JWKS):** Client SDK is MIT. Backend verifies JWKS via `PyJWT` (MIT). No proprietary Supabase server lock-in exists. Self-hosted Apache-2.0 / MIT / AGPL deployments are permitted by Supabase terms.
3. **n8n Trademarks & Brand Mentions:** `n8n` (licensed under Sustainable Use License / fair-code by n8n GmbH) is referenced solely as a compatible upstream integration target (`N8nClient`, `parse_n8n_error_webhook`). FlowSentry does **not** embed or copy n8n source code, so n8n's Sustainable Use License does **not** taint FlowSentry. Include a clear non-affiliation trademark disclaimer in `README.md` (`n8n`, `Supabase`, `Slack`, `OpenAI`, `Google Gemini`, `HubSpot`, `Stripe` are trademarks of their respective owners).

---

## 5. Derivative Work Risk Analysis (`AGPL-3.0-only`)

- **Community Code Importing Community Dependencies:** `AGPL-3.0-only` is legally compatible with every Python (`MIT`, `BSD`, `Apache-2.0`, `ISC`, `PSF`, `Unlicense`, `MPL-2.0`, `LGPLv3`) and Node (`MIT`, `ISC`, `Apache-2.0`, `BSD`, `MPL-2.0`, `LGPL-3.0-or-later`, `BlueOak-1.0.0`, `CC-BY-4.0`) dependency observed.
- **Commercial Modules Linking AGPL-3.0 Core:** Any third party or downstream vendor importing/linking `AGPL-3.0-only` FlowSentry Python/TypeScript modules in the same runtime process creates a derivative/combined work subject to AGPL-3.0 source disclosure over network usage. **Only the copyright holder (via sole ownership + signed contributor CLAs)** can commercially dual-license combined Enterprise/Cloud builds; clean architectural separation (SPI + out-of-process services) protects external Enterprise extensions and Cloud services from accidental copyleft leakage even internally.

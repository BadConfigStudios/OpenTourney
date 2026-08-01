# Phase 1 — Repo Scaffold + CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up OpenTourney's backend and frontend service skeletons, a Sphinx docs scaffold, and GitHub Actions CI on `badconfig-runners`, so every later phase has a real build/test/lint pipeline to land on.

**Architecture:** Two independently runnable services — a FastAPI backend (`backend/`) exposing only `GET /healthz`, and a Vite + React + TypeScript frontend (`frontend/`) rendering a placeholder page wrapped in a `QueryClientProvider` (state-management wiring only; no API calls yet). A Sphinx docs project (`docs/`) with `autodoc` enabled but no content beyond an index page. One CI workflow (`.github/workflows/ci.yml`) lints and tests both services, builds the docs, and builds both Docker images, all on `badconfig-runners`.

**Tech Stack:** Python 3.12, FastAPI, pytest, ruff, Node 20, React 18, TypeScript, Vite, Vitest, Testing Library, ESLint (flat config), Sphinx, Docker, GitHub Actions.

## Global Constraints

- TDD (red → green → refactor) for all code (NFR1, `~/.claude/CLAUDE.md`).
- Backend stack is FastAPI (`DECISIONS.md`, 2026-07-19 — matches limitless-organizer-tracker/club-checkin, auto-generates OpenAPI).
- Frontend stack is React + TypeScript + Vite + TanStack Query (`DECISIONS.md`, 2026-07-19).
- Docs toolchain is Sphinx with `autodoc` (`DECISIONS.md`, 2026-07-19 — pulls docs from FastAPI/Pydantic models; versioning via `sphinx-multiversion` is a later-phase concern, not scaffolded here).
- All CI jobs run on `badconfig-runners` (`REQUIREMENTS.md` FR3; org-wide switch per limitless-organizer-tracker commit `2f42824`).
- Python floor `>=3.12`, Node `20` — matches limitless-organizer-tracker's CI.
- API-first: the reference UI must never get private backend-only access beyond the published API (NFR2) — not exercised yet in Phase 1 (no API calls from the frontend until later phases), but no shortcut may be taken that would violate it later.
- OpenTourney owns no accounts/passwords (NFR4) — not exercised in Phase 1 (no auth yet).
- Kubernetes staging verification (NFR3) begins Phase 2 (`DECISIONS.md`) — Phase 1's verification gate is local + CI only, not staging.
- Traces to `REQUIREMENTS.md` FR1–FR4, Build Order Phase 1.

---

## File Structure

```
OpenTourney/
├── .gitignore
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py
│   └── tests/
│       ├── __init__.py
│       └── integration/
│           ├── __init__.py
│           └── test_health.py
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── eslint.config.js
│   ├── Dockerfile
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── App.test.tsx
│       ├── vite-env.d.ts
│       └── test/
│           └── setup.ts
├── docs/
│   ├── conf.py
│   └── index.rst
└── .github/
    └── workflows/
        └── ci.yml
```

- `backend/app/` — service code. Single-endpoint skeleton only; `main.py` stays a single file until Phase 3 introduces the domain model and routers are split out.
- `backend/tests/integration/` — mirrors limitless-organizer-tracker's layered test layout (`unit/`, `integration/`, `acceptance/`); only `integration/` exists in Phase 1 because `/healthz` is a real in-process HTTP call through `TestClient`, not an isolated unit.
- `frontend/src/` — component code co-located with its test (`App.tsx` + `App.test.tsx`), matching limitless-organizer-tracker's convention.
- `docs/` — flat Sphinx project at repo root (not nested under `backend/`), since it documents the whole project, not just the backend package.
- `.github/workflows/ci.yml` — single workflow, six jobs, one per lint/test/build concern.

---

### Task 1: Backend service skeleton

**Files:**
- Create: `OpenTourney/.gitignore`
- Create: `OpenTourney/backend/pyproject.toml`
- Create: `OpenTourney/backend/app/__init__.py`
- Create: `OpenTourney/backend/app/main.py`
- Create: `OpenTourney/backend/tests/__init__.py`
- Create: `OpenTourney/backend/tests/integration/__init__.py`
- Test: `OpenTourney/backend/tests/integration/test_health.py`
- Create: `OpenTourney/backend/Dockerfile`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a FastAPI app object importable as `app.main:app`, with `GET /healthz` returning `{"status": "ok"}` (HTTP 200). Frontend Task 2 does not call this yet; CI Task 4's `backend-lint`/`backend-test` jobs run `ruff check app tests` and `pytest` against this package; Task 4's `docker-build` job builds `./backend` using this `Dockerfile`.

- [ ] **Step 1: Scaffold the backend package and repo-wide `.gitignore`**

`OpenTourney/.gitignore`:
```gitignore
# --- Python ---
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
.venv/
venv/

# --- Node / frontend ---
node_modules/
dist/
.vite/
coverage/

# --- Env & secrets ---
.env
.env.*
!.env.example

# --- Docs ---
docs/_build/

# --- Editors / OS ---
.DS_Store
*.swp
*.code-workspace
```

`OpenTourney/backend/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "opentourney-backend"
version = "0.1.0"
description = "OpenTourney API backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "sphinx>=7.4",
]

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

`OpenTourney/backend/app/__init__.py`: empty file.

`OpenTourney/backend/tests/__init__.py`: empty file.

`OpenTourney/backend/tests/integration/__init__.py`: empty file.

- [ ] **Step 2: Write the failing test**

`OpenTourney/backend/tests/integration/test_health.py`:
```python
from fastapi.testclient import TestClient

from app.main import app


def test_healthz_returns_ok():
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run the test to verify it fails**

Run (from `backend/`): `pip install -e ".[dev]" && pytest tests/integration/test_health.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'app.main'` (or `app` has no attribute `main`) — `app/main.py` doesn't exist yet.

- [ ] **Step 4: Write the minimal implementation**

`OpenTourney/backend/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="OpenTourney")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/integration/test_health.py -v`
Expected: PASS

- [ ] **Step 6: Lint**

Run: `ruff check app tests`
Expected: no errors. Fix any that appear before continuing.

- [ ] **Step 7: Add the Dockerfile**

`OpenTourney/backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 8: Commit**

```bash
git add .gitignore backend/pyproject.toml backend/app backend/tests backend/Dockerfile
git commit -m "feat(backend): scaffold FastAPI service with /healthz"
```

---

### Task 2: Frontend service skeleton

**Files:**
- Create: `OpenTourney/frontend/package.json`
- Create: `OpenTourney/frontend/tsconfig.json`
- Create: `OpenTourney/frontend/vite.config.ts`
- Create: `OpenTourney/frontend/index.html`
- Create: `OpenTourney/frontend/eslint.config.js`
- Create: `OpenTourney/frontend/src/vite-env.d.ts`
- Create: `OpenTourney/frontend/src/test/setup.ts`
- Test: `OpenTourney/frontend/src/App.test.tsx`
- Create: `OpenTourney/frontend/src/App.tsx`
- Create: `OpenTourney/frontend/src/main.tsx`
- Create: `OpenTourney/frontend/Dockerfile`

**Interfaces:**
- Consumes: nothing from Task 1 (runs independently; no API calls yet, per Global Constraints/NFR2 — nothing to violate yet since there's nothing to call).
- Produces: an `App` component (named export) rendering an `<h1>OpenTourney</h1>`, mounted in `main.tsx` inside `QueryClientProvider`. `npm run build`, `npm run lint`, `npm run test -- --run` all succeed. CI Task 4's `frontend-lint`/`frontend-test` jobs and `docker-build` job (via `Dockerfile`) depend on this.

- [ ] **Step 1: Scaffold frontend config files**

`OpenTourney/frontend/package.json`:
```json
{
  "name": "opentourney-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "lint": "eslint .",
    "test": "vitest",
    "preview": "vite preview"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@eslint/js": "^9.11.0",
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "eslint": "^9.11.0",
    "eslint-plugin-react-hooks": "^5.1.0",
    "eslint-plugin-react-refresh": "^0.4.0",
    "globals": "^15.9.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.6.0",
    "typescript-eslint": "^8.7.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0"
  }
}
```

`OpenTourney/frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src", "vite.config.ts"]
}
```

`OpenTourney/frontend/vite.config.ts`:
```typescript
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
```

`OpenTourney/frontend/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>OpenTourney</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`OpenTourney/frontend/eslint.config.js`:
```javascript
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
);
```

`OpenTourney/frontend/src/vite-env.d.ts`:
```typescript
/// <reference types="vite/client" />
```

`OpenTourney/frontend/src/test/setup.ts`:
```typescript
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

afterEach(() => cleanup());
```

- [ ] **Step 2: Write the failing test**

`OpenTourney/frontend/src/App.test.tsx`:
```typescript
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the OpenTourney heading", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "OpenTourney" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run (from `frontend/`): `npm install && npm run test -- --run`
Expected: FAIL — `Cannot find module './App'` (or equivalent resolution error) — `App.tsx` doesn't exist yet.

- [ ] **Step 4: Write the minimal implementation**

`OpenTourney/frontend/src/App.tsx`:
```typescript
export function App() {
  return <h1>OpenTourney</h1>;
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm run test -- --run`
Expected: PASS

- [ ] **Step 6: Wire the entry point**

`OpenTourney/frontend/src/main.tsx`:
```typescript
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
```

- [ ] **Step 7: Verify build and lint**

Run: `npm run build`
Expected: succeeds, produces `dist/`.

Run: `npm run lint`
Expected: no errors. Fix any that appear before continuing.

- [ ] **Step 8: Add the Dockerfile**

`OpenTourney/frontend/Dockerfile`:
```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/eslint.config.js frontend/Dockerfile frontend/src
git commit -m "feat(frontend): scaffold React/TS/Vite service with placeholder page"
```

---

### Task 3: Sphinx docs scaffold

**Files:**
- Create: `OpenTourney/docs/conf.py`
- Create: `OpenTourney/docs/index.rst`

**Interfaces:**
- Consumes: `sphinx` from `backend/pyproject.toml`'s `dev` extra (Task 1) — installed via `pip install -e "backend[dev]"`.
- Produces: an HTML build at `docs/_build/` via `sphinx-build -b html docs docs/_build -W` (warnings-as-errors). CI Task 4's `docs-build` job runs this exact command.

- [ ] **Step 1: Scaffold the Sphinx project**

`OpenTourney/docs/conf.py`:
```python
project = "OpenTourney"
copyright = "2026, BadConfigStudios"
author = "BadConfigStudios"
release = "0.1.0"

extensions = ["sphinx.ext.autodoc"]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "alabaster"
```

`OpenTourney/docs/index.rst`:
```rst
OpenTourney
===========

Game-agnostic, open tournament-tracking standard and engine.

.. toctree::
   :maxdepth: 2
```

- [ ] **Step 2: Verify it builds cleanly**

Run (from repo root, with `backend[dev]` installed per Task 1 Step 3/5): `sphinx-build -b html docs docs/_build -W`
Expected: build succeeds, exit code 0, no warnings. `sphinx.ext.autodoc` is enabled but unused (no `automodule::`/`autoclass::` directives) until a later phase documents the domain model — it must not produce warnings on its own.

- [ ] **Step 3: Commit**

```bash
git add docs/conf.py docs/index.rst
git commit -m "docs: scaffold Sphinx project with autodoc enabled"
```

---

### Task 4: CI workflow

**Files:**
- Create: `OpenTourney/.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `backend/pyproject.toml` dev extra (Task 1), `frontend/package.json` scripts (Task 2), `docs/` Sphinx project (Task 3), `backend/Dockerfile` and `frontend/Dockerfile` (Tasks 1–2).
- Produces: six CI jobs (`backend-lint`, `backend-test`, `frontend-lint`, `frontend-test`, `docs-build`, `docker-build`), all `runs-on: badconfig-runners`, triggered on every push and pull request.

- [ ] **Step 1: Write the workflow**

`OpenTourney/.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  backend-lint:
    runs-on: badconfig-runners
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
      - run: pip install -e ".[dev]"
      - run: ruff check app tests

  backend-test:
    runs-on: badconfig-runners
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
      - run: pip install -e ".[dev]"
      - run: pytest --cov=app

  frontend-lint:
    runs-on: badconfig-runners
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: npm install
      - run: npm run lint

  frontend-test:
    runs-on: badconfig-runners
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: npm install
      - run: npm run test -- --run

  docs-build:
    runs-on: badconfig-runners
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
      - run: pip install -e "backend[dev]"
      - run: sphinx-build -b html docs docs/_build -W

  docker-build:
    runs-on: badconfig-runners
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t opentourney-backend ./backend
      - run: docker build -t opentourney-frontend ./frontend
```

Note: unlike limitless-organizer-tracker's `docker-build` job (which only runs on pushes to `main`), this runs on every push/PR — Phase 1's Dockerfiles have no prior CI coverage, so a broken image should be caught before merge, not after.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow on badconfig-runners"
```

- [ ] **Step 3: Push and verify on GitHub**

Run: `git push -u origin feat/phase-1-repo-scaffold-ci`
Expected: all six jobs listed above appear on the pushed branch and pass. Fix and re-push if any fail — do not open the PR until this workflow is green.

---

### Task 5: Phase 1 verification (manual gate before PR/merge)

Per `~/.claude/CLAUDE.md`'s mandatory manual verification gate: bring the project up locally and exercise every new behavior before opening/merging the PR. Work through this checklist and report pass/fail per item.

**Files:** none (verification only).

- [ ] **Step 1: Backend happy path**

Run: `cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload`
Then: `curl -s localhost:8000/healthz`
Expected: `{"status":"ok"}`

- [ ] **Step 2: Backend edge case**

Run: `curl -s -o /dev/null -w "%{http_code}" localhost:8000/nope`
Expected: `404`

- [ ] **Step 3: Frontend happy path**

Run: `cd frontend && npm install && npm run dev`
Open `http://localhost:5173` in a browser.
Expected: page renders a single "OpenTourney" heading, no console errors.

- [ ] **Step 4: Frontend build**

Run: `npm run build`
Expected: succeeds, `dist/index.html` exists.

- [ ] **Step 5: Docs build**

Run (repo root): `sphinx-build -b html docs docs/_build -W`
Expected: exit code 0, `docs/_build/index.html` exists.

- [ ] **Step 6: Docker images**

Run: `docker build -t opentourney-backend ./backend && docker build -t opentourney-frontend ./frontend`
Expected: both succeed.

Run: `docker run --rm -p 8000:8000 opentourney-backend` then in another shell `curl -s localhost:8000/healthz`
Expected: `{"status":"ok"}`

- [ ] **Step 7: CI green**

Confirm (from Task 4 Step 3) all six GitHub Actions jobs are green on the pushed branch.

- [ ] **Step 8: Open the PR**

```bash
gh pr create --title "Phase 1: repo scaffold + CI" --body "$(cat <<'EOF'
## Summary
- FastAPI backend skeleton with /healthz (FR1)
- React + TypeScript + Vite frontend skeleton (FR2)
- GitHub Actions CI on badconfig-runners: lint/test both services, docs build, docker build (FR3)
- Sphinx docs scaffold with autodoc enabled (FR4)

Closes Phase 1 of MVP1 (REQUIREMENTS.md).

## Test plan
- [x] Backend: pytest integration test for /healthz
- [x] Frontend: Vitest/Testing Library render test for App
- [x] CI green on badconfig-runners (backend-lint, backend-test, frontend-lint, frontend-test, docs-build, docker-build)
- [x] Manual verification per checklist (see Task 5 of the implementation plan)
EOF
)"
```

Then run `/review`. Do not run `gh pr merge` — owner merges after explicit in-the-moment approval.

---

## Self-Review

**Spec coverage:** FR1 (Task 1), FR2 (Task 2), FR3 (Task 4), FR4 (Task 3) — all four Phase 1 FRs covered. NFR1 (TDD) applied in Tasks 1–2 via explicit red/green steps; Tasks 3–4 are non-code scaffolding verified by build/CI success instead, consistent with how limitless-organizer-tracker's own `mkdocs build --strict`/CI-yaml steps aren't wrapped in a test framework either. NFR3 (staging) explicitly deferred to Phase 2 in Global Constraints. NFR2/NFR4/NFR5 noted as not-yet-exercised, not violated.

**Placeholder scan:** no TBD/TODO markers; every step has literal file content or an exact runnable command with an expected result.

**Type/name consistency:** `app.main:app` (Task 1) matches the CI/Dockerfile CMD (`uvicorn app.main:app`) and the test import (`from app.main import app`). `App` (named export, Task 2 Step 4) matches the import in both `App.test.tsx` and `main.tsx`. Docker image tags `opentourney-backend`/`opentourney-frontend` (Task 4's `docker-build` job) match those used in Task 5 Step 6.

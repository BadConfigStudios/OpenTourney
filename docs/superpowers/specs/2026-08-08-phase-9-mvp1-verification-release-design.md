# Phase 9 — MVP1 Verification + Release Cut (Design)

Date: 2026-08-08
Status: Approved (brainstorming), pending plan/execution
Requirement: FR23, `REQUIREMENTS.md` Build Order phase 9 (last phase of MVP1)
Related: `DEVELOPMENT.md` (existing staging deploy workflow), `DECISIONS.md`
2026-08-05 (Accept-header route dispatch — informs why docs get their own
container rather than riding on backend/frontend nginx), issue #57 (deferred,
not part of this phase — see Out of scope)

---

## 1. Scope

MVP1's Build Order (`REQUIREMENTS.md`) ends at Phase 9: run the full
verification suite, stand up a versioned Sphinx docs site (FR23: data-model
reference via autodoc, API usage guide, deployment guide), deploy it
alongside the existing backend/frontend on the cube cluster staging
environment, and cut the `v0.1.0` release.

**In scope:**
- Full backend pytest + frontend test suite run, lint clean.
- Redeploy current `main` to `opentourney-staging`, manual golden-path
  verification in browser (NFR3 — every phase verified against real
  Kubernetes staging, not deferred).
- Sphinx docs content:
  - `sphinx.ext.autodoc` pointed at `backend/app/models/*` (Event, Pod,
    Entry, Round, Match, RBAC) for the data-model reference. Requires
    adding class/field docstrings to these models — currently undocumented.
  - Hand-written API usage guide: auth flow (OIDC + persona-switcher
    tokens), golden-path request/response walkthrough, links the existing
    `docs/openapi.json`.
  - Deployment guide: adapted from `DEVELOPMENT.md`'s staging section
    (Helm install, Percona PG prereqs, GHCR pull secret, port-forward
    access).
  - `docs/conf.py` updated to add `backend/` to `sys.path` for autodoc
    imports.
- Docs deploy: new `Dockerfile.docs` (multi-stage — `sphinx-build` then
  copy `_build/html` into an nginx static-serve image, mirroring the
  existing frontend container pattern), new `deployment-docs.yaml` +
  `service-docs.yaml` Helm templates in `charts/opentourney`, deployed to
  the `opentourney-staging` namespace. Access via `kubectl port-forward`,
  same exposure level as backend/frontend today — no public Ingress/DNS
  work in this phase.
- Release cut: `CHANGELOG.md` `[0.1.0]` entry (BR1-4, FR1-23/25-26, phases
  1-9 summary) replacing `[Unreleased]`; `REQUIREMENTS.md` Build Order
  Phase 9 row marked done; `git tag v0.1.0` on the commit verified live in
  `opentourney-staging` at sign-off (per MVP delivery model — no rebuild
  just to tag). Tag push and any `main` merge require live owner approval
  at the time, not pre-authorized by this spec.

**Out of scope (explicitly deferred):**
- Multi-version docs switcher (sphinx-multiversion or similar) — only one
  version exists at `v0.1.0`; add when `v0.2.0` ships and versioning
  actually matters.
- Public Ingress/hostname for the docs site (or any component) — cube
  cluster staging remains port-forward-only, consistent with current app
  exposure.
- Issue #57 (labeled/typed tiebreak wire contract) — filed as a Phase 8
  follow-up, not blocking, not part of MVP1 verification.
- Roadmap issues #41-#51 — post-MVP1 scope, not started by this phase.
- NFR6 (OpenAPI contract constraints/examples for third-party consumers) —
  explicitly marked "not required for MVP1 completion" in `REQUIREMENTS.md`.

## 2. Docs content architecture

Three-page minimum under `docs/index.rst`'s toctree:

- `data-model.rst` — `automodule`/`autoclass` directives against
  `app.models.event`, `app.models.pod`, `app.models.entry`,
  `app.models.round`, `app.models.match`, `app.models.rbac`. Each model
  class gets a docstring describing its role in the tournament lifecycle;
  non-obvious fields (e.g. `Entry.dropped_at_round`, timestamp mixins) get
  field-level docstrings where the name alone doesn't explain intent.
- `api-usage.rst` — narrative walkthrough: mint a persona token, create
  Event → Pod → Entries, generate Round 1, report a match result, pull the
  final report. Links `openapi.json` for the full contract rather than
  duplicating it.
- `deployment.rst` — condensed from `DEVELOPMENT.md`: Helm values layering,
  Percona PG Operator prerequisite, `ghcr-pull` secret creation, `helm
  upgrade --install` command, port-forward verification. This becomes the
  canonical version; `DEVELOPMENT.md` can link to it rather than duplicate
  once written, but rewriting `DEVELOPMENT.md` itself is not required by
  this phase.

`docs/opentourney-architecture.md` and `docs/tcg-ruleset-research.md` are
forward-looking roadmap research, not MVP1's shipped data model — not
reused as source content for the data-model reference; the autodoc output
describes what's actually implemented.

## 3. Docs deploy architecture

New Helm-managed component, `docs`, alongside existing `backend`/`frontend`:

- `Dockerfile.docs`: stage 1 builds `sphinx-build -b html docs docs/_build/html`
  with backend installed (for autodoc imports) plus Sphinx; stage 2 copies
  the built HTML into an `nginx:alpine` (or equivalent) static-serve image,
  matching the frontend's existing container shape.
- `charts/opentourney/templates/deployment-docs.yaml` +
  `service-docs.yaml`: single replica, no PG dependency, no
  `ghcr-pull`-gated image if built/pushed the same way as backend/frontend
  (reuse existing image push mechanics — no new registry setup).
- `values.yaml` / `values.staging.yaml` gain a `docs:` block (image tag,
  pull policy, replicas) mirroring the `backend:`/`frontend:` shape.
- Verification: `kubectl port-forward svc/docs 8080:80` (or similar),
  confirm autodoc pages render with real model docstrings, API usage guide
  and deployment guide readable, OpenAPI download link still works.

Rejected: serving docs from the existing backend or frontend nginx
container. `DECISIONS.md` 2026-08-05 already routes `frontend`'s nginx on
`Accept` header to resolve path collisions with the backend API; adding a
third concern (static docs) to that same routing surface compounds an
already-fragile mechanism instead of using a clean, independent container.

## 4. Verification checklist (for the manual gate)

- [ ] `pytest` (backend) full suite passes
- [ ] Frontend test suite passes
- [ ] `ruff` (or configured linter) clean
- [ ] `sphinx-build -b html docs docs/_build/html` succeeds with no errors,
      autodoc renders model docstrings (not just bare field lists)
- [ ] `helm upgrade --install` succeeds for backend/frontend/docs on
      `opentourney-staging`
- [ ] Golden path re-verified in browser against redeployed staging:
      create Event/Pod/Entries → Round 1 pairings → BO1 report → subsequent
      round → final standings with real tiebreakers (Phase 8 regression)
- [ ] Docs site reachable via port-forward, all three new pages render
      correctly, OpenAPI download link works
- [ ] `CHANGELOG.md` `[0.1.0]` entry accurate against actual shipped scope
- [ ] `REQUIREMENTS.md` Build Order Phase 9 row updated

## 5. Testing

- No new application behavior — this phase adds documentation and a static
  docs-serving container. TDD (NFR1) doesn't apply in the usual
  red/green/refactor sense; "tests" here are the verification checklist
  above.
- `.github/workflows/ci.yml:76` already runs `sphinx-build -b html docs
  docs/_build -W` (warnings-as-errors) — confirmed existing, no new CI step
  needed. This phase's autodoc additions must build clean under that
  existing `-W` gate (a broken cross-reference or import fails CI as-is).

## 6. Open questions

None outstanding — all four design sections were reviewed and approved
section-by-section with the owner during brainstorming (2026-08-08).

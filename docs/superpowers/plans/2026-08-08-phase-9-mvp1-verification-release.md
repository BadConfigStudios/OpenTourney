# Phase 9 — MVP1 Verification + Release Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Sphinx docs site required by FR23 (data-model reference via autodoc, API usage guide, deployment guide), deploy it alongside backend/frontend on the cube cluster staging environment, and cut the `v0.1.0` release, closing out MVP1's Build Order.

**Architecture:** Three new/expanded Sphinx pages under `docs/`, sourced from real docstrings added to `backend/app/models/*` and real endpoint/schema data already in the codebase. A new `docs` Helm component (`Dockerfile.docs` → nginx static-serve, mirroring the existing frontend container pattern) deploys the built site to `opentourney-staging`. Release cut is two doc edits (`CHANGELOG.md`, `REQUIREMENTS.md`) plus a `git tag` gated on the manual verification pass.

**Tech Stack:** Sphinx 7.4+ (`sphinx.ext.autodoc`, already enabled in `docs/conf.py`), reStructuredText, nginx:alpine, Helm.

## Global Constraints

- FR23: docs must cover data-model reference (autodoc), API usage guide, deployment guide, versioned per release.
- NFR3: every phase verified against the real Kubernetes staging environment, not deferred.
- No public Ingress/hostname work — docs reachable via `kubectl port-forward`, same exposure level as backend/frontend today.
- No multi-version docs switcher — single static build stamped `release = "0.1.0"` (already set in `docs/conf.py`), add versioning tooling at `v0.2.0`.
- `backend[dev]` (installed editable in CI's `docs-build` job, `.github/workflows/ci.yml:75`) already provides `sphinx>=7.4` and makes `app.*` importable — **no `sys.path` edit needed in `docs/conf.py`**, correcting the design spec's assumption on this point.
- `.github/workflows/ci.yml:76` already runs `sphinx-build -b html docs docs/_build -W` (warnings-as-errors) — all new autodoc/rst content must build clean under that existing gate.
- Tag push and `main` merge require live owner approval at the time — not pre-authorized by this plan.

---

## File Structure

- `backend/app/models/base.py`, `event.py`, `pod.py`, `entry.py`, `round.py`, `match.py`, `rbac.py` — add class/field docstrings (no behavior change).
- `docs/data-model.rst` — new, `autoclass` directives against the six model files above.
- `docs/api-usage.rst` — new, narrative golden-path walkthrough (mint token → create Event/Pod/Entries → generate round → report result → pull report).
- `docs/deployment.rst` — new, condensed from `DEVELOPMENT.md`'s Staging deployment section, extended to cover the new `docs` image.
- `docs/index.rst` — modify, toctree gains the three new pages.
- `docs/Dockerfile.docs` — new, multi-stage build (sphinx-build then nginx:alpine), build context is repo root.
- `charts/opentourney/templates/deployment-docs.yaml`, `service-docs.yaml` — new, mirror `deployment-frontend.yaml`/`service-frontend.yaml`.
- `charts/opentourney/values.yaml`, `values.staging.yaml` — modify, add `docs:` block.
- `.github/workflows/ci.yml` — modify, add `docker build -f docs/Dockerfile.docs -t opentourney-docs .` to the `docker-build` job.
- `DEVELOPMENT.md` — modify, extend the build/push/deploy commands to include the `docs` image; fix stale "lands with the `v0.1.0` cut in Phase 8" reference to Phase 9.
- `CHANGELOG.md` — modify, `[0.1.0]` entry replacing `[Unreleased]`.
- `REQUIREMENTS.md` — modify, Build Order Phase 9 row marked done.

---

## Task 1: Data-model reference (docstrings + autodoc page)

**Files:**
- Modify: `backend/app/models/base.py`, `backend/app/models/event.py`, `backend/app/models/pod.py`, `backend/app/models/entry.py`, `backend/app/models/round.py`, `backend/app/models/match.py`, `backend/app/models/rbac.py`
- Create: `docs/data-model.rst`
- Modify: `docs/index.rst`

**Interfaces:**
- Consumes: nothing (docstrings only, no import/signature changes).
- Produces: nothing consumed by later tasks — Task 2/3 add sibling pages independently.

- [ ] **Step 1: Add docstrings to `backend/app/models/base.py`**

```python
class Base(DeclarativeBase):
    """Declarative base for all OpenTourney ORM models, with a fixed
    Alembic-friendly constraint-naming convention."""

    metadata = MetaData(naming_convention=convention)


class UUIDPrimaryKeyMixin:
    """Adds a server-generated UUID primary key (`id`) to a model."""

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    """Adds a `created_at` column, set once by the database on insert."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Add docstring to `backend/app/models/event.py`**

```python
class Event(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single-day in-person tournament event, identified by its date.

    MVP1 restricts an Event to at most one Pod — see `Pod`'s
    `uq_pod_event` unique constraint.
    """

    __tablename__ = "events"
```

- [ ] **Step 3: Add docstring to `backend/app/models/pod.py`**

```python
class Pod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One tournament instance within an Event — the unit a
    `TournamentFormat` (`format_slug`, e.g. ``"swiss"``) and `GameModule`
    (`game_slug`, e.g. ``"generic"``) actually run against.

    `completed_at` is set when the organizer concludes the pod (see
    `POST /pods/{pod_id}/complete`); a completed pod's final standings are
    available via `GET /pods/{pod_id}/report`.
    """

    __tablename__ = "pods"
```

- [ ] **Step 4: Add docstring to `backend/app/models/entry.py`**

```python
class Entry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A player's registration within a Pod.

    OpenTourney owns no accounts (NFR4) — a player is identified by the
    `(player_uuid, source_system)` pair asserted by an external identity
    provider, not a local user record. `source_system` names which
    external system minted `player_uuid` (e.g. a specific OIDC issuer).

    The `metadata` column is a free-form JSONB bag for ruleset/game-module
    data (e.g. deck list); the Python attribute is `metadata_` because
    SQLAlchemy's `DeclarativeBase` reserves `.metadata` for its own use —
    the API layer (`EntryRead`) maps it back to `metadata` for callers.
    """

    __tablename__ = "entries"
```

- [ ] **Step 5: Add docstrings to `backend/app/models/round.py`**

```python
class Round(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One generated round of pairings within a Pod's Swiss sequence.

    `number` is 1-indexed and unique per pod. `matches` holds every
    pairing generated for this round, including byes (a `Match` with
    `entry2_id is None`), ordered by insertion.
    """

    __tablename__ = "rounds"
```

- [ ] **Step 6: Add docstrings to `backend/app/models/match.py`**

```python
class MatchResult(str, enum.Enum):
    """A match's outcome. `UNREPORTED` until a result is submitted via
    `POST /matches/{match_id}/result`; terminal values are the two win
    outcomes and `TIE` (draw)."""

    UNREPORTED = "unreported"
    ENTRY1_WIN = "entry1_win"
    ENTRY2_WIN = "entry2_win"
    TIE = "tie"


class Match(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single pairing between two entries within a Round.

    `entry2_id` is nullable — `None` marks a bye (`entry1_id` receives an
    automatic win, no result reporting required). `confirmed_by` is a
    JSONB audit-trail list recording who confirmed the reported result;
    `reported_by`/`witnessed_by` are set from the reporting identity's
    `source_system:player_uuid` (see `report_match_result`).
    """

    __tablename__ = "matches"
```

- [ ] **Step 7: Add docstrings to `backend/app/models/rbac.py`**

```python
class PodRoleName(str, enum.Enum):
    """Roles grantable within a single Pod. `SCOREKEEPER` may report match
    results; `USER` is a non-privileged grant (currently unused by any
    authorization check, reserved for future use)."""

    SCOREKEEPER = "scorekeeper"
    USER = "user"


class EventOrganizer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity (`player_uuid` + `source_system`,
    NFR4) organizer rights over an Event — create/update Pods and Entries,
    generate rounds, complete the event."""

    __tablename__ = "event_organizers"


class PodRole(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity a `PodRoleName` role scoped to a
    single Pod, independent of any `EventOrganizer` grant on the parent
    Event."""

    __tablename__ = "pod_roles"
```

- [ ] **Step 8: Write `docs/data-model.rst`**

```rst
Data Model Reference
=====================

OpenTourney's tournament data model, generated from the SQLAlchemy models
in ``backend/app/models``. See :doc:`api-usage` for how these map onto the
published REST API, and the `OpenAPI spec <openapi.json>`_ for exact
request/response schemas.

Event
-----

.. autoclass:: app.models.event.Event
   :members:
   :undoc-members:

Pod
---

.. autoclass:: app.models.pod.Pod
   :members:
   :undoc-members:

Entry
-----

.. autoclass:: app.models.entry.Entry
   :members:
   :undoc-members:

Round
-----

.. autoclass:: app.models.round.Round
   :members:
   :undoc-members:

Match
-----

.. autoclass:: app.models.match.Match
   :members:
   :undoc-members:

.. autoclass:: app.models.match.MatchResult
   :members:
   :undoc-members:

RBAC
----

.. autoclass:: app.models.rbac.EventOrganizer
   :members:
   :undoc-members:

.. autoclass:: app.models.rbac.PodRole
   :members:
   :undoc-members:

.. autoclass:: app.models.rbac.PodRoleName
   :members:
   :undoc-members:
```

- [ ] **Step 9: Wire into the toctree — `docs/index.rst`**

```rst
OpenTourney
===========

Game-agnostic, open tournament-tracking standard and engine.

`Download the OpenAPI spec (JSON) <openapi.json>`_

.. toctree::
   :maxdepth: 2

   data-model
   api-usage
   deployment
```

- [ ] **Step 10: Build the docs and verify autodoc rendered real content**

Run: `cd backend && pip install -e ".[dev]" && cd .. && sphinx-build -b html docs docs/_build -W`
Expected: build succeeds with no warnings/errors.

Run: `grep -o "single-day in-person tournament" docs/_build/data-model.html`
Expected: prints a match — confirms the `Event` docstring rendered, not just a bare field list.

- [ ] **Step 11: Commit**

```bash
git add backend/app/models/base.py backend/app/models/event.py backend/app/models/pod.py backend/app/models/entry.py backend/app/models/round.py backend/app/models/match.py backend/app/models/rbac.py docs/data-model.rst docs/index.rst
git commit -m "docs(phase-9): add data-model reference page (FR23)"
```

---

## Task 2: API usage guide

**Files:**
- Create: `docs/api-usage.rst`

**Interfaces:**
- Consumes: nothing new — describes existing endpoints (`app/routers/*`) and `backend/scripts/mint_test_token.py`, both already implemented.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write `docs/api-usage.rst`**

```rst
API Usage Guide
================

OpenTourney has no login flow of its own (NFR4) — every request carries a
bearer JWT asserting an external identity. This guide walks the golden
path: mint a token, create an Event through to a finished Pod's report.

Authentication
--------------

Every endpoint (except ``/healthz``) requires ``Authorization: Bearer
<token>``, verified against the configured OIDC issuer's JWKS. For manual
testing against a static-JWKS deployment (``secrets.oidcJwksStatic``, see
:doc:`deployment`), mint a token with the backend's helper script:

.. code-block:: bash

   python backend/scripts/mint_test_token.py \
     --private-key-path <path-to-pem> \
     --kid <kid> \
     --issuer <issuer> \
     --audience <audience> \
     --organizer

``--organizer`` includes the ``organizer`` role claim, required for
event-management endpoints below. Omit it to mint a non-organizer token
(sufficient for match-result reporting as a Scorekeeper, once granted a
``PodRole``).

Export the result for the examples below:

.. code-block:: bash

   TOKEN=$(python backend/scripts/mint_test_token.py --organizer ...)

Golden path
-----------

1. **Create an Event** (organizer-only):

   .. code-block:: bash

      curl -X POST http://localhost:8000/events \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"date": "2026-08-08"}'

   Returns an ``EventRead`` — note its ``id``.

2. **Create a Pod** within that event (MVP1: one pod per event, Swiss
   format, generic game module):

   .. code-block:: bash

      curl -X POST http://localhost:8000/pods \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"event_id": "<event-id>", "format_slug": "swiss", "game_slug": "generic"}'

3. **Add Entries** (one per player):

   .. code-block:: bash

      curl -X POST http://localhost:8000/entries \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"pod_id": "<pod-id>", "player_uuid": "<uuid>", "source_system": "manual-verification"}'

4. **Generate Round 1** (organizer-only; pairs all current entries):

   .. code-block:: bash

      curl -X POST http://localhost:8000/pods/<pod-id>/rounds \
        -H "Authorization: Bearer $TOKEN"

   Returns a ``RoundRead`` with its ``matches`` — a bye match has
   ``entry2_id: null`` and needs no result.

5. **Report a match result** (Organizer or Scorekeeper):

   .. code-block:: bash

      curl -X POST http://localhost:8000/matches/<match-id>/result \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"result": "entry1_win"}'

   ``result`` is one of ``entry1_win``, ``entry2_win``, ``tie``.

6. **Generate subsequent rounds** by repeating step 4 — pairings are
   computed from current standings, including OMW%/OOMW% tiebreakers
   (FR25).

7. **Pull the final report** once every match in the pod is resolved:

   .. code-block:: bash

      curl http://localhost:8000/pods/<pod-id>/report -H "Authorization: Bearer $TOKEN"

   Returns a ``PodReport``: ``is_complete``, ``rounds_played``, and ranked
   ``standings`` (points + tiebreaker values per entry).

See the `OpenAPI spec <openapi.json>`_ for the full schema of every
request/response body, and :doc:`data-model` for what each field means at
the database layer.
```

- [ ] **Step 2: Build and verify**

Run: `sphinx-build -b html docs docs/_build -W`
Expected: build succeeds with no warnings — confirms the `:doc:` cross-references to `deployment` and `data-model` resolve (both exist after Task 1/3).

- [ ] **Step 3: Commit**

```bash
git add docs/api-usage.rst
git commit -m "docs(phase-9): add API usage guide (FR23)"
```

---

## Task 3: Deployment guide

**Files:**
- Create: `docs/deployment.rst`
- Modify: `DEVELOPMENT.md` (fix stale Phase 8 reference)

**Interfaces:**
- Consumes: nothing new — condenses `DEVELOPMENT.md`'s existing Staging deployment section.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write `docs/deployment.rst`**

```rst
Deployment Guide
==================

OpenTourney deploys to a Kubernetes cluster via the Helm chart in
``charts/opentourney``. This page covers the staging workflow; see
``DEVELOPMENT.md`` in the repo root for the full, up-to-date reference
(prerequisites, gotchas) — this page is the condensed version for docs-site
readers without repo access.

Prerequisites
-------------

- **Percona PG Operator v3** installed and watching the target namespace
  (the chart's ``PerconaPGCluster`` resource requires it). For a
  database-less bring-up, pass ``--set percona.enabled=false``.
- **A namespaced GHCR pull secret** named ``ghcr-pull``:

  .. code-block:: bash

     kubectl -n <namespace> create secret docker-registry ghcr-pull \
       --docker-server=ghcr.io \
       --docker-username=<github-username> \
       --docker-password="$(gh auth token)"

- **Required secrets values** — ``secrets.databaseUrl`` (enforced via
  Helm's ``required``), ``secrets.oidcIssuer``, ``secrets.oidcAudience``,
  and one of ``secrets.oidcJwksUrl`` / ``secrets.oidcJwksStatic``.

Deploy workflow
----------------

1. **Build and push images** (backend, frontend, and docs) from the target
   commit:

   .. code-block:: bash

      docker build --platform linux/amd64 -t ghcr.io/badconfigstudios/opentourney/backend:<tag> -f backend/Dockerfile.prod ./backend
      docker build --platform linux/amd64 -t ghcr.io/badconfigstudios/opentourney/frontend:<tag> -f frontend/Dockerfile.prod ./frontend
      docker build --platform linux/amd64 -t ghcr.io/badconfigstudios/opentourney/docs:<tag> -f docs/Dockerfile.docs .

      docker push ghcr.io/badconfigstudios/opentourney/backend:<tag>
      docker push ghcr.io/badconfigstudios/opentourney/frontend:<tag>
      docker push ghcr.io/badconfigstudios/opentourney/docs:<tag>

2. **Deploy the release**:

   .. code-block:: bash

      helm upgrade --install opentourney-staging charts/opentourney \
        --namespace opentourney-staging --create-namespace \
        -f charts/opentourney/values.staging.yaml \
        --set backend.image.tag=<tag> \
        --set frontend.image.tag=<tag> \
        --set docs.image.tag=<tag> \
        --set-string secrets.databaseUrl=<database-url> \
        --set-string secrets.oidcIssuer=<oidc-issuer> \
        --set-string secrets.oidcAudience=<oidc-audience> \
        --set-string secrets.oidcJwksStatic=<oidc-jwks-static-json>

3. **Verify** via port-forward (no public hostname yet for any
   component):

   .. code-block:: bash

      kubectl -n opentourney-staging port-forward svc/backend 8000:8000
      kubectl -n opentourney-staging port-forward svc/docs 8080:80

      curl http://localhost:8000/healthz
      curl http://localhost:8080/  # docs site index

See :doc:`api-usage` for exercising the backend once it's reachable.
```

- [ ] **Step 2: Fix stale Phase 8 reference in `DEVELOPMENT.md`**

In the "Staging deployment" intro paragraph, replace:

```
staging is not managed by Fleet/GitOps (no production release exists yet; that
lands with the `v0.1.0` cut in Phase 8).
```

with:

```
staging is not managed by Fleet/GitOps (no production release exists yet; that
lands with the `v0.1.0` cut in Phase 9).
```

- [ ] **Step 3: Build and verify**

Run: `sphinx-build -b html docs docs/_build -W`
Expected: build succeeds with no warnings.

- [ ] **Step 4: Commit**

```bash
git add docs/deployment.rst DEVELOPMENT.md
git commit -m "docs(phase-9): add deployment guide, fix stale Phase 8 reference (FR23)"
```

---

## Task 4: Docs container + Helm deploy

**Files:**
- Create: `docs/Dockerfile.docs`
- Create: `charts/opentourney/templates/deployment-docs.yaml`
- Create: `charts/opentourney/templates/service-docs.yaml`
- Modify: `charts/opentourney/values.yaml`
- Modify: `charts/opentourney/values.staging.yaml`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `docs/` built by `sphinx-build` (Tasks 1-3's content), `backend/` as installed by `pip install -e "backend[dev]"`.
- Produces: `docs` Service reachable at port 80 in-cluster, matching the `backend`/`frontend` Service naming pattern (`ot.labels`/`ot.fullname` helpers from `_helpers.tpl`).

- [ ] **Step 1: Write `docs/Dockerfile.docs`**

```dockerfile
FROM python:3.12-slim AS build

WORKDIR /app

COPY backend/ backend/
RUN pip install --no-cache-dir -e "backend[dev]"

COPY docs/ docs/
RUN sphinx-build -b html docs docs/_build -W

FROM nginx:alpine

COPY --from=build /app/docs/_build /usr/share/nginx/html

EXPOSE 80
```

- [ ] **Step 2: Verify the image builds (context is repo root)**

Run: `docker build -t opentourney-docs -f docs/Dockerfile.docs .`
Expected: build succeeds; final stage is `nginx:alpine` with the built site copied in.

Run: `docker run --rm -d -p 8080:80 --name ot-docs-test opentourney-docs && sleep 1 && curl -sf http://localhost:8080/ | grep -o "OpenTourney" && docker stop ot-docs-test`
Expected: prints `OpenTourney` — confirms the built index page serves.

- [ ] **Step 3: Write `charts/opentourney/templates/deployment-docs.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "ot.fullname" . }}-docs
  labels:
    {{- include "ot.labels" . | nindent 4 }}
    app.kubernetes.io/component: docs
spec:
  replicas: {{ .Values.docs.replicas }}
  selector:
    matchLabels:
      app.kubernetes.io/component: docs
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/component: docs
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
        - name: docs
          image: "{{ .Values.docs.image.repository }}:{{ .Values.docs.image.tag }}"
          imagePullPolicy: {{ .Values.docs.image.pullPolicy }}
          ports:
            - containerPort: {{ .Values.docs.port }}
          readinessProbe:
            httpGet:
              path: /
              port: {{ .Values.docs.port }}
            initialDelaySeconds: 5
            periodSeconds: 10
```

- [ ] **Step 4: Write `charts/opentourney/templates/service-docs.yaml`**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: docs
  labels:
    {{- include "ot.labels" . | nindent 4 }}
    app.kubernetes.io/component: docs
spec:
  selector:
    app.kubernetes.io/component: docs
    app.kubernetes.io/instance: {{ .Release.Name }}
  ports:
    - port: 80
      targetPort: {{ .Values.docs.port }}
```

- [ ] **Step 5: Add `docs:` block to `charts/opentourney/values.yaml`**

Add after the existing `frontend:` block:

```yaml
docs:
  image:
    repository: ghcr.io/badconfigstudios/opentourney/docs
    tag: latest
    pullPolicy: Always
  replicas: 1
  port: 80
```

- [ ] **Step 6: Add `docs:` block to `charts/opentourney/values.staging.yaml`**

Add after the existing `frontend:` block:

```yaml
docs:
  image:
    tag: latest
    pullPolicy: Always
  replicas: 1
```

- [ ] **Step 7: Add docs build to CI's `docker-build` job — `.github/workflows/ci.yml`**

Add after the existing `docker build -t opentourney-frontend-prod ...` line:

```yaml
      - run: docker build -t opentourney-docs -f docs/Dockerfile.docs .
```

- [ ] **Step 8: Verify the chart renders**

Run: `helm template opentourney-staging charts/opentourney -f charts/opentourney/values.staging.yaml --set-string secrets.databaseUrl=x --set-string secrets.oidcIssuer=x --set-string secrets.oidcAudience=x --set-string secrets.oidcJwksStatic=x`
Expected: renders without error, output includes a `Deployment` and `Service` named with `-docs` / `docs` for the new component.

- [ ] **Step 9: Commit**

```bash
git add docs/Dockerfile.docs charts/opentourney/templates/deployment-docs.yaml charts/opentourney/templates/service-docs.yaml charts/opentourney/values.yaml charts/opentourney/values.staging.yaml .github/workflows/ci.yml
git commit -m "feat(infra): deploy docs site via new Helm docs component"
```

---

## Task 5: Release cut docs

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `REQUIREMENTS.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing — this is the terminal task; the `git tag v0.1.0` step happens after Task 6's manual verification, not here.

- [ ] **Step 1: Replace `[Unreleased]` with `[0.1.0]` in `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project are documented here, one entry per
MVP tag. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] — MVP1: Core In-Person Swiss Engine

Serves BR1-BR4 / FR1-23, FR25-26. Full Build Order: phases 1-9.

### Added

- Repo scaffold (FastAPI + React/TS/Vite), CI, Sphinx docs scaffold (Phase 1)
- Kubernetes staging deployment via Helm + Percona PG Operator (Phase 2)
- Domain model: Event/Pod/Entry/Round/Match, `TournamentFormat` +
  `GameModule` plugin interfaces (Phase 3)
- Swiss pairing/round generation and seating (Phase 4)
- Operational API, RBAC, OIDC auth, published OpenAPI spec (Phase 5)
- Match and tournament reporting: BO1 results with provenance, final
  report (Phase 6)
- Operational UI: setup, pairings/seating, BO1 scoring, final report,
  persona switcher (Phase 7)
- Real Swiss tiebreakers (OMW%/OOMW%) behind a pluggable
  `TiebreakStrategy` interface, replacing the UUID-string stopgap (Phase 8,
  FR25)
- Versioned Sphinx docs site: data-model reference (autodoc), API usage
  guide, deployment guide; deployed to staging (Phase 9, FR23)

### Known follow-ups (not blocking, tracked as issues)

- #57 — tiebreak API/UI wire contract has no label/strategy identifier;
  needed before a second `TiebreakStrategy` family ships under #41.
```

- [ ] **Step 2: Mark Phase 9 done in `REQUIREMENTS.md`**

In the Build Order table, change the Phase 9 row from:

```
| 9 | MVP1 verification (full suite, staging verification, versioned docs site, release cut `v0.1.0`) | MVP1 |
```

to:

```
| 9 | MVP1 verification (full suite, staging verification, versioned docs site, release cut `v0.1.0`) | MVP1 — done |
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md REQUIREMENTS.md
git commit -m "docs(phase-9): cut CHANGELOG [0.1.0], mark Phase 9 done in REQUIREMENTS.md"
```

---

## Task 6: Manual verification gate + release (not a subagent task)

Per `~/.claude/CLAUDE.md`'s Manual verification section, this is the
mandatory pre-merge gate — run by the session owner/controller after
Tasks 1-5 are code-reviewed, not delegated to a subagent, and not
satisfied by "tests pass" alone.

**Checklist:**

- [ ] `pytest` (backend) full suite passes
- [ ] Frontend test suite passes
- [ ] `ruff` clean
- [ ] `sphinx-build -b html docs docs/_build -W` succeeds with real
      docstring content rendered (not bare field lists)
- [ ] Build and push `backend`, `frontend`, `docs` images from this
      branch's HEAD (per `docs/deployment.rst`)
- [ ] `helm upgrade --install` succeeds against `opentourney-staging`
- [ ] Golden path re-verified in browser against redeployed staging:
      create Event/Pod/Entries → Round 1 pairings → BO1 report →
      subsequent round → final standings with real tiebreakers
- [ ] Docs site reachable via `kubectl port-forward svc/docs`, all three
      new pages render, OpenAPI download link works
- [ ] `CHANGELOG.md`/`REQUIREMENTS.md` entries checked against actual
      shipped scope

**Only after every item above passes and the owner confirms:**

- [ ] `git tag v0.1.0` on the commit currently verified live in
      `opentourney-staging` (no rebuild solely to tag)
- [ ] Push the tag and merge to `main` — **both require explicit,
      in-the-moment owner approval**, not inferred from this plan's
      existence

---

## Self-Review Notes

- **Spec coverage:** all four design-doc sections (verification,
  docs content, docs deploy, release cut) map to Tasks 1-6 above.
- **Correction from spec:** `docs/conf.py` needs no `sys.path` edit —
  `backend[dev]` is already installed editable in CI's docs-build job, so
  `import app.models...` resolves without it. No task adds this edit.
- **Correction from spec:** the design doc's data-model description
  mentioned `Entry.dropped_at_round` as a field to document — that field
  doesn't exist yet (it's FR24, explicitly deferred post-MVP1). Task 1's
  `Entry` docstring does not reference it.
- **Type/name consistency:** `docs.image.repository`,
  `docs.image.tag`, `docs.image.pullPolicy`, `docs.replicas`, `docs.port`
  used identically across `values.yaml`, `values.staging.yaml`,
  `deployment-docs.yaml`, `service-docs.yaml` (Task 4).

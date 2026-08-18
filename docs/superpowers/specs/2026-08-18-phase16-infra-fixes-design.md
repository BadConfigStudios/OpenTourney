# Phase 16 infra fix PR — issue #88 blockers #1-3 + low-LOE minors

**Status:** Approved, ready for planning.
**Precedes:** Phase 16 PR2 (frontend `oidc-client-ts` integration, issue #82/FR36) — PR2's plan already exists at `docs/superpowers/plans/2026-08-17-phase16-pr2-frontend-oidc.md` and assumes the fixes below are already live.
**Origin:** Issue #88 — deferred findings from Phase 16 PR1's (#89, merged as `f9e4c95`) final whole-branch review.

## Goal

Fix the 3 infra issues that block PR2's manual staging login walkthrough (Task 6 of the PR2 plan), plus a handful of low-LOE cleanup items from the same review pass. This PR touches only `charts/opentourney/` and `DEVELOPMENT.md` — no frontend code.

## Why this PR exists separately from PR2

None of the 3 blockers touch frontend code; all are backend/infra (Helm chart, `bootstrap.py`, `DEVELOPMENT.md`). Landing them first keeps PR2 code-only and gives its Task 6 walkthrough (real browser login as organizer/scorekeeper/player) a real chance of passing on the first attempt, instead of debugging infra and frontend code changes simultaneously.

## Fixes

### 1. `publicBaseUri` "bare host" claim is wrong

**Current state:** Three places (`values.yaml`'s comment on `zitadel.login.publicBaseUri`, `bootstrap.py`'s comment on `LOGIN_V2_BASE_URI`, and `DEVELOPMENT.md`'s "double `/ui/v2/login`" troubleshooting note) assert that Zitadel's `defaultBaseURL()` appends `/ui/v2/login` itself, so the value passed here must be a bare host. But `values.staging.yaml` — the only configuration ever verified end-to-end — sets `publicBaseUri: "https://opentourney-staging.badconfig.com/ui/v2/login"`, **with** the suffix. The bare-host claim was never live-verified and is contradicted by the one config that works.

**Fix:**
- Correct the three comments to state the suffix is required.
- `DEVELOPMENT.md`'s "double `/ui/v2/login`" troubleshooting note is also stale — it predates PR1's `externalSecure: true` cutover and describes the old bare-host-is-correct assumption. Rewrite it to match reality.
- Append `/ui/v2/login` to the in-cluster fallback default in `zitadel-deployment.yaml` (the `{{ .Values.zitadel.login.publicBaseUri | default (printf "http://%s-zitadel-login:3000" ...) }}` fallback used when `publicBaseUri` is unset), for consistency with the only shape ever confirmed working.
- No change needed to `values.staging.yaml` — it's already correct.

### 2. `FRONTEND_APP_REDIRECT_URI` is stale, and re-running bootstrap can't fix it

**Current state:** `bootstrap.py` hardcodes `FRONTEND_APP_REDIRECT_URI = "http://opentourney-staging.local/callback"`, predating PR1's migration to the real public hostname. `get_or_create_application()`'s 409-idempotent path never PUTs redirect URIs on an already-existing app, so fixing the constant alone won't fix the already-registered `opentourney-frontend` app.

**Fix:**
- Derive the real callback URL from chart values instead of hardcoding it: `https://<ingress.hostname>/callback`. The frontend and Zitadel already share one public origin by this chart's single-domain gateway design (see `gateway-ingress.yaml`), so `ingress.hostname` is the correct source. Compute this in the chart (reusing the existing `ot.zitadelOrigin` helper pattern already used for `ZITADEL_SYSTEM_API_AUDIENCE`) and pass it to the bootstrap container as a new env var (e.g. `ZITADEL_FRONTEND_APP_REDIRECT_URI`); `bootstrap.py` reads it instead of the hardcoded constant.
- Add an update-on-already-exists branch to `get_or_create_application()`, mirroring the existing PUT-on-409 pattern in `get_or_create_action()` (PUT the current fields; treat a "no changes" 400 the same way `set_trigger`/`get_or_create_action` already do). This self-heals the already-registered app on the next `helm upgrade` — no manual one-time Console fix required.
- **devMode:** the corrected URI is HTTPS, and staging already runs `zitadel.externalSecure: true`. Zitadel's real policy (HTTPS required for non-loopback redirect URIs) is already satisfied, so `devMode: true` is very likely unnecessary — the existing `DEVELOPMENT.md` note claiming it's needed describes an old HTTP-only (`externalSecure: false`) deployment, not staging today. Don't guess: verify live during this PR's own verification step (below) and only add the flag if a real `400` proves it's needed.

### 3. `gateway-ingress.yaml` doesn't route several OIDC endpoints

**Current state:** Only `/oauth` and `/.well-known` route to core Zitadel. `/oidc/v1/userinfo`, `/oidc/v1/end_session`, `/idps/callback`, `/v2/*` fall through to the frontend's SPA catch-all and return `200` with the SPA shell instead of a 404 — a failure mode invisible to status-code checks. PR2's `oidc-client-ts` will call at least `/oidc/v1/userinfo`, likely `/oidc/v1/end_session`.

**Fix:** Add `/oidc`, `/idps`, `/v2` to the Zitadel-backend path block in `gateway-ingress.yaml`, same `Prefix` pattern as the existing `/oauth`/`.well-known` entries. Leave `/ui/console` unrouted — nothing in this project uses Zitadel's Console UI, and there's no reason to expose an unused admin surface publicly.

## Low-LOE minors folded in

- **#5** — `DEVELOPMENT.md`'s "Public URL: TBD" line and the deploy-workflow section are stale (predate the Cloudflare Tunnel + `staging-upgrade.sh` setup). Update to the real staging URL and mention `scripts/staging-upgrade.sh` and the committed `values.staging.yaml` settings. Falls out naturally since this PR is already editing `DEVELOPMENT.md` for #1/#2.
- **#6** — `zitadel-login-deployment.yaml` is missing `enableServiceLinks: false`. Core's deployment already sets this with a comment explaining why (kubelet injects `{SVCNAME}_*` env vars that collide with Zitadel's own config vars); the login pod receives the same injected `ZITADEL_*` vars and reads `ZITADEL_EXTERNALDOMAIN` too. Add the same line + comment.
- **#8** — No guard that `ingress.hostname` and `zitadel.externalDomain` agree. A mismatch reproduces a 404/401 failure class already debugged twice on this branch (per issue #88's own history). Add a `fail` guard (~3 lines) alongside the existing `ingress.hostname`-required check in `gateway-ingress.yaml`, only when `zitadel.enabled` — this chart supports Zitadel-disabled deployments where the two are unrelated.
- **#9** — `bootstrap.py`'s `SYSTEM_API_USER`/`SYSTEM_API_KEY_PATH`/`SYSTEM_API_AUDIENCE` constants sit mid-file. Move them up next to the other module-level constants (`ZITADEL_BASE`, `ROLES`, `PROJECT_NAME`, etc.).

## Explicitly out of scope

- **Issue #88 item #4** (unpinned `pip install` in the `bootstrap` container, which now mounts a `SYSTEM_OWNER` key) — flagged in the issue itself as "not low-LOE." Stays open as a separate follow-up.
- **Minor #7** (missing checksum annotations on the bootstrap-system-key and login-service-key Secrets) — only bites a delete-and-recreate recovery scenario; lower value than the items above. Stays open in issue #88.
- **Minor #10** (claimed hand-quoted `ZITADEL_EXTERNALDOMAIN` instead of `| quote`) — checked current `zitadel-deployment.yaml`, `zitadel-login-deployment.yaml`, and `zitadel-login-configmap.yaml` on `origin/main`: every occurrence already uses the `| quote` filter. Already resolved (likely fixed opportunistically during PR1's own review-fix commits). No action; close as already-fixed when this PR references issue #88.
- **Minor #11** (`staging-upgrade.sh` hardcodes context/namespace/release, incompatible with the per-customer-namespace prod model) — issue #88 itself says "fine for now." Tied to the prod multi-tenancy model already committed to in `DECISIONS.md`, better addressed when that work starts, not bundled here.

## Verification

Since this PR's whole purpose is unblocking PR2's live walkthrough, verify live here rather than deferring to PR2:

1. `helm lint` + `helm template` render clean (existing pattern from PR1's plan).
2. Deploy to staging (`scripts/staging-upgrade.sh` or documented `helm upgrade`).
3. Confirm the bootstrap sidecar's log shows the `opentourney-frontend` app's redirect URI updated to the real HTTPS callback URL (via the new update-on-exists path) — check the Management API or a direct `kubectl exec` query against the existing app, not just the log line.
4. `curl` the 3 newly-routed paths (`/oidc/v1/userinfo` unauthenticated, `/idps/...`, `/v2/features/instance` unauthenticated) and confirm they return a real Zitadel error response (e.g. `401`/`404` from core), not `200` with the frontend's `index.html`.
5. Manually drive one real browser login (organizer) through Login V2 end-to-end — confirms #1 and #2 together (correct `publicBaseUri` redirect + correct registered callback URI accepted without a 400). This is a lighter version of PR2 Task 6's walkthrough, done here specifically to isolate infra failures from frontend failures before PR2 starts.
6. If step 5 hits a `400` on the authorize/callback step, add `devMode: true` to `get_or_create_application()`'s request body, redeploy, and retry — per the design note above, only as a fallback, not a default.

## Testing

This is a Helm chart + one Python script; no unit test suite exists for `bootstrap.py` today. Verification is the manual staging walkthrough above (steps 1-2 are the closest thing to an automated check — `helm lint`/`helm template` catch template-rendering errors). No new automated test infra proposed — matches this repo's existing pattern for this chart (PR1 also verified live, not via automated tests, per its own plan's Task 8).

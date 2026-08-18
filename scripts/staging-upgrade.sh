#!/usr/bin/env bash
# Idempotent `helm upgrade` for opentourney-staging, reusing durable secrets
# straight from the live cluster instead of re-deriving/re-pasting them by
# hand on every deploy. Image tags default to whatever's currently deployed
# (a chart-only change -- like this one -- shouldn't accidentally roll an
# image back) unless overridden via a passthrough flag.
#
# Usage:
#   scripts/staging-upgrade.sh [extra helm upgrade args...]
#
# Extra args are passed to `helm upgrade` verbatim and win over this
# script's own flags (helm applies later --set/--set-string flags last), e.g.:
#   scripts/staging-upgrade.sh --set-string secrets.oidcAudience=<new-client-id>
#   scripts/staging-upgrade.sh --set backend.image.tag=<tag> --set frontend.image.tag=<tag>
#
# CONTEXT/NAMESPACE/RELEASE are overridable via env vars (e.g. when
# mcgee-local times out off-network, run `CONTEXT=mcgee-remote
# scripts/staging-upgrade.sh`) -- each defaults to the values this script has
# always used, so a bare invocation is unchanged.
set -euo pipefail

CONTEXT="${CONTEXT:-mcgee-local}"
NAMESPACE="${NAMESPACE:-opentourney-staging}"
RELEASE="${RELEASE:-opentourney-staging}"
CHART="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/charts/opentourney"

secret() {
  local value
  value=$(kubectl --context "$CONTEXT" -n "$NAMESPACE" get secret "$1" -o "jsonpath={.data.$2}" | base64 -d)
  # A missing Secret/key or a typo'd key name makes kubectl's jsonpath print
  # nothing (exit 0) -- without this check that silently resolves to an empty
  # string, which then blanks a live secret via --set-string on an otherwise
  # routine upgrade instead of failing loudly.
  if [[ -z "$value" ]]; then
    echo "ERROR: secret $1 key $2 is empty or missing -- refusing to proceed with a blank value" >&2
    exit 1
  fi
  echo "$value"
}

DATABASE_URL=$(secret opentourney-staging-opentourney-secrets DATABASE_URL)
OIDC_AUDIENCE=$(secret opentourney-staging-opentourney-secrets OIDC_AUDIENCE)
OIDC_ISSUER=$(secret opentourney-staging-opentourney-secrets OIDC_ISSUER)
OIDC_JWKS_URL=$(secret opentourney-staging-opentourney-secrets OIDC_JWKS_URL)
ZITADEL_MASTERKEY=$(secret opentourney-staging-opentourney-zitadel-secrets ZITADEL_MASTERKEY)
ZITADEL_ADMIN_PASSWORD=$(secret opentourney-staging-opentourney-zitadel-secrets ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD)

CURRENT_VALUES=$(helm --kube-context "$CONTEXT" -n "$NAMESPACE" get values "$RELEASE" -o json)
BACKEND_TAG=$(echo "$CURRENT_VALUES" | python3 -c "import sys,json; print(json.load(sys.stdin).get('backend',{}).get('image',{}).get('tag',''))")
FRONTEND_TAG=$(echo "$CURRENT_VALUES" | python3 -c "import sys,json; print(json.load(sys.stdin).get('frontend',{}).get('image',{}).get('tag',''))")
DOCS_TAG=$(echo "$CURRENT_VALUES" | python3 -c "import sys,json; print(json.load(sys.stdin).get('docs',{}).get('image',{}).get('tag',''))")

helm upgrade --install "$RELEASE" "$CHART" \
  --kube-context "$CONTEXT" \
  --namespace "$NAMESPACE" --create-namespace \
  -f "$CHART/values.staging.yaml" \
  --set-string backend.image.tag="$BACKEND_TAG" \
  --set-string frontend.image.tag="$FRONTEND_TAG" \
  --set-string docs.image.tag="$DOCS_TAG" \
  --set-string secrets.databaseUrl="$DATABASE_URL" \
  --set-string secrets.oidcAudience="$OIDC_AUDIENCE" \
  --set-string secrets.oidcIssuer="$OIDC_ISSUER" \
  --set-string secrets.oidcJwksUrl="$OIDC_JWKS_URL" \
  --set-string zitadel.masterkey="$ZITADEL_MASTERKEY" \
  --set-string zitadel.firstInstance.adminPassword="$ZITADEL_ADMIN_PASSWORD" \
  "$@"

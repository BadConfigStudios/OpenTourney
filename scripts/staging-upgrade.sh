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
set -euo pipefail

CONTEXT=mcgee-local
NAMESPACE=opentourney-staging
RELEASE=opentourney-staging
CHART="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/charts/opentourney"

secret() {
  kubectl --context "$CONTEXT" -n "$NAMESPACE" get secret "$1" -o "jsonpath={.data.$2}" | base64 -d
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

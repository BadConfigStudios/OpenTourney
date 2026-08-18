#!/bin/sh
# Runs automatically at container start -- nginx's official image executes
# every executable script under /docker-entrypoint.d/ before starting nginx.
set -eu
envsubst '${OIDC_AUTHORITY} ${OIDC_CLIENT_ID}' \
  < /usr/share/nginx/html/config.json.template \
  > /usr/share/nginx/html/config.json

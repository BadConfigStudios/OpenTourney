#!/bin/sh
set -eu

envsubst '${PERSONA_ORGANIZER_TOKEN} ${PERSONA_SCOREKEEPER_TOKEN} ${PERSONA_PLAYER_TOKEN}' \
  < /usr/share/nginx/html/config.json.template \
  > /usr/share/nginx/html/config.json

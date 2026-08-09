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

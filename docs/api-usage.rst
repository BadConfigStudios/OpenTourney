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

1. **Create an Organization** (Phase 11: Events belong to an
   Organization, and the creator becomes its ``OWNER``):

   .. code-block:: bash

      curl -X POST http://localhost:8000/organizations \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"name": "Friday Night League"}'

   Returns an ``OrganizationRead`` — note its ``id``.

2. **Create an Event** (caller must be ``OWNER`` or ``ORGANIZER`` on the
   organization):

   .. code-block:: bash

      curl -X POST http://localhost:8000/events \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"date": "2026-08-08", "name": "Friday Standard", "organization_id": "<organization-id>"}'

   Returns an ``EventRead`` — note its ``id``.

3. **Create a Pod** within that event (MVP1: one pod per event, Swiss
   format, generic game module):

   .. code-block:: bash

      curl -X POST http://localhost:8000/pods \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"event_id": "<event-id>", "format_slug": "swiss", "game_slug": "generic"}'

4. **Add Entries** (one per player):

   .. code-block:: bash

      curl -X POST http://localhost:8000/entries \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"pod_id": "<pod-id>", "player_uuid": "<uuid>", "source_system": "manual-verification"}'

5. **Generate Round 1** (organizer-only; pairs all current entries):

   .. code-block:: bash

      curl -X POST http://localhost:8000/pods/<pod-id>/rounds \
        -H "Authorization: Bearer $TOKEN"

   Returns a ``RoundRead`` with its ``matches`` — a bye match has
   ``entry2_id: null`` and needs no result.

6. **Report a match result** (Organizer or Scorekeeper):

   .. code-block:: bash

      curl -X POST http://localhost:8000/matches/<match-id>/result \
        -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"result": "entry1_win"}'

   ``result`` is one of ``entry1_win``, ``entry2_win``, ``tie``.

7. **Generate subsequent rounds** by repeating step 5 — pairings are
   computed from current standings, including OMW%/OOMW% tiebreakers
   (FR25).

8. **Pull the final report** once every match in the pod is resolved:

   .. code-block:: bash

      curl http://localhost:8000/pods/<pod-id>/report -H "Authorization: Bearer $TOKEN"

   Returns a ``PodReport``: ``is_complete``, ``rounds_played``, and ranked
   ``standings`` (points + tiebreaker values per entry).

See the `OpenAPI spec <openapi.json>`_ for the full schema of every
request/response body, and :doc:`data-model` for what each field means at
the database layer.

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

Organization
------------

.. autoclass:: app.models.organization.Organization
   :members:
   :undoc-members:

.. autoclass:: app.models.organization.OrganizationMember
   :members:
   :undoc-members:

.. autoclass:: app.models.organization.OrgRoleName
   :members:
   :undoc-members:

RBAC
----

.. autoclass:: app.models.rbac.PodRole
   :members:
   :undoc-members:

.. autoclass:: app.models.rbac.PodRoleName
   :members:
   :undoc-members:

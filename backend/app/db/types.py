from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# Portable JSON column: native JSONB on PostgreSQL, standard JSON on SQLite for unit tests.
JSONType = JSON().with_variant(JSONB(), "postgresql")

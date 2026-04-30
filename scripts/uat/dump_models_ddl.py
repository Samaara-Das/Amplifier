"""Dump the DDL implied by Base.metadata to stdout (for AC2 diff vs alembic upgrade head)."""
import sys
sys.path.insert(0, "server")
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from app.core.database import Base
import app.models  # noqa: registers all model classes

for table in Base.metadata.sorted_tables:
    print(str(CreateTable(table).compile(dialect=postgresql.dialect())) + ";")

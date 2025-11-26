"""
Member Payment Management System
FastAPI + HTMX + Jinja2 + PostgreSQL

Installation:
pip install fastapi uvicorn sqlalchemy psycopg2-binary jinja2 python-multipart

Run:
uvicorn main:app --reload
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    ForeignKey,
    UniqueConstraint,
    Boolean,
    MetaData,
    DateTime,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

# Use a naming convention for constraints so Alembic generates deterministic names
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=naming_convention)

Base = declarative_base(metadata=metadata)

# Name of the shared schema that stores authentication/credential data
SHARED_SCHEMA = "shared"


SHARED_SCHEMA = "shared"


# Shared Users Table (keeps passwords / auth information centralized)
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "tenant_schema", "username", name="uq_shared_users_tenant_username"
        ),
        UniqueConstraint("tenant_schema", "email", name="uq_shared_users_tenant_email"),
        {"schema": SHARED_SCHEMA},
    )

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True, index=True)
    password_hash = Column(String, nullable=False)
    tenant_schema = Column(String, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


# Other app custom models here:

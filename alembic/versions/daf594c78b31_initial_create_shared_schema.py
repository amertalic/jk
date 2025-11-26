"""Initial create shared schema

Revision ID: daf594c78b31
Revises:
Create Date: 2025-11-25 20:51:05.099104

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "daf594c78b31"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Ensure shared schema exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_namespace WHERE nspname = 'shared'
            ) THEN
                EXECUTE 'CREATE SCHEMA shared';
            END IF;
        END
        $$;
    """)

    # 2. Check if the table already exists
    table_exists = (
        op.get_bind()
        .execute(
            sa.text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'shared'
                  AND table_name = 'users'
            )
        """)
        )
        .scalar()
    )

    if table_exists:
        # Skip creation
        print("Table shared.users already exists — skipping creation.")
        return

    # 3. Create the users table inside shared schema
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("tenant_schema", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint(
            "tenant_schema", "email", name="uq_shared_users_tenant_email"
        ),
        sa.UniqueConstraint(
            "tenant_schema", "username", name="uq_shared_users_tenant_username"
        ),
        schema="shared",
    )

    op.create_index(
        op.f("ix_shared_users_email"), "users", ["email"], unique=False, schema="shared"
    )
    op.create_index(
        op.f("ix_shared_users_id"), "users", ["id"], unique=False, schema="shared"
    )
    op.create_index(
        op.f("ix_shared_users_tenant_schema"),
        "users",
        ["tenant_schema"],
        unique=False,
        schema="shared",
    )
    op.create_index(
        op.f("ix_shared_users_username"),
        "users",
        ["username"],
        unique=False,
        schema="shared",
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # If table doesn't exist, skip dropping
    table_exists = (
        op.get_bind()
        .execute(
            sa.text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'shared'
                  AND table_name = 'users'
            )
        """)
        )
        .scalar()
    )

    if not table_exists:
        print("Table shared.users does not exist — skipping drop.")
        return

    op.drop_index(op.f("ix_shared_users_username"), table_name="users", schema="shared")
    op.drop_index(
        op.f("ix_shared_users_tenant_schema"), table_name="users", schema="shared"
    )
    op.drop_index(op.f("ix_shared_users_id"), table_name="users", schema="shared")
    op.drop_index(op.f("ix_shared_users_email"), table_name="users", schema="shared")
    op.drop_table("users", schema="shared")

    # Optional: drop schema when empty
    # op.execute("DROP SCHEMA IF EXISTS shared CASCADE")

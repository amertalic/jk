#!/usr/bin/env python3
"""
Multi-tenant Alembic Migration CLI Tool

This CLI tool manages Alembic migrations across multiple PostgreSQL schemas (tenants).
Each schema maintains its own alembic_version table to track migration state independently.

Quick Reference:
    python cli_migrations.py list-schemas               # List all schemas and their versions
    python cli_migrations.py current --all              # Show current versions
    python cli_migrations.py upgrade --all              # Upgrade all tenant schemas
    python cli_migrations.py upgrade --schema qa        # Upgrade specific schema
    python cli_migrations.py stamp head --all           # Mark all schemas as current (no migration run)

Detailed Usage:
    python cli_migrations.py upgrade --all              # Upgrade all tenant schemas
    python cli_migrations.py upgrade --schema qa        # Upgrade specific schema
    python cli_migrations.py upgrade --schema qa 3de7e59774a2  # Upgrade to specific revision
    python cli_migrations.py current --all              # Show current versions
    python cli_migrations.py current --schema qa        # Show version for specific schema
    python cli_migrations.py history --all              # Show migration history
    python cli_migrations.py stamp head --schema qa     # Stamp schema without running migrations

For full documentation, see: CLI_MIGRATIONS_README.md
"""

import argparse
import sys
import os
from typing import List, Tuple, Optional
from sqlalchemy import text
from alembic.config import Config
from alembic import command
from settings import settings
from database import engine

# Configuration
ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "alembic.ini")
EXCLUDE_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "public"}


def get_all_tenant_schemas() -> List[str]:
    """Get all schemas from database excluding system schemas and public."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT schema_name 
            FROM information_schema.schemata
            WHERE schema_name NOT IN :excluded
            ORDER BY schema_name;
        """),
            {"excluded": tuple(EXCLUDE_SCHEMAS)},
        )
        return [row[0] for row in result]


def ensure_alembic_version_table(schema_name: str) -> None:
    """Ensure alembic_version table exists in the specified schema."""
    with engine.begin() as conn:
        # Check if table exists
        result = conn.execute(
            text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = :schema 
                AND table_name = 'alembic_version'
            );
        """),
            {"schema": schema_name},
        )

        exists = result.scalar()

        if not exists:
            print(f"  Creating alembic_version table in schema '{schema_name}'...")
            conn.execute(
                text(f"""
                CREATE TABLE "{schema_name}".alembic_version (
                    version_num VARCHAR(32) NOT NULL,
                    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                );
            """)
            )


def get_current_revision(schema_name: str) -> Optional[str]:
    """Get the current alembic revision for a schema."""
    try:
        # Use a fresh connection to ensure we see latest changes
        with engine.connect() as conn:
            result = conn.execute(
                text(f"""
                SELECT version_num 
                FROM "{schema_name}".alembic_version
                ORDER BY version_num DESC
                LIMIT 1;
            """)
            )
            row = result.fetchone()
            return row[0] if row else None
    except Exception as e:
        # Table might not exist yet
        return None


def upgrade_schema(
    schema_name: str, revision: str = "head"
) -> Tuple[bool, Optional[str]]:
    """
    Upgrade a specific schema to the given revision.

    Args:
        schema_name: Name of the schema to upgrade
        revision: Alembic revision to upgrade to (default: 'head')

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Ensure alembic_version table exists in this schema
        ensure_alembic_version_table(schema_name)

        # Create Alembic config
        cfg = Config(ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", settings.ALCHEMY_DB_URL)

        # Set the version_table_schema to the target schema
        cfg.set_main_option("version_table_schema", schema_name)
        cfg.set_main_option("search_path", schema_name)

        # Get current revision before upgrade
        current = get_current_revision(schema_name)
        print(f"  Current revision: {current or 'empty'}")

        # Run upgrade
        command.upgrade(cfg, revision)

        # Get new revision after upgrade
        new_revision = get_current_revision(schema_name)
        print(f"  New revision: {new_revision or 'empty'}")

        return True, None

    except Exception as e:
        return False, str(e)


def downgrade_schema(
    schema_name: str, revision: str = "-1"
) -> Tuple[bool, Optional[str]]:
    """
    Downgrade a specific schema to the given revision.

    Args:
        schema_name: Name of the schema to downgrade
        revision: Alembic revision to downgrade to (default: '-1')

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Ensure alembic_version table exists in this schema
        ensure_alembic_version_table(schema_name)

        # Create Alembic config
        cfg = Config(ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", settings.ALCHEMY_DB_URL)

        # Set the version_table_schema to the target schema
        cfg.set_main_option("version_table_schema", schema_name)
        cfg.set_main_option("search_path", schema_name)

        # Get current revision before downgrade
        current = get_current_revision(schema_name)
        print(f"  Current revision: {current or 'empty'}")

        # Run downgrade
        command.downgrade(cfg, revision)

        # Get new revision after downgrade
        new_revision = get_current_revision(schema_name)
        print(f"  New revision: {new_revision or 'empty'}")

        return True, None

    except Exception as e:
        return False, str(e)


def downgrade_all_schemas(revision: str = "-1") -> None:
    """Downgrade all schemas to the given revision."""
    schemas = get_all_tenant_schemas()
    print("Downgrading all schemas...")
    for schema in schemas:
        print(f"Running alembic downgrade for schema: {schema} ...")
        success, error = downgrade_schema(schema, revision)
        if success:
            print(f"  {schema}: Success")
        else:
            print(f"  {schema}: Failed - {error}")


def show_current(schema_name: str) -> None:
    """Show current migration version for a schema."""
    try:
        ensure_alembic_version_table(schema_name)
        current = get_current_revision(schema_name)

        if current:
            print(f"  {schema_name}: {current}")
        else:
            print(f"  {schema_name}: No migrations applied (empty)")

    except Exception as e:
        print(f"  {schema_name}: Error - {e}")


def show_history(schema_name: str) -> None:
    """Show migration history for a schema."""
    try:
        cfg = Config(ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", settings.ALCHEMY_DB_URL)
        cfg.set_main_option("version_table_schema", schema_name)

        print(f"\n{schema_name}:")
        command.history(cfg)

    except Exception as e:
        print(f"  {schema_name}: Error - {e}")


def stamp_schema(schema_name: str, revision: str) -> Tuple[bool, Optional[str]]:
    """
    Stamp a schema with a specific revision without running migrations.
    Useful when tables already exist and you want to mark the schema as being at a certain revision.

    Args:
        schema_name: Name of the schema to stamp
        revision: Alembic revision to stamp with

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Ensure alembic_version table exists in this schema
        ensure_alembic_version_table(schema_name)

        # Create Alembic config
        cfg = Config(ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", settings.ALCHEMY_DB_URL)
        cfg.set_main_option("version_table_schema", schema_name)
        cfg.set_main_option("search_path", schema_name)

        print(f"  Stamping schema with revision: {revision}")

        # Run stamp
        command.stamp(cfg, revision)

        # Get new revision after stamp
        new_revision = get_current_revision(schema_name)
        print(f"  Schema now at revision: {new_revision}")

        return True, None

    except Exception as e:
        return False, str(e)


def cmd_upgrade(args):
    """Handle upgrade command."""
    revision = args.revision if hasattr(args, "revision") else "head"

    if args.all:
        schemas = get_all_tenant_schemas()
        if not schemas:
            print("No tenant schemas found.")
            return

        print(f"Upgrading {len(schemas)} schema(s) to revision '{revision}'...\n")

        summary = {}
        for schema in schemas:
            print(f"Upgrading schema '{schema}'...")
            success, error = upgrade_schema(schema, revision)
            summary[schema] = "Success" if success else f"Failed: {error}"
            print()

        print("=" * 60)
        print("UPGRADE SUMMARY")
        print("=" * 60)
        for schema, result in summary.items():
            status = "✓" if result == "Success" else "✗"
            print(f"{status} {schema}: {result}")

        # Check if any failed
        failed = [s for s, r in summary.items() if r != "Success"]
        if failed:
            print(f"\n{len(failed)} schema(s) failed to upgrade.")
            sys.exit(1)
        else:
            print(f"\nAll {len(schemas)} schema(s) upgraded successfully!")

    elif args.schema:
        schema = args.schema
        print(f"Upgrading schema '{schema}' to revision '{revision}'...\n")
        success, error = upgrade_schema(schema, revision)

        if success:
            print(f"\n✓ Schema '{schema}' upgraded successfully!")
        else:
            print(f"\n✗ Schema '{schema}' failed to upgrade: {error}")
            sys.exit(1)
    else:
        print("Error: Specify --all or --schema <name>")
        sys.exit(1)


def cmd_downgrade(args):
    """Handle downgrade command."""
    revision = args.revision if hasattr(args, "revision") else "-1"

    if args.all:
        schemas = get_all_tenant_schemas()
        if not schemas:
            print("No tenant schemas found.")
            return

        print(f"Downgrading {len(schemas)} schema(s) to revision '{revision}'...\n")

        summary = {}
        for schema in schemas:
            print(f"Downgrading schema '{schema}'...")
            success, error = downgrade_schema(schema, revision)
            summary[schema] = "Success" if success else f"Failed: {error}"
            print()

        print("=" * 60)
        print("DOWNGRADE SUMMARY")
        print("=" * 60)
        for schema, result in summary.items():
            status = "✓" if result == "Success" else "✗"
            print(f"{status} {schema}: {result}")

        # Check if any failed
        failed = [s for s, r in summary.items() if r != "Success"]
        if failed:
            print(f"\n{len(failed)} schema(s) failed to downgrade.")
            sys.exit(1)
        else:
            print(f"\nAll {len(schemas)} schema(s) downgraded successfully!")

    elif args.schema:
        schema = args.schema
        print(f"Downgrading schema '{schema}' to revision '{revision}'...\n")
        success, error = downgrade_schema(schema, revision)

        if success:
            print(f"\n✓ Schema '{schema}' downgraded successfully!")
        else:
            print(f"\n✗ Schema '{schema}' failed to downgrade: {error}")
            sys.exit(1)
    else:
        print("Error: Specify --all or --schema <name>")
        sys.exit(1)


def cmd_current(args):
    """Handle current command."""
    if args.all:
        schemas = get_all_tenant_schemas()
        if not schemas:
            print("No tenant schemas found.")
            return

        print(f"Current revisions for {len(schemas)} schema(s):\n")
        for schema in schemas:
            show_current(schema)

    elif args.schema:
        print(f"Current revision for schema '{args.schema}':\n")
        show_current(args.schema)
    else:
        print("Error: Specify --all or --schema <name>")
        sys.exit(1)


def cmd_history(args):
    """Handle history command."""
    if args.all:
        schemas = get_all_tenant_schemas()
        if not schemas:
            print("No tenant schemas found.")
            return

        print(f"Migration history for {len(schemas)} schema(s):")
        for schema in schemas:
            show_history(schema)

    elif args.schema:
        print(f"Migration history for schema '{args.schema}':")
        show_history(args.schema)
    else:
        print("Error: Specify --all or --schema <name>")
        sys.exit(1)


def cmd_list_schemas(args):
    """List all tenant schemas."""
    schemas = get_all_tenant_schemas()
    if not schemas:
        print("No tenant schemas found.")
        return

    print(f"Found {len(schemas)} tenant schema(s):\n")
    for schema in schemas:
        current = get_current_revision(schema)
        version_info = f"(revision: {current})" if current else "(no migrations)"
        print(f"  • {schema} {version_info}")


def cmd_stamp(args):
    """Handle stamp command."""
    revision = args.revision

    if args.all:
        schemas = get_all_tenant_schemas()
        if not schemas:
            print("No tenant schemas found.")
            return

        print(f"Stamping {len(schemas)} schema(s) with revision '{revision}'...\n")

        summary = {}
        for schema in schemas:
            print(f"Stamping schema '{schema}'...")
            success, error = stamp_schema(schema, revision)
            summary[schema] = "Success" if success else f"Failed: {error}"
            print()

        print("=" * 60)
        print("STAMP SUMMARY")
        print("=" * 60)
        for schema, result in summary.items():
            status = "✓" if result == "Success" else "✗"
            print(f"{status} {schema}: {result}")

        # Check if any failed
        failed = [s for s, r in summary.items() if r != "Success"]
        if failed:
            print(f"\n{len(failed)} schema(s) failed to stamp.")
            sys.exit(1)
        else:
            print(f"\nAll {len(schemas)} schema(s) stamped successfully!")

    elif args.schema:
        schema = args.schema
        print(f"Stamping schema '{schema}' with revision '{revision}'...\n")
        success, error = stamp_schema(schema, revision)

        if success:
            print(f"\n✓ Schema '{schema}' stamped successfully!")
        else:
            print(f"\n✗ Schema '{schema}' failed to stamp: {error}")
            sys.exit(1)
    else:
        print("Error: Specify --all or --schema <name>")
        sys.exit(1)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Multi-tenant Alembic Migration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Upgrade command
    upgrade_parser = subparsers.add_parser(
        "upgrade", help="Upgrade schema(s) to a newer version"
    )
    upgrade_parser.add_argument(
        "revision", nargs="?", default="head", help="Target revision (default: head)"
    )
    upgrade_group = upgrade_parser.add_mutually_exclusive_group(required=True)
    upgrade_group.add_argument(
        "--all", action="store_true", help="Upgrade all tenant schemas"
    )
    upgrade_group.add_argument("--schema", type=str, help="Upgrade specific schema")

    # Downgrade command
    downgrade_parser = subparsers.add_parser("downgrade", help="Downgrade schemas")
    downgrade_parser.add_argument(
        "--all", action="store_true", help="Downgrade all schemas"
    )
    downgrade_parser.add_argument("--schema", help="Downgrade a specific schema")
    downgrade_parser.add_argument(
        "--revision", default="-1", help="Revision to downgrade to (default: -1)"
    )

    # Current command
    current_parser = subparsers.add_parser(
        "current", help="Show current revision for schema(s)"
    )
    current_group = current_parser.add_mutually_exclusive_group(required=True)
    current_group.add_argument(
        "--all", action="store_true", help="Show current revision for all schemas"
    )
    current_group.add_argument(
        "--schema", type=str, help="Show current revision for specific schema"
    )

    # History command
    history_parser = subparsers.add_parser(
        "history", help="Show migration history for schema(s)"
    )
    history_group = history_parser.add_mutually_exclusive_group(required=True)
    history_group.add_argument(
        "--all", action="store_true", help="Show history for all schemas"
    )
    history_group.add_argument(
        "--schema", type=str, help="Show history for specific schema"
    )

    # List schemas command
    list_parser = subparsers.add_parser("list-schemas", help="List all tenant schemas")

    # Stamp command
    stamp_parser = subparsers.add_parser(
        "stamp",
        help="Stamp schema(s) with a specific revision without running migrations",
    )
    stamp_parser.add_argument(
        "revision", help="Target revision to stamp with (e.g., head, 4f3b2a1c9d3e)"
    )
    stamp_group = stamp_parser.add_mutually_exclusive_group(required=True)
    stamp_group.add_argument(
        "--all", action="store_true", help="Stamp all tenant schemas"
    )
    stamp_group.add_argument("--schema", type=str, help="Stamp specific schema")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Route to appropriate command handler
    if args.command == "upgrade":
        cmd_upgrade(args)
    elif args.command == "downgrade":
        cmd_downgrade(args)
    elif args.command == "current":
        cmd_current(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "list-schemas":
        cmd_list_schemas(args)
    elif args.command == "stamp":
        cmd_stamp(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

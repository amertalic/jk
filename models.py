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
from sqlalchemy import Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column
from typing import List

from constants import MemberStatus, Sex

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


# Shared Users Table (keeps passwords / auth information centralized)
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "tenant_schema", "username", name="uq_shared_users_tenant_username"
        ),
        UniqueConstraint("tenant_schema", "email", name="uq_shared_users_tenant_email"),
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


class Location(Base):
    """
    Represents a physical location where judo training takes place.

    This could be different training halls, branches, or facilities.
    Each member is assigned to one location.

    Attributes:
        id: Primary key
        name: Unique name of the location (e.g., "Downtown Dojo", "North Branch")
        members: List of members training at this location

    Example:
        location = Location(name="Main Dojo")
        session.add(location)
        session.commit()
    """

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Relationships
    members: Mapped[List["Member"]] = relationship(back_populates="location")


class Level(Base):
    """
    Represents a judo skill level (belt color).

    Stores belt/rank information with a rank number for proper ordering.
    Lower rank numbers represent beginner levels.

    Attributes:
        id: Primary key
        name: Name of the belt (e.g., "White Belt", "Yellow Belt", "Black Belt")
        rank: Numeric rank for ordering (1=beginner, higher=advanced)
        members: List of members at this level

    Example:
        white_belt = Level(name="White Belt", rank=1)
        yellow_belt = Level(name="Yellow Belt", rank=2)
        session.add_all([white_belt, yellow_belt])
        session.commit()
    """

    __tablename__ = "levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )  # e.g., "White Belt", "Yellow Belt"
    rank: Mapped[int] = mapped_column(nullable=False)  # For ordering (1, 2, 3...)

    # Relationships
    members: Mapped[List["Member"]] = relationship(back_populates="level")


class PaymentPrice(Base):
    __tablename__ = "payment_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str] = mapped_column(
        String(100)
    )  # e.g., "Standard", "Student", "Family"

    # Relationships
    payments: Mapped[List["Payment"]] = relationship(back_populates="price")


class Member(Base):
    """
    Represents a judo club member with personal and membership information.

    Core model for managing club members. Includes personal details, membership status,
    assigned level (belt), and location. Optimized with indexes for fast searching.

    Attributes:
        id: Primary key
        name: First name
        surname: Last name
        date_of_birth: Birth date
        sex: Gender (using Sex enum)
        status: Membership status (using MemberStatus enum)
        date_of_enrolment: When the member joined the club
        level_id: Foreign key to Level (belt color)
        location_id: Foreign key to Location (training location)
        level: Relationship to Level object
        location: Relationship to Location object
        payments: List of all payments made by this member

    Indexes:
        - Status (for filtering active/inactive members)
        - Name + Surname (for search-as-you-type functionality)
        - Location (for location-based queries)

    Example:
        member = Member(
            name="John",
            surname="Doe",
            date_of_birth=date(1990, 5, 15),
            sex=Sex.MALE,
            status=MemberStatus.ACTIVE,
            level_id=1,  # White belt
            location_id=1  # Main dojo
        )
        session.add(member)
        session.commit()

        # Search members by name (fast due to index)
        results = session.query(Member).filter(
            Member.name.ilike(f"{search_term}%")
        ).limit(10).all()
    """

    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    surname: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[datetime] = mapped_column(Date, nullable=False)
    sex: Mapped[Sex] = mapped_column(nullable=False)
    status: Mapped[MemberStatus] = mapped_column(
        default=MemberStatus.ACTIVE, nullable=False
    )
    date_of_enrolment: Mapped[datetime] = mapped_column(
        Date, default=datetime.utcnow, nullable=False
    )

    # Foreign Keys
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    # Relationships
    level: Mapped["Level"] = relationship(back_populates="members")
    location: Mapped["Location"] = relationship(back_populates="members")
    payments: Mapped[List["Payment"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )

    # Indexes for fast querying
    __table_args__ = (
        Index("idx_member_status", "status"),
        Index("idx_member_name_surname", "name", "surname"),
        Index("idx_member_location", "location_id"),
    )

    @property
    def full_name(self):
        """Returns the member's full name (name + surname)."""
        return f"{self.name} {self.surname}"


class Payment(Base):
    """
    Represents a membership payment made by a member.

    Tracks monthly membership payments with period information and amount.
    Can be linked to a predefined price or have a custom amount.
    Optimized with indexes for fast payment history queries and period lookups.

    Attributes:
        id: Primary key
        member_id: Foreign key to Member who made the payment
        price_id: Foreign key to PaymentPrice (nullable for custom amounts)
        amount: Actual amount paid (allows flexibility for discounts/adjustments)
        payment_date: When the payment was recorded
        period_month: Month this payment covers (1-12)
        period_year: Year this payment covers
        notes: Optional notes (e.g., "gratis", "free", "double payment", "late fee")
        member: Relationship to Member object
        price: Relationship to PaymentPrice object

    Indexes:
        - member_id (for viewing a member's payment history)
        - period_year + period_month (for finding who paid in a specific month)
        - member_id + period (composite for checking if specific member paid for specific month)

    Example:
        # Standard payment using predefined price
        payment = Payment(
            member_id=5,
            price_id=1,  # Standard rate
            amount=30.00,
            period_month=11,
            period_year=2025
        )
        session.add(payment)

        # Free/gratis payment
        free_payment = Payment(
            member_id=5,
            price_id=None,
            amount=0.00,
            period_month=12,
            period_year=2025,
            notes="gratis - competition winner"
        )
        session.add(free_payment)

        # Query: Find all payments for November 2025
        november_payments = session.query(Payment).filter(
            Payment.period_month == 11,
            Payment.period_year == 2025
        ).all()

        # Query: Check if member paid for specific month (very fast due to composite index)
        has_paid = session.query(Payment).filter(
            Payment.member_id == 5,
            Payment.period_month == 11,
            Payment.period_year == 2025
        ).first() is not None
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)
    price_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_prices.id"), nullable=True
    )  # Null for custom amounts

    amount: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )  # Actual amount paid
    payment_date: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    period_month: Mapped[int] = mapped_column(nullable=False)  # 1-12
    period_year: Mapped[int] = mapped_column(nullable=False)
    notes: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # e.g., "gratis", "free", "double"

    # Relationships
    member: Mapped["Member"] = relationship(back_populates="payments")
    price: Mapped["PaymentPrice"] = relationship(back_populates="payments")

    # Indexes for fast payment queries
    __table_args__ = (
        Index("idx_payment_member", "member_id"),
        Index("idx_payment_period", "period_year", "period_month"),
        Index("idx_payment_member_period", "member_id", "period_year", "period_month"),
    )

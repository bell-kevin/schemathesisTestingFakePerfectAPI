"""Database utilities and seed data."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterator, Sequence
from uuid import UUID

from sqlmodel import Session, SQLModel, create_engine, select

from .models import AuditLog, Item, Order, OrderStatus, User

DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    """Create all database tables."""

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Yield a database session for request handling."""

    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""

    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def seed_data() -> None:
    """Seed the database with deterministic data."""

    with session_scope() as session:
        existing_users: Sequence[User] = session.exec(select(User)).all()
        if existing_users:
            return

        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

        users = [
            User(
                id=UUID("11111111-1111-1111-1111-111111111111"),
                email="ada.lovelace@example.com",
                full_name="Ada Lovelace",
                is_active=True,
                joined_at=base_time,
                updated_at=base_time,
            ),
            User(
                id=UUID("22222222-2222-2222-2222-222222222222"),
                email="grace.hopper@example.com",
                full_name="Grace Hopper",
                is_active=True,
                joined_at=base_time,
                updated_at=base_time,
            ),
            User(
                id=UUID("33333333-3333-3333-3333-333333333333"),
                email="george.boole@example.com",
                full_name="George Boole",
                is_active=False,
                joined_at=base_time,
                updated_at=base_time,
            ),
        ]

        orders = [
            Order(
                id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1"),
                user_id=users[0].id,
                status=OrderStatus.PROCESSING,
                total=Decimal("125.50"),
                placed_at=base_time,
                updated_at=base_time,
            ),
            Order(
                id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2"),
                user_id=users[1].id,
                status=OrderStatus.SHIPPED,
                total=Decimal("89.90"),
                placed_at=base_time,
                updated_at=base_time,
            ),
            Order(
                id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3"),
                user_id=users[0].id,
                status=OrderStatus.PENDING,
                total=Decimal("42.00"),
                placed_at=base_time,
                updated_at=base_time,
            ),
        ]

        items = [
            Item(
                id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1"),
                order_id=orders[0].id,
                sku="LPT-1000",
                name="Analytical Engine Manual",
                quantity=1,
                unit_price=Decimal("125.50"),
            ),
            Item(
                id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2"),
                order_id=orders[1].id,
                sku="COB-1959",
                name="COBOL Specification",
                quantity=1,
                unit_price=Decimal("89.90"),
            ),
            Item(
                id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3"),
                order_id=orders[2].id,
                sku="ALG-0001",
                name="Algorithm Notes",
                quantity=2,
                unit_price=Decimal("21.00"),
            ),
        ]

        audit_logs = [
            AuditLog(
                id=UUID("cccccccc-cccc-cccc-cccc-ccccccccccc1"),
                user_id=users[0].id,
                order_id=orders[0].id,
                action="order.created",
                summary="Order created via initial seed",
                performed_at=base_time,
            ),
            AuditLog(
                id=UUID("cccccccc-cccc-cccc-cccc-ccccccccccc2"),
                user_id=users[1].id,
                action="user.login",
                summary="Seed login event",
                performed_at=base_time,
            ),
        ]

        session.add_all(users)
        session.add_all(orders)
        session.add_all(items)
        session.add_all(audit_logs)


def init_db() -> None:
    """Initialize database tables and seed data."""

    create_db_and_tables()
    seed_data()

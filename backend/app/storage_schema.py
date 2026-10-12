"""Additional durable tables for the synthetic VitalGuard demo."""
from sqlalchemy import (
    Boolean, Column, DateTime, Index, Integer, MetaData, String, Table, Text, func,
)

metadata = MetaData()

patients = Table(
    "patients", metadata,
    Column("patient_id", String(64), primary_key=True),
    Column("display_name", String(120), nullable=False),
    Column("sex", String(1), nullable=False, server_default="U"),
    Column("date_of_birth", String(10), nullable=True),
    Column("ward", String(80), nullable=False, server_default="General Ward"),
    Column("bed", String(20), nullable=False, server_default=""),
    Column("active", Boolean, nullable=False, server_default="1"),
    Column("created_by", String(120), nullable=False, server_default="demo-system"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
)

alerts = Table(
    "alerts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("patient_id", String(64), nullable=False, index=True),
    Column("event_key", String(160), nullable=False, unique=True),
    Column("severity", String(16), nullable=False),
    Column("status", String(24), nullable=False, server_default="open"),
    Column("title", String(180), nullable=False),
    Column("details_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("acknowledged_by", String(120)),
    Column("acknowledged_at", DateTime(timezone=True)),
    Column("resolved_at", DateTime(timezone=True)),
    Column("assigned_to", String(120)),
    Column("assigned_at", DateTime(timezone=True)),
    Column("alert_type", String(32), nullable=False, server_default="clinical_rule"),
    Column("reopened_at", DateTime(timezone=True)),
    Column("reopened_by", String(120)),
    Column("notes_json", Text, nullable=False, server_default="[]"),
)
Index("idx_alerts_status_created", alerts.c.status, alerts.c.created_at.desc())
Index("idx_alerts_type_status", alerts.c.alert_type, alerts.c.status)

audit_events = Table(
    "audit_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entity_type", String(32), nullable=False),
    Column("entity_id", String(160), nullable=False),
    Column("action", String(80), nullable=False),
    Column("actor", String(120), nullable=False, server_default="demo-system"),
    Column("details_json", Text, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("idx_audit_entity_created", audit_events.c.entity_type, audit_events.c.entity_id, audit_events.c.created_at.desc())

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(128), unique=True, nullable=False, index=True),
    Column("password_hash", String(256), nullable=False),
    Column("role", String(32), nullable=False, server_default="nurse"),
    Column("full_name", String(120), nullable=False, server_default=""),
    Column("active", Boolean, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
)
Index("idx_users_username_active", users.c.username, users.c.active)


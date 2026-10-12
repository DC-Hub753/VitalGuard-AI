"""Small, ordered, idempotent schema migrations for the demo database.

The migration ledger is applied sequentially. Schema changes must be added as a
new version rather than editing a previously released migration. This remains
a lightweight SQLAlchemy migration runner; a managed PostgreSQL service and
backup/restore drill are separate release requirements.
"""

from sqlalchemy import Column, DateTime, Integer, MetaData, Table, func, insert, inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Engine

from .storage import _METADATA
from .storage_schema import metadata as _EXTENDED_METADATA
from .ingestion_schema import metadata as _INGESTION_METADATA

_MIGRATION_METADATA = MetaData()
MIGRATIONS = Table(
    "schema_migrations", _MIGRATION_METADATA,
    Column("version", Integer, primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# Keep migration definitions immutable after release. Each step should be
# safe to re-run after an interrupted startup.
LATEST_VERSION = 7



def _applied_versions(engine: Engine) -> set[int]:
    with engine.connect() as connection:
        return set(connection.execute(select(MIGRATIONS.c.version)).scalars())


def _record_version(engine: Engine, version: int) -> None:
    with engine.begin() as connection:
        connection.execute(insert(MIGRATIONS).values(version=version))


def migrate(engine: Engine) -> None:
    """Apply all known schema versions in order; safe to invoke repeatedly."""
    _MIGRATION_METADATA.create_all(engine)

    # Version 1: establish the original synthetic demo schema. Re-running
    # create_all is intentionally safe for a partially initialized database.
    applied = _applied_versions(engine)
    _METADATA.create_all(engine)
    _EXTENDED_METADATA.create_all(engine)
    if 1 not in applied:
        _record_version(engine, 1)

    # Version 2: index alert worklist queries by patient, status and creation.
    # checkfirst=True supports both fresh databases and interrupted upgrades.
    applied = _applied_versions(engine)
    if 2 not in applied:
        with engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alerts_patient_status_created ON alerts (patient_id, status, created_at DESC)"))
        _record_version(engine, 2)
    else:
        # Ensure a partially restored schema is repaired without rewriting the
        # migration ledger.
        with engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alerts_patient_status_created ON alerts (patient_id, status, created_at DESC)"))

    # Version 3: source provenance, observed timestamps, units and idempotency ledger.
    applied = _applied_versions(engine)
    if 3 not in applied:
        _INGESTION_METADATA.create_all(engine)
        _record_version(engine, 3)
    else:
        # Repair a missing table after an interrupted restore without rewriting the ledger.
        _INGESTION_METADATA.create_all(engine)

    # Version 4: extend patients with sex, date_of_birth, ward, bed, active, created_by.
    # Renamed the old 'unit' column to 'ward'. For existing databases that
    # already have the patients table from version 1, we add columns individually.
    applied = _applied_versions(engine)
    if 4 not in applied:
        _add_patients_columns(engine)
        _seed_demo_patients_if_empty(engine)
        _record_version(engine, 4)
    else:
        _add_patients_columns(engine)
        _seed_demo_patients_if_empty(engine)

    # Version 5: establish users table with PBKDF2 password hashes and RBAC roles (admin, clinician, nurse).
    applied = _applied_versions(engine)
    if 5 not in applied:
        _EXTENDED_METADATA.tables["users"].create(engine, checkfirst=True)
        _seed_demo_users_if_empty(engine)
        _record_version(engine, 5)
    else:
        _EXTENDED_METADATA.tables["users"].create(engine, checkfirst=True)
        _seed_demo_users_if_empty(engine)

    # Version 6: add source_mode and quality_json to ingestion_records.
    applied = _applied_versions(engine)
    if 6 not in applied:
        _add_ingestion_columns(engine)
        _record_version(engine, 6)
    else:
        _add_ingestion_columns(engine)

    # Version 7: add assigned_to, alert_type, reopened, and notes to alerts table.
    applied = _applied_versions(engine)
    if 7 not in applied:
        _add_alerts_columns(engine)
        _record_version(engine, 7)
    else:
        _add_alerts_columns(engine)

    applied = _applied_versions(engine)
    expected = set(range(1, LATEST_VERSION + 1))
    if not expected.issubset(applied):
        raise RuntimeError(f"Database migrations incomplete: expected {sorted(expected)}, found {sorted(applied)}")


def _add_patients_columns(engine: Engine) -> None:
    """Idempotently add Phase-1 columns to the patients table.

    PostgreSQL supports ADD COLUMN IF NOT EXISTS natively.
    SQLite does not, so we catch the duplicate-column OperationalError.
    """
    columns = [
        "ALTER TABLE patients ADD COLUMN sex VARCHAR(1) NOT NULL DEFAULT 'U'",
        "ALTER TABLE patients ADD COLUMN date_of_birth VARCHAR(10)",
        "ALTER TABLE patients ADD COLUMN ward VARCHAR(80) NOT NULL DEFAULT 'General Ward'",
        "ALTER TABLE patients ADD COLUMN bed VARCHAR(20) NOT NULL DEFAULT ''",
        "ALTER TABLE patients ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE patients ADD COLUMN created_by VARCHAR(120) NOT NULL DEFAULT 'demo-system'",
    ]
    is_postgresql = engine.dialect.name == "postgresql"
    with engine.begin() as connection:
        for ddl in columns:
            if is_postgresql:
                # Use IF NOT EXISTS for PostgreSQL.
                ddl = ddl.replace("ADD COLUMN ", "ADD COLUMN IF NOT EXISTS ", 1)
            try:
                connection.execute(text(ddl))
            except OperationalError:
                # SQLite: column already exists from a previous run or create_all.
                pass
    # Migrate data from the legacy 'unit' column only when it exists.
    # Fresh/current schemas have 'ward' but no 'unit'; attempting the UPDATE
    # unconditionally raises ProgrammingError on PostgreSQL and aborts startup.
    patient_columns = {column["name"] for column in inspect(engine).get_columns("patients")}
    if "unit" in patient_columns:
        with engine.begin() as connection:
            connection.execute(text(
                "UPDATE patients SET ward = unit WHERE ward = 'General Ward' AND unit IS NOT NULL AND unit != 'Demo Ward'"
            ))


def _seed_demo_users_if_empty(engine: Engine) -> None:
    """Seed initial role accounts if the users table is completely empty."""
    from .user_service import seed_initial_users
    seed_initial_users(engine)


def _seed_demo_patients_if_empty(engine: Engine) -> None:
    """Seed initial patient cohort if the patients table is completely empty."""
    from .patient_service import seed_initial_patients
    seed_initial_patients(engine)



def _add_ingestion_columns(engine: Engine) -> None:
    """Idempotently add Phase-3 columns to ingestion_records table."""
    columns = [
        "ALTER TABLE ingestion_records ADD COLUMN source_mode VARCHAR(32) NOT NULL DEFAULT 'synthetic_demo'",
        "ALTER TABLE ingestion_records ADD COLUMN quality_json TEXT NOT NULL DEFAULT '{}'",
    ]
    is_postgresql = engine.dialect.name == "postgresql"
    with engine.begin() as connection:
        for ddl in columns:
            if is_postgresql:
                ddl = ddl.replace("ADD COLUMN ", "ADD COLUMN IF NOT EXISTS ", 1)
            try:
                connection.execute(text(ddl))
            except OperationalError:
                pass
        try:
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_ingestion_source_mode ON ingestion_records (source_mode)"))
        except OperationalError:
            pass


def _add_alerts_columns(engine: Engine) -> None:
    """Idempotently add Phase-5 columns to alerts table."""
    is_postgresql = engine.dialect.name == "postgresql"
    tz_type = "TIMESTAMP WITH TIME ZONE" if is_postgresql else "DATETIME"
    columns = [
        "ALTER TABLE alerts ADD COLUMN assigned_to VARCHAR(120)",
        f"ALTER TABLE alerts ADD COLUMN assigned_at {tz_type}",
        "ALTER TABLE alerts ADD COLUMN alert_type VARCHAR(32) NOT NULL DEFAULT 'clinical_rule'",
        f"ALTER TABLE alerts ADD COLUMN reopened_at {tz_type}",
        "ALTER TABLE alerts ADD COLUMN reopened_by VARCHAR(120)",
        "ALTER TABLE alerts ADD COLUMN notes_json TEXT NOT NULL DEFAULT '[]'",
    ]
    with engine.begin() as connection:
        for ddl in columns:
            if is_postgresql:
                ddl = ddl.replace("ADD COLUMN ", "ADD COLUMN IF NOT EXISTS ", 1)
            try:
                connection.execute(text(ddl))
            except OperationalError:
                pass
        try:
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alerts_type_status ON alerts (alert_type, status)"))
        except OperationalError:
            pass



import importlib.util
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from procurawise.shared.config import Settings, get_settings
from procurawise.shared.logging import configure_logging
from procurawise.shared.mongo import get_mongo_client

logger = logging.getLogger("procurawise.migrations")

# service/procurawise/shared/migrations.py -> service/migrations
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _load_migration_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load migration module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migrations(settings: Settings | None = None) -> int:
    """Applies pending numbered migrations from `migrations/` idempotently,
    tracked via the `_migrations` control collection. Returns the count applied.
    A no-op (returns 0) until the first real migration file exists."""
    settings = settings or get_settings()
    client = get_mongo_client(settings)
    db = client[settings.mongodb_db_name]
    control = db["_migrations"]

    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.py"))
    applied_ids = {doc["_id"] for doc in control.find({}, {"_id": 1})}
    pending = [path for path in migration_files if path.stem not in applied_ids]

    if not pending:
        logger.info("no pending migrations")
        return 0

    for path in pending:
        logger.info("applying migration %s", path.stem)
        module = _load_migration_module(path)
        module.apply(db)
        control.insert_one({"_id": path.stem, "applied_at": datetime.now(UTC)})

    logger.info("applied %d migration(s)", len(pending))
    return len(pending)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    run_migrations(settings)


if __name__ == "__main__":
    main()

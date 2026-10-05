"""Create an isolated SQLite snapshot for Compose; never overwrite either DB."""
from pathlib import Path
import sqlite3


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "data" / "maintenance.db"
    target_dir = root / "data" / "local" / "compose"
    target = target_dir / "maintenance.db"
    target_dir.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print(f"Keeping existing container database: {target}")
        return
    if not source.is_file():
        print(f"No local database to copy; maintenance will initialize {target}")
        return
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(target) as snapshot:
            original.backup(snapshot)
    print(f"SQLite snapshot created: {target}")
    print(f"Original database unchanged: {source}")


if __name__ == "__main__":
    main()

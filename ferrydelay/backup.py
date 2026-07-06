"""WAL-safe snapshot of the database.

Uses SQLite's online backup API (not a raw file copy) so it's consistent even
while the collector is mid-write. Snapshots land in ``backups/`` with a
timestamp; the newest ``KEEP`` are retained.

    python -m ferrydelay.backup
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .config import Config

KEEP = 8  # ~2 months of weekly snapshots


def main() -> int:
    cfg = Config.load()
    if not cfg.db_path.exists():
        print(f"No database at {cfg.db_path} — nothing to back up.")
        return 1

    backup_dir = cfg.db_path.parent.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    dest = backup_dir / f"ferry-{stamp}.db"

    src = sqlite3.connect(cfg.db_path)
    dst = sqlite3.connect(dest)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()

    snapshots = sorted(backup_dir.glob("ferry-*.db"))
    for old in snapshots[:-KEEP]:
        old.unlink()

    print(f"Backed up -> {dest}  ({dest.stat().st_size // 1024} KB, "
          f"keeping newest {KEEP})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

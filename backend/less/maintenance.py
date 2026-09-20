"""Backup/restore for the default local Compose deployment."""

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from less.config import ROOT, settings

DEFAULT_URL = "postgresql+psycopg://less:less_local@127.0.0.1:55432/less"
ADMIN_URL = "postgresql://less:less_local@127.0.0.1:55432/postgres"


def require_default():
    if settings().database_url != DEFAULT_URL:
        raise ValueError("Backup/restore supports the default local Compose deployment only")


def digest(path: Path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def backup() -> Path:
    require_default()
    folder = (
        settings().data_dir / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    folder.mkdir(parents=True)
    # Snapshots are immutable and are committed to disk before any DB reference.
    # Dump first, then copy snapshots; extra snapshots are harmless.
    with (folder / "database.dump").open("wb") as out:
        subprocess.run(
            ["docker", "compose", "exec", "-T", "postgres", "pg_dump", "-U", "less", "-Fc", "less"],
            cwd=ROOT,
            stdout=out,
            check=True,
        )
    source = settings().data_dir / "snapshots"
    if source.exists():
        shutil.copytree(source, folder / "snapshots")
    checksums = {"database.dump": digest(folder / "database.dump")}
    for path in (folder / "snapshots").rglob("*"):
        if path.is_file():
            checksum = digest(path)
            if checksum != path.name:
                raise ValueError("Snapshot checksum mismatch; backup not marked complete")
            checksums[str(path.relative_to(folder))] = checksum
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "database": "less",
                "status": "complete",
                "checksums": checksums,
            },
            indent=2,
        )
    )
    return folder.resolve()


def restore(folder: Path, database_name: str) -> dict:
    require_default()
    if not re.fullmatch(r"less_restore_[a-z0-9_]{1,40}", database_name):
        raise ValueError("Restore requires a NEW database named less_restore_<name>")
    folder = folder.resolve()
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest.get("status") != "complete":
        raise ValueError("Backup is incomplete")
    for relative, checksum in manifest["checksums"].items():
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or digest(path) != checksum:
            raise ValueError(f"Backup checksum failed: {relative}")
    destination = settings().data_dir / "restores" / database_name
    if destination.exists():
        raise ValueError("Restore directory already exists; choose a fresh name")
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        # CREATE fails if the DB exists. Never drop, truncate or overwrite a user database.
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    with (folder / "database.dump").open("rb") as source:
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "-U",
                "less",
                "--exit-on-error",
                "-d",
                database_name,
            ],
            cwd=ROOT,
            stdin=source,
            check=True,
        )
    destination.mkdir(parents=True)
    if (folder / "snapshots").exists():
        shutil.copytree(folder / "snapshots", destination / "snapshots")
    restored_url = f"postgresql://less:less_local@127.0.0.1:55432/{database_name}"
    with psycopg.connect(restored_url) as conn:
        paths = conn.execute(
            "SELECT snapshot_path FROM item_versions UNION SELECT snapshot_path FROM source_checks WHERE snapshot_path IS NOT NULL"
        ).fetchall()
        for (relative,) in paths:
            path = destination / relative
            if not path.is_file() or digest(path) != path.name:
                raise ValueError("Restored snapshot does not match its database reference")
        count = conn.execute("SELECT count(*) FROM items").fetchone()[0]
    return {
        "database_url": restored_url.replace("postgresql://", "postgresql+psycopg://"),
        "data_dir": str(destination.resolve()),
        "items": count,
        "snapshots_checked": len(paths),
    }

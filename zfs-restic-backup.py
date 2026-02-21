#!/usr/bin/env python3
"""
ZFS lock check + snapshot + restic backup for TrueNAS cron.

Checks encrypted dataset is unlocked, creates ZFS snapshot, runs restic backup
from the snapshot dir (.zfs/snapshot/<name>) with --time from the ZFS snapshot
creation time, then destroys the snapshot on success.

Usage:
  zfs-restic-backup.py [--restic-bin <path>] <mount_point> [-- <restic_args>...]

  --restic-bin   Optional. Path to restic binary (if not using the one in PATH).
  mount_point    ZFS dataset mount point to back up.
  After "--", arguments are passed through to restic backup.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import cast


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat()}] {msg}", flush=True)


def script_sha256() -> str | None:
    """Return SHA-256 hex digest of this script file, or None if unreadable."""
    try:
        path = Path(__file__).resolve()
        if not path.is_file():
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def run_cmd(
    cmd: list[str],
    check: bool = True,
    capture: bool = False,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a command; if check=True and non-zero exit, raise CalledProcessError."""
    kw: dict = {"check": check}
    if capture:
        kw["capture_output"] = True
        kw["text"] = True
    if cwd is not None:
        kw["cwd"] = str(cwd)
    return subprocess.run(cmd, **kw)


def get_dataset_for_path(path: str) -> str | None:
    """Resolve mountpoint path to ZFS dataset name, or None if not found."""
    result = run_cmd(
        ["zfs", "list", "-H", "-o", "name,mountpoint"],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.strip().splitlines():
        if "\t" in line:
            name, mnt = line.split("\t", 1)
            if mnt == path:
                return cast(str, name)
    return None


def get_encryption_root(dataset: str) -> str | None:
    """Return encryption root dataset name, or None if not encrypted."""
    result = run_cmd(
        ["zfs", "get", "-H", "-o", "value", "encryptionroot", dataset],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value or value == "-":
        return None
    return cast(str, value)


def get_keystatus(dataset: str) -> str | None:
    """Return keystatus value (e.g. available, unavailable, locked) or None."""
    result = run_cmd(
        ["zfs", "get", "-H", "-o", "value", "keystatus", dataset],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        return None
    return cast(str | None, result.stdout.strip() or None)


def get_snapshot_creation_time(snapshot_spec: str) -> str | None:
    """Return restic --time format (YYYY-MM-DD HH:MM:SS) from ZFS snapshot creation, or None."""
    result = run_cmd(
        ["zfs", "get", "-H", "-p", "-o", "value", "creation", snapshot_spec],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        epoch = int(raw)
        if epoch > 1e12:
            epoch = epoch // 1_000_000_000
        dt = datetime.fromtimestamp(epoch)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return None


def parse_args(argv: list[str]) -> tuple[str | None, str, list[str]]:
    """Parse argv: optional --restic-bin <path>, then mount point, then args after '--'."""
    restic_bin: str | None = None
    args = list(argv)
    while args and args[0] == "--restic-bin":
        args.pop(0)  # drop --restic-bin
        if not args:
            return ("", "", [])  # invalid: --restic-bin with no value
        restic_bin = args.pop(0).strip()
    if not args:
        return (restic_bin, "", [])
    if "--" in args:
        idx = args.index("--")
        mount_point = args[0]
        restic_args = args[idx + 1 :]
        return restic_bin, mount_point.strip(), restic_args
    return restic_bin, args[0].strip(), []


def main() -> int:
    # ---------- Parse CLI ----------
    restic_bin, mount_point, restic_cli_args = parse_args(sys.argv[1:])
    if not mount_point:
        if restic_bin == "":
            log("ERROR: --restic-bin requires a path argument")
        else:
            log("ERROR: Missing required argument: mount point")
        log("Usage: zfs-restic-backup.py [--restic-bin <path>] <mount_point> [-- <restic_args>...]")
        return 1

    # ---------- Validate optional restic binary ----------
    restic_cmd: str = "restic"
    if restic_bin:
        restic_bin_path = Path(restic_bin).resolve()
        if not restic_bin_path.is_file():
            log(f"ERROR: --restic-bin path is not a file: {restic_bin_path}")
            return 1
        if not os.access(restic_bin_path, os.X_OK):
            log(f"ERROR: --restic-bin path is not executable: {restic_bin_path}")
            return 1
        restic_cmd = str(restic_bin_path)

    source_path = os.path.abspath(mount_point)

    # ---------- Requirements (script sha, then zfs & restic version) ----------
    script_name = Path(sys.argv[0]).name
    digest = script_sha256()
    log(f"  {script_name}: sha256:{digest}" if digest else f"  {script_name}: (unable to read)")

    version_cmds = [
        ("zfs", ["zfs", "version"]),
        ("restic", [restic_cmd, "version"]),
    ]
    for name, cmd in version_cmds:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            out = (result.stdout or "").strip() or (result.stderr or "").strip()
            if result.returncode != 0:
                log(f"ERROR: {name} failed (exit {result.returncode})")
                if out:
                    log(out)
                return 1
            for line in (out.splitlines() or ["ok"]):
                log(f"  {name}: {line}")
        except FileNotFoundError:
            log(f"ERROR: {name} not found")
            return 1

    if not Path(source_path).is_dir():
        log(f"ERROR: Path {source_path} not found")
        return 1

    pid = os.getpid()
    hostname = re.sub(r"[^a-zA-Z0-9-]", "-", os.uname().nodename).strip("-") or "host"
    snap_ts = datetime.now()
    snap_name = f"zfs-restic-{pid}-{hostname}-{snap_ts.strftime('%Y%m%d-%H%M%S')}"

    # ---------- 1) ZFS lock check ----------
    log("Checking ZFS dataset is unlocked...")
    ds = get_dataset_for_path(source_path)
    if not ds:
        log(f"ERROR: No ZFS dataset with mountpoint {source_path}")
        return 1
    enc_root = get_encryption_root(ds)
    if enc_root:
        status = get_keystatus(enc_root)
        if status in ("unavailable", "locked"):
            log(f"ERROR: {source_path} (encryption root {enc_root}) is LOCKED - unlock on TrueNAS first")
            return 1
        if status != "available":
            log(f"ERROR: keystatus '{status}' for {enc_root}")
            return 1
        log(f"  OK: {source_path} unlocked")
    else:
        log(f"  OK: {source_path} ({ds}) not encrypted")

    # ---------- 2) Create ZFS snapshot ----------
    log("Creating ZFS snapshot...")
    run_cmd(["zfs", "snapshot", f"{ds}@{snap_name}"])
    log(f"  Created {ds}@{snap_name}")

    snapshot_spec = f"{ds}@{snap_name}"
    restic_time = get_snapshot_creation_time(snapshot_spec)
    if not restic_time:
        log("ERROR: could not read ZFS snapshot creation time")
        run_cmd(["zfs", "destroy", snapshot_spec], check=False)
        return 1

    snapshot_dir = Path(source_path) / ".zfs" / "snapshot" / snap_name
    if not snapshot_dir.is_dir():
        log(f"ERROR: Snapshot dir not found: {snapshot_dir}")
        run_cmd(["zfs", "destroy", snapshot_spec], check=False)
        return 1

    # ---------- 3) Restic backup ----------
    log("Running restic backup...")
    cmd = [
        restic_cmd, "backup",
        "--time", restic_time,
        ".",
    ] + restic_cli_args
    log(f"  {' '.join(cmd)}")
    result = run_cmd(cmd, check=False, cwd=snapshot_dir)
    if result.returncode != 0:
        log(f"ERROR: restic backup failed ({result.returncode}) - snapshot left in place: {snap_name}")
        return result.returncode

    log("Destroying ZFS snapshot...")
    run_cmd(["zfs", "destroy", snapshot_spec], check=False)

    log("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

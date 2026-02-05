#!/usr/bin/env python3
"""
Check that ZFS dataset(s) for the given path(s) are unlocked.

For each path (mount point), resolves to a ZFS dataset and, if the dataset
is encrypted, checks that the encryption root is unlocked. Exits 0 if all
are unlocked (or not encrypted), 1 with a clear message if any are locked.

Use before loading secrets from an encrypted dataset in cron, e.g.:
  zfs-check-unlocked.py /mnt/secrets && . /mnt/secrets/restic.env && ...

Usage:
  zfs-check-unlocked.py <path> [<path> ...]
"""

from __future__ import annotations

import os
import subprocess
import sys


def run_cmd(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=capture,
        check=False,
    )


def get_dataset_for_path(path: str) -> str | None:
    """Resolve mountpoint path to ZFS dataset name, or None if not found."""
    result = run_cmd(["zfs", "list", "-H", "-o", "name,mountpoint"])
    if result.returncode != 0:
        return None
    for line in result.stdout.strip().splitlines():
        if "\t" in line:
            name, mnt = line.split("\t", 1)
            if mnt == path:
                return name
    return None


def get_encryption_root(dataset: str) -> str | None:
    """Return encryption root dataset name, or None if not encrypted."""
    result = run_cmd(["zfs", "get", "-H", "-o", "value", "encryptionroot", dataset])
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value or value == "-":
        return None
    return value


def get_keystatus(dataset: str) -> str | None:
    """Return keystatus value (e.g. available, unavailable, locked) or None."""
    result = run_cmd(["zfs", "get", "-H", "-o", "value", "keystatus", dataset])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def check_path(path: str) -> str | None:
    """
    Check that the dataset for path is unlocked. Return None if OK, else error message.
    Uses ZFS mountpoint property (path need not exist yet, e.g. when dataset is locked).
    """
    resolved = os.path.abspath(path)
    ds = get_dataset_for_path(resolved)
    if not ds:
        return f"No ZFS dataset with mountpoint: {resolved}"

    enc_root = get_encryption_root(ds)
    if not enc_root:
        return None  # not encrypted, OK

    status = get_keystatus(enc_root)
    if status in ("unavailable", "locked"):
        return f"Dataset is LOCKED: {resolved} (encryption root {enc_root}) — unlock the dataset first"
    if status != "available":
        return f"Unexpected keystatus '{status}' for {enc_root} ({resolved})"
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: zfs-check-unlocked.py <path> [<path> ...]", file=sys.stderr)
        return 1

    failed = False
    for path in sys.argv[1:]:
        path = path.strip()
        if not path:
            continue
        err = check_path(path)
        if err:
            print(err, file=sys.stderr)
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

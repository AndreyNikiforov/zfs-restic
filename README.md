# zfs-restic

ZFS-aware [restic](https://restic.net/) backup for a single dataset. Intended for any ZFS host.

## What it does

1. **Validates** that `zfs` and `restic` are on PATH.
2. **ZFS lock check** — Resolves the given mount point to a ZFS dataset. If the dataset has an encryption root, checks that it is unlocked; exits with an error if locked.
3. **Snapshot** — Creates a ZFS snapshot `dataset@zfs-restic-<pid>-<hostname>-YYYYMMDD-HHMMSS`.
4. **Backup** — Runs `restic backup` with cwd set to the snapshot dir (`.zfs/snapshot/<name>`), with `--time` from the ZFS snapshot creation time.
5. **Cleanup** — On success, destroys the ZFS snapshot; on restic failure, the snapshot is left in place for inspection or retry.

## Usage

```text
zfs-restic-backup.py <mount_point> [-- <restic_args>...]
```

- **`mount_point`** (required) — Mount point of the ZFS dataset to back up (e.g. `/mnt/tank/family`). Must be the exact mountpoint as shown by `zfs list -o name,mountpoint`.
- **`-- <restic_args>...`** (optional) — Passed through to `restic backup`; see restic documentation.

### Examples

```bash
python3 zfs-restic-backup.py /mnt/tank/family

python3 zfs-restic-backup.py /mnt/tank/family -- --dry-run
```

### Cron (e.g. daily at 2am)

Source your restic environment and run the script with the mount point:

```cron
0 2 * * * . /root/restic-backup.env && python3 /path/to/zfs-restic-backup.py /mnt/tank/family >> /var/log/zfs-restic.log 2>&1
```

If restic env or secrets live on an encrypted dataset, check that it is unlocked first so cron fails with a clear message instead of obscure errors:

```bash
zfs-check-unlocked.py /mnt/secrets && . /mnt/secrets/restic.env && python3 /path/to/zfs-restic-backup.py /mnt/tank/family
```

## zfs-check-unlocked.py

Standalone utility to check that ZFS dataset(s) are unlocked (for use before loading secrets from encrypted volumes). Takes one or more mount paths; exits 0 if all are unlocked (or not encrypted), 1 with a clear “Dataset is LOCKED” message otherwise. Stdlib only, no restic dependency.

```text
zfs-check-unlocked.py <path> [<path> ...]
```

## Requirements

- Python 3 (stdlib only; no pip dependencies).
- `zfs` and `restic` on PATH.
- Run as root (or with permission to create/destroy ZFS snapshots and read the dataset).
- For encrypted datasets: unlock the encryption root before the backup runs (e.g. before cron); the script exits with an error if the dataset is locked.

## License

See [LICENSE](LICENSE).

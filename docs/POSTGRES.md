# PostgreSQL for HOLO-RTLS (production)

SQLite is the default for local/dev. For production, use Postgres.

## Setup

```bash
# Create DB + user (example)
createdb holo_rtls
# Or via URL:
export DATABASE_URL=postgresql://holo:CHANGE_ME@127.0.0.1:5432/holo_rtls
```

Install driver (already listed in `requirements.txt`):

```bash
pip install psycopg2-binary
```

## Migrations / schema

On first boot the app runs `db.create_all()` plus light SQLite-only column patches (`_ensure_schema_columns`). For Postgres:

1. Point `DATABASE_URL` at Postgres before first start.
2. Prefer Flask-Migrate for schema evolution:

```bash
export FLASK_APP=run.py
flask db upgrade   # when migration revisions exist
```

If starting fresh on Postgres, `create_all` is enough for a greenfield deploy; add Alembic revisions before changing production schema.

## Backups

- **SQLite:** `POST /api/backup/trigger` copies the DB file; optional Fernet encryption via `BACKUP_ENCRYPT_KEY`. Restore is file-copy + restart.
- **Postgres:** use `pg_dump` / `pg_restore` (or your cloud snapshot). The in-app file restore endpoint returns `400` for non-SQLite URIs.

Example:

```bash
pg_dump "$DATABASE_URL" -Fc -f holo_rtls_$(date +%Y%m%d).dump
pg_restore -d "$DATABASE_URL" --clean --if-exists holo_rtls_YYYYMMDD.dump
```

## Encryption (optional, SQLite backups)

```bash
export BACKUP_ENCRYPT_KEY='long-random-passphrase'
```

Backups are written as `*.db.enc` (Fernet). Restore requires the same key and the `cryptography` package.

## Legacy UWB demo

```bash
# Hard-disable deprecated /api/uwb (returns 410)
export HOLO_ENABLE_UWB_DEMO=0
```

Default is enabled for lab compatibility. Prefer `/api/positioning/*`.

## Web Push (VAPID)

Optional browser push for critical alerts (works with the service worker):

```bash
# Generate keys: python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v.public_key); print(v.private_key)"
export VAPID_PUBLIC_KEY='...'
export VAPID_PRIVATE_KEY='...'
export VAPID_CLAIMS_EMAIL='mailto:ops@example.com'
```

Users enable subscriptions in **Settings → Location Core → Enable Web Push**.

## Checklist

| Item | Dev (SQLite) | Prod (Postgres) |
|------|--------------|-----------------|
| `DATABASE_URL` | `sqlite:////…/holo_rtls.db` | `postgresql://…` |
| App file backup/restore | Yes | No — use `pg_dump` |
| Connection pooling | N/A | Prefer PgBouncer / pool_size tuning |
| Secrets | `.env` | Secret manager / env |

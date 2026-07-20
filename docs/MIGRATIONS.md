# Database schema & migrations

HOLO-RTLS supports **two ways** to keep the database schema in sync with the models.
By default you don't have to do anything — the app auto-reconciles additive changes.
For production / Postgres / strict control, use the bundled Alembic migrations.

---

## 1. Default: automatic additive reconcile (zero-config)

On startup the app runs `create_all()` (creates any missing **tables**) and then a
generic reconcile pass that **adds any model columns missing from existing tables**
(`backend/app.py :: _ensure_schema_columns`).

This means: **adding a nullable column to a model never breaks an existing SQLite DB.**
Previously, adding e.g. `User.phone` without a migration caused
`sqlite3.OperationalError: no such column: users.phone` on boot — that class of failure
is now handled automatically.

**Limitations** — the auto-reconcile only *adds* columns. It does **not** handle:
- dropping or renaming columns/tables
- changing a column's type or constraints
- data backfills

For those, use a real migration (section 2).

Disable auto-reconcile with `AUTO_SCHEMA_RECONCILE=0` (recommended when you manage the
schema with Alembic, so the two mechanisms don't both try to apply a change).

---

## 2. Managed migrations (Alembic / Flask-Migrate)

A migration history lives in `migrations/`. The baseline (`fe75fca48d38_baseline_schema`)
captures the full current schema (24 tables).

> All `flask db` commands need the app importable and the secrets set. On this repo:
> ```
> set FLASK_APP=run            # or pass --app run
> set HOLO_SKIP_INIT=1         # don't start the positioning bootstrap for CLI
> set SECRET_KEY=...           # required
> set JWT_SECRET_KEY=...       # required
> ```
> (`HOLO_SKIP_INIT=1` keeps `flask db` from running `create_all()`/background threads,
> which would otherwise interfere with autogenerate.)

### Fresh install (managed)
```bash
AUTO_SCHEMA_RECONCILE=0 flask --app run db upgrade
```
Builds the whole schema from the baseline and stamps `alembic_version`.

### After you change a model
```bash
HOLO_SKIP_INIT=1 flask --app run db migrate -m "add X to Y"   # autogenerate
# review the generated file in migrations/versions/ , then:
flask --app run db upgrade                                    # apply
```
Commit the generated version script — `migrations/versions/*.py` is tracked in git.

### Upgrading an existing deployment
```bash
flask --app run db upgrade      # applies any pending migrations (ALTER TABLE ...)
```

### Postgres
Set `DATABASE_URL=postgresql://user:pass@host:5432/holo_rtls`, install the driver
(`pip install -r requirements-postgres.txt`), then `flask db upgrade`. On Postgres,
prefer managed migrations (`AUTO_SCHEMA_RECONCILE=0`). See `docs/POSTGRES.md`.

---

## Which should I use?

| Situation | Use |
|---|---|
| Local dev, SQLite, iterating on models | Default auto-reconcile (nothing to do) |
| Production, Postgres, audited schema changes | Alembic migrations, `AUTO_SCHEMA_RECONCILE=0` |
| Dropping/renaming/retyping columns, backfills | Alembic migration (auto-reconcile can't) |

The two are compatible for *additive* changes but shouldn't both own the same change —
turn auto-reconcile off when you adopt managed migrations.

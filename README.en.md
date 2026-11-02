# Less

[中文](README.md) | [English](README.en.md)

**Read less. Know more.**

A local reading product that stores and presents a small set of useful Briefs. A content skill / agent discovers, filters, verifies, and distills sources; the application preserves facts, value, judgment, limitations, and primary references.

## Current features

- Preview a single Brief draft or JSON array in the administration page, then explicitly save each item. Unfinished items remain available after partial failure.
- Read Today by retention date while preserving actual source dates; inspect details and topics derived from saved Briefs.
- Optionally run morning/evening discovery and email digests when SMTP and Codex are configured.

See the [current documentation index](docs/README.md). The `v0.1-content-engine-prototype` tag retains the old engine; old specifications and operation notes are historical references.

## Run locally

The repository pins Python 3.12; the package supports 3.12–3.13. Install uv, Node.js, and npm, then run:

```bash
make setup
make dev
```

Open <http://127.0.0.1:5173>. First startup creates `data/less.db`. The local reading app does not require Docker, PostgreSQL, Redis, or an external API key. Copy `.env.example` to `.env` if you need to change the database path or Today timezone. An absolute SQLite URL looks like `sqlite:////absolute/path/to/less.db`.

## Drafts and content discovery

The repository skill lives in `.agents/skills/less-content/` and can be invoked as `$less-content` in a compatible agent. Manual runs produce drafts for human review; authorized scheduled tasks validate and save automatically.

Discovery first handles explicitly requested sources, then consults the versioned [preferred-source list](.agents/skills/less-content/references/preferred-sources.md), expanding search for coverage and cross-checking. The list is a starting point, not a whitelist or automatic collector. Observation scope and source roles are documented in the [current content-skill specification](docs/current/02-content-skill.md).

## Morning and evening digests

`make dev` starts the API, frontend, and a separate scheduler. While running, it schedules tasks at 06:00 and 18:00 in `LESS_TIMEZONE` (default `Asia/Shanghai`). Missed slots during sleep or downtime are not backfilled. Alternatively run `.venv/bin/less scheduler`, but do not run a second scheduler alongside `make dev`. Database date/slot uniqueness prevents duplicate execution.

Tasks use the locally authenticated Codex CLI and live web search. They search in Chinese and English for useful practice, supported interviews/opinions, and significant capability changes. Selection is value-based, with no fixed item count or language quota; source access gaps are recorded in `task_note`.

The main window is 12 hours with a 24-hour lookback for late discoveries. Date-only sources retain their date without an invented time. Candidate Briefs are compared with relevant saved items; ambiguous duplicates are not automatically kept. Verified high/medium-confidence items can be saved after validation and deduplication, with limitations required for medium confidence. Empty results also produce a short email. Delivery follows task completion and may occur after the scheduled time.

Configure these variables in the ignored `.env`, using [the example](.env.example):

| Variables | Purpose |
| --- | --- |
| `LESS_SMTP_HOST`, `LESS_SMTP_PORT` | SMTP host / port: 587 STARTTLS or 465 TLS |
| `LESS_SMTP_USERNAME`, `LESS_SMTP_PASSWORD` | Login and application password |
| `LESS_MAIL_FROM`, `LESS_MAIL_TO` | Sender and recipient |

Without SMTP, the scheduler records failure and does not start expensive content work. SMTP credentials are not passed to the Codex child process. `.venv/bin/less preview --slot morning` (or `evening`) generates a real content-based text preview without saving or emailing, but still runs content discovery; it is not an offline check. Runs are stored in SQLite `digest_runs`; task failures attempt notification, and SMTP failures receive limited retries.

HTML and text email share content rendering. The HTML uses a warm-white, olive, single-column layout, up to 640px wide, with inline styles and no external images/fonts. Browser previews do not establish compatibility with every mail client.

## Validation

```bash
make test
```

This covers SQLite API tests, Ruff, TypeScript/Vite build, and Playwright scenarios. After API changes, run `make api-types` to synchronize OpenAPI and frontend types. This documentation update did not start discovery, send email, or change scheduling.

## License and data

Do not commit the local database, SMTP passwords, or private email content. Preserve source URLs, dates, and limitations when using content.

The default branch does not include a project-level license file. Public visibility does not itself grant reuse rights. Third-party dependencies and assets retain their own terms.

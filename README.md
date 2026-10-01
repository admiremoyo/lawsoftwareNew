# LawPractice – practice management & trust accounting for law firms

A complete, browser-based system for running a law firm: clients and matters, checklists, diary, time
recording, fee notes, **trust accounting that can never be overdrawn**, business accounts and VAT, and
the reports partners and auditors ask for. Each firm runs on its own private server.

| Guide | For |
| --- | --- |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Setting up a firm's server (Docker, HTTPS, email, backups, updates) |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Taking a new client firm live: data migration, trust opening balances, training |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Day-to-day use by the firm's staff |
| [docs/SALES.md](docs/SALES.md) | Positioning, pricing, the demo script, finding firms, contracts you need |
| [marketing/index.html](marketing/index.html) | A ready-made landing page for your website |

## Features

**Practice management**
- Clients and matters with automatic codes and file numbers; file notes; private document storage
- Precedents (letters) merged with client and matter details, downloaded as Word documents
- Workflow checklists per matter type (conveyancing, estates, litigation, collections, divorce), added
  automatically with due dates; editable
- Diary with month view and agenda; dashboard of today's diary, court dates and deadlines, overdue
  checklist steps and prescription warnings
- Global search; interest calculator (with optional in duplum cap)

**Billing**
- Time recording (hours or minutes) at matter, fee-earner or firm rates; disbursements with or without VAT
- Fee notes: draft from unbilled work → issue → PDF with your logo → email to the client → record payment
  or pay from trust; voiding returns work to unbilled
- Client statements of account (screen, PDF, email)

**Trust accounting**
- Receipts (printable trust receipt), payments, matter-to-matter transfers, fees to business
- A matter's trust balance can never go below zero; entries are reversed, never edited or deleted;
  matters holding trust money can't be closed
- Monthly three-way reconciliation (bank statement, cash book, matter ledgers) and trust listing

**Business accounting**
- Business cash book; fee payments post automatically; expenses by category with input VAT
- VAT report (invoice or payments basis) and income statement

**Reports**: work in progress, aged debtors, trust balances, fee earner time, matter listing – CSV export.

**Security and administration**
- Roles (partner, associate, candidate attorney, secretary, bookkeeper) controlling trust, billing,
  accounting, settings and user management
- Two-factor sign-in (authenticator app), optionally compulsory for the firm; lockout after repeated
  failed sign-ins; password reset by email
- Audit log of every financial action and sign-in; financial records read-only in the admin site
- HTTPS with automatic certificates, strict security headers, private document downloads
- Nightly database and document backups with a tested restore script
- CSV import of clients and matters (with trust opening balances) for moving from another system
- First-run setup wizard; firm logo, VAT rate, currency and numbering configurable; product name
  configurable for selling under your own brand; works on phones and tablets

## Quick start (local demo)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in as `admin` / `demo-admin-2026` (partner) or
`associate` / `demo-associate-2026`.

Without `seed_demo`, the first visit opens the setup wizard instead.

## Production

```bash
cp .env.example .env    # fill in domain, secrets, email
docker compose up -d --build
```

This starts PostgreSQL, the app (gunicorn), Caddy (automatic HTTPS) and the nightly backup job. Full
instructions: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Tests

```bash
python manage.py test
```

The suite covers trust rules (no overdrafts, reversals, reconciliation), billing and VAT, permissions,
two-factor sign-in, lockout, imports, PDFs and email, and security regressions. GitHub Actions runs it on
PostgreSQL, plus `check --deploy` and a Docker build, on every push.

## Project layout

```
accounts/    sign-in, lockout, two-factor, roles & permissions, users, setup wizard
accounting/  business cash book, VAT report, income statement, client statements
billing/     time entries, disbursements, fee notes, payments, PDF/email
clients/     clients
core/        firm settings, dashboard, search, reports, import, audit log, PDF & email helpers
diary/       diary / calendar
matters/     matters, file notes, documents, precedents, workflows & checklists
trust/       trust cash book, services.py (all trust rules), reconciliation
deploy/      entrypoint, Caddyfile, backup / restore scripts
templates/   HTML and PDF templates (Bootstrap 5 bundled locally – no internet needed)
```

All trust money movements go through `trust/services.py`, where the no-overdraft rule and reversal logic
live.

> Trust accounting rules differ by jurisdiction. Have a trust-account auditor review the reports and
> procedures against your local rules before relying on them.

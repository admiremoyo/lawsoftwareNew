# LawPractice – law firm practice management & trust accounting

A web-based practice management system for law firms, in the spirit of LawPac: clients, matters/files,
time recording, fee notes, **trust accounting with reconciliation**, a diary, precedents and reports.
Built with Django and SQLite, so it runs on any office PC or server.

## Features

| Area | What it does |
| --- | --- |
| **Clients** | Individuals and companies, auto client codes (`CL00001`), contact details, ID/registration and VAT numbers. |
| **Matters** | Auto file numbers (`MAT00001`), matter type, responsible attorney, opposing party/attorney, court and case number, prescription date, hourly/fixed/contingency billing. Tabs for file notes, time, disbursements, fee notes, trust ledger, documents and diary. |
| **Time recording** | Hours or minutes per fee earner; rate taken from the matter override, then the fee earner's rate, then the firm default. Billed time is locked. |
| **Disbursements** | With or without VAT; locked once billed. |
| **Fee notes (invoices)** | Draft from unbilled time, disbursements and fixed-fee items → issue → receive payments. VAT calculated at the rate in force when the fee note was raised. Void releases the work for re-billing. Printable tax invoice (print to PDF). |
| **Trust account** | Receipts (with printable trust receipt), payments, transfers between matters, transfer of fees to business (settles a fee note). **A matter's trust ledger can never be overdrawn**, and one client's money can't be used for another. Entries are never edited or deleted, only reversed. Matters holding trust money can't be closed. |
| **Trust reconciliation** | Tick cleared items against the bank statement; three-way check of bank statement vs cash book vs total of matter ledgers. |
| **Diary** | Month calendar and agenda per fee earner: appointments, court dates, deadlines, tasks. Dashboard shows today's diary, upcoming court dates/deadlines, overdue items and prescription warnings. |
| **Precedents** | Document templates with merge fields (`{{ client.name }}`, `{{ matter.file_number }}`…) generated as Word documents and saved on the matter. Upload any other document to a matter. |
| **Reports** | WIP, aged debtors (30/60/90+), trust balances per matter (trust creditors), fee earner time, matter listing. CSV export. |
| **Admin** | Firm settings (name, VAT rate, currency symbol, number prefixes, bank details), user roles and hourly rates, audit log of every financial action. |

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # optional demo firm, clients, matters, trust entries
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in as `admin` / `admin123` (partner) or `associate` / `associate123`.

Without demo data, create your first user with `python manage.py createsuperuser`, then set up the firm
under **Firm settings** and add staff under **Users** (Django admin). Set each user's role and hourly rate
under *User profiles* in the admin.

Run the tests with `python manage.py test`.

## Configuration

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | dev key | **Set a long random value in production.** |
| `DJANGO_DEBUG` | `1` | Set to `0` in production. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated host names. |
| `DJANGO_DB_PATH` | `db.sqlite3` | SQLite file location. |
| `TIME_ZONE` | `UTC` | e.g. `Africa/Harare`, `Africa/Johannesburg`. |

For production run behind a proper web server (e.g. `gunicorn lawpractice.wsgi` + nginx), run
`python manage.py collectstatic`, serve `media/` (uploaded documents) privately, and back up the database
and `media/` daily.

## Project layout

```
core/      firm settings, user profiles, numbering, audit log, dashboard, search, reports
clients/   clients
matters/   matters, file notes, documents, precedents
billing/   time entries, disbursements, fee notes, payments
trust/     trust cash book, services.py (all trust rules), reconciliation
diary/     diary / calendar
templates/ HTML templates (Bootstrap 5, bundled in static/vendor – no internet needed)
```

All trust money movements go through `trust/services.py`, which is where the no-overdraft rule and
reversal logic live.

## Roadmap ideas

- Role-based permissions per screen (e.g. only bookkeepers post trust entries)
- Business (general ledger) accounting, VAT returns, bank feeds/statement import
- Interest-bearing trust investments per matter
- Email fee notes and statements to clients; client statement of account
- Conveyancing and estates workflows (checklists, deeds office/Master's office steps)
- Collections module with interest and tariff calculations
- PostgreSQL for multi-office deployments

> Trust accounting rules differ by jurisdiction (e.g. the relevant Legal Practitioners Act and Law Society
> rules). Have your auditor review the reports and procedures before relying on them.

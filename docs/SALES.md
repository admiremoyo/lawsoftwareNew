# Selling LawPractice

A practical playbook for finding the first paying law firms. The numbers are starting points to adapt
to your market, not advice.

## Who to sell to first

**Small and mid-sized firms (1–20 fee earners)** that today use one of:
- spreadsheets and paper trust ledgers,
- an ageing desktop system that only runs on one office PC,
- a general accounting package that doesn't understand trust money.

They feel three pains you solve directly:
1. **Trust account risk** – an overdrawn client ledger or an unbalanced reconciliation is an audit and
   disciplinary problem. The system makes overdrafts impossible and reconciles in minutes.
2. **Unbilled work** – time that is never recorded or billed. Time recording, WIP report, fee notes
   emailed as PDF in two clicks.
3. **Missed dates** – prescription, court dates and dies. Dashboard warnings and checklists.

## Positioning (one sentence)

> "Practice management and trust accounting for law firms – in your browser, on any device, with your
> trust account always balanced and your fees always billed."

**Do not** use the name "LawPac" (or any competitor's name) in your branding, website or product, or
claim to be compatible with, endorsed by or affiliated with it. You can truthfully say you help firms
*move from* their current system (the CSV import does that).

## What's included (feature list for proposals)

- Clients, matters (auto file numbers), file notes, documents, precedents with mail-merge
- Workflow checklists for conveyancing, estates, litigation, collections and divorce
- Diary: court dates, deadlines, prescription warnings
- Time recording, disbursements, fee notes with VAT, PDF and email
- Trust accounting: receipts, payments, transfers, fees to business, no-overdraft rule, reversals,
  monthly three-way reconciliation, trust listing
- Business account: income, expenses, VAT report, income statement, client statements
- Reports: WIP, aged debtors, fee earner time, matter listing (CSV export)
- Security: two-factor sign-in, roles and permissions, full audit log, encrypted HTTPS, nightly backups,
  each firm on its own isolated server
- Works on PCs, tablets and phones – nothing to install

## Pricing models

| Model | Example | Notes |
| --- | --- | --- |
| **Setup fee** | US$300–800 once | Covers server setup, data import, trust opening balances and 2 training sessions. Charge it – it filters out tyre-kickers and pays for your time. |
| **Monthly per user** | US$15–30 per user / month, minimum 3 users | Easy to understand; grows with the firm. |
| **Monthly per firm tier** | Solo US$40 · Up to 5 users US$99 · Up to 15 users US$199 | Simpler invoicing. |
| **Annual prepay** | 2 months free | Improves your cash flow. |

Your costs per firm are roughly the server (US$6–15/month), email sending (often free tier), off-site
backup storage (≈US$1–5/month) and your support time. Price so that **each firm covers its server many
times over**.

Offer a **30-day pilot**: the firm runs the system on a demo server with sample data plus a copy of a few
real matters, then you migrate them properly when they sign.

## The demo (30 minutes)

Use a separate demo server with `seed_demo` data (see `docs/DEPLOYMENT.md`).

1. **Dashboard** (2 min): today's diary, court dates, prescription warning, unbilled time, trust held.
2. **Open a matter** (5 min): new conveyancing matter → checklist appears with due dates.
3. **Trust** (8 min): receipt → print receipt. Try to pay out more than the balance → refused. *"This is
   the mistake that gets firms into trouble with the Law Society – it can't happen here."* Show the
   reconciliation screen.
4. **Billing** (8 min): record time → draft fee note → issue → PDF with their logo → email → pay from
   trust → appears in the business account.
5. **Reports** (4 min): WIP ("money you've earned but not billed"), aged debtors, VAT report.
6. **Security** (3 min): two-factor sign-in on your phone, roles, audit log, nightly backups.

Close: *"What would you need to see to start a 30-day pilot?"*

## Finding firms

- **Law Society / bar association** member directories and events; sponsor a CPD session on trust
  accounting compliance (teach, don't pitch).
- **Auditors and accountants who audit trust accounts** – they see which firms struggle. Offer them a
  referral fee (e.g. one month's subscription per signed firm).
- **Direct outreach**: 20 personalised emails/calls a week to small firms; offer a free "trust account
  health check" using the demo.
- **Referrals**: give each client a month free for every firm they refer.
- A simple **website** (`marketing/index.html` is a ready-made starting page) with a "Book a demo" button.

## Contracts and compliance you need before the first sale

Get a local lawyer to review these – your customers are lawyers and will read them.

- **Service agreement / terms**: what's included, uptime target, support hours and response times,
  fees and increases, termination, and **data export on exit** (you provide a full database and
  documents export).
- **Data processing agreement**: the firm is the controller of its clients' personal data; you are the
  processor. Cover where data is hosted, who can access it, breach notification, backups and deletion.
  Check your data-protection law (e.g. Zimbabwe's Cyber and Data Protection Act, South Africa's POPIA).
- **Trust accounting**: trust rules differ by jurisdiction. Before selling, have a trust-account auditor
  review the trust reports and reconciliation against the local rules, and keep their letter – it is a
  strong sales asset.
- **Professional indemnity / cyber insurance** for your business.

## Support routine

- A support email/WhatsApp number with stated hours.
- Monthly: check each firm's backups and `/health/` monitor, apply updates (`docs/DEPLOYMENT.md` §7).
- Quarterly: test-restore one firm's backup.
- Keep a short changelog to send customers with each update – it shows the product is alive.

# Onboarding a new client firm

A repeatable checklist for taking a firm from "signed" to "live". Typical duration: 1–2 weeks.

## Week 0 – before go-live

- [ ] Signed service agreement, data processing agreement and first invoice paid.
- [ ] Collect from the firm:
  - firm details: legal name, address, phone, email, VAT/tax number, logo (PNG/JPG)
  - business and trust bank account details
  - list of staff: name, email, role (partner / associate / candidate / secretary / bookkeeper), hourly rate
  - numbering preferences (file, client and fee note prefixes) and default hourly rate
  - their current matter types and standard steps (to adjust the workflow checklists)
  - letter templates they use most (letter of demand, engagement letter…) to set up as precedents
- [ ] Deploy their server (`docs/DEPLOYMENT.md`), complete the setup wizard and firm settings.
- [ ] Turn on *Require two-factor sign-in for all users*.

## Data migration

Agree a **cut-over date** (best: the last day of a month, right after a trust reconciliation).

1. Export clients and matters from the old system (or Excel) to CSV.
2. In **Import data**, download the `clients.csv` and `matters.csv` templates and map the columns.
3. Import clients, then matters. Every row is validated and previewed; nothing is saved if any row has a
   problem.
4. **Trust opening balances**: put each matter's trust balance at the cut-over date in the
   `trust_opening_balance` column of the matters file, dated the cut-over date.
5. Check: *Reports → Trust balances* total must equal the old system's trust listing **and** the reconciled
   trust bank balance on that date. Do not go live until it does.
6. Outstanding fee notes from the old system: create one fee note per matter with a fixed-fee line
   "Balance brought forward from previous system", dated the cut-over date, so debtors and statements are
   correct.
7. Business account: record an opening "Capital introduced"/opening-balance entry for the business bank
   balance at the cut-over date.

## Training (2 × 90 minutes is usually enough)

**Session 1 – everyone**: signing in and two-factor setup, dashboard, clients and matters, checklists,
file notes, documents and precedents, diary, recording time and disbursements.

**Session 2 – partners and bookkeeper**: trust receipts/payments/transfers and why the system refuses
overdrafts, reversals instead of deletions, fee notes (draft → issue → email → payment / pay from trust),
monthly trust reconciliation, business account and expenses, VAT report, income statement, statements,
users and roles, audit log.

## Go-live day

- [ ] Final import done and trust total agreed to the bank.
- [ ] Every user has signed in and set up two-factor sign-in.
- [ ] One real trust receipt, one time entry and one fee note processed with you watching.
- [ ] Off-site backups confirmed running.

## First month

- [ ] Check in after week 1 for questions.
- [ ] Sit with the bookkeeper for the first month-end trust reconciliation in the system.
- [ ] Share the reconciliation and trust listing with the firm's auditor and get their sign-off.

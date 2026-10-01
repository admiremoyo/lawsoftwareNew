# Deploying LawPractice for a client firm

Each law firm gets **its own copy** of the system: its own server (or stack), database, documents and
backups. Nothing is shared between firms, which keeps client confidentiality and trust money records
completely separate and makes pricing simple.

Time needed: about 45 minutes for the first firm, 15 minutes once you've done it before.

---

## 1. What you need

| Item | Recommendation |
| --- | --- |
| A server (VPS) | Ubuntu 24.04, 2 vCPU, 4 GB RAM, 60 GB disk. Any provider works (Hetzner, DigitalOcean, Contabo, AWS Lightsail, a local data centre). Small firms (≤10 users) run comfortably on this. |
| A domain name | e.g. `smithlaw.yourbrand.com` or the firm's own `practice.smithlaw.co.zw`. |
| An email sending account | Any SMTP service: the firm's Microsoft 365 / Google Workspace mailbox, Brevo, Mailgun, Amazon SES… Used for fee notes, statements and password resets. |
| Somewhere off the server for backups | Another server, cloud storage (S3, Backblaze B2, Google Drive via rclone), or an external drive at the firm. |

## 2. Point the domain at the server

At the domain's DNS provider create an **A record**: `smithlaw.yourbrand.com → <server IP address>`.
Wait until `ping smithlaw.yourbrand.com` shows the server's IP (usually minutes).

## 3. Install Docker on the server

```bash
ssh root@<server-ip>
curl -fsSL https://get.docker.com | sh
apt-get install -y git
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

## 4. Get the software and configure it

```bash
git clone https://github.com/admiremoyo/lawsoftwareNew.git /opt/lawpractice
cd /opt/lawpractice
cp .env.example .env
nano .env
```

Fill in `.env`:

- `DOMAIN`, `DJANGO_ALLOWED_HOSTS` – the domain from step 2.
- `DJANGO_CSRF_TRUSTED_ORIGINS` – the same, with `https://` in front.
- `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` – generate each with
  `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`. **Keep a copy of `.env` somewhere safe**
  (a password manager); you need it to restore backups onto a new server.
- `TIME_ZONE` – e.g. `Africa/Harare` or `Africa/Johannesburg`.
- `EMAIL_*` and `DEFAULT_FROM_EMAIL` – the SMTP account from step 1.
- `DJANGO_ADMIN_EMAILS` – your support address; you'll be emailed if the system hits an error.
- `PRODUCT_NAME` (optional) – the software name users see, if you sell it under your own brand.

## 5. Start it

```bash
docker compose up -d --build
docker compose ps        # all four services should be "Up", web "(healthy)"
```

The first start takes a few minutes. Caddy obtains an HTTPS certificate automatically.

Open `https://smithlaw.yourbrand.com` — the **setup wizard** appears. Enter the firm's name, currency and
VAT rate, and create the first partner's account. Then:

1. **Firm settings**: address, phone, VAT number, logo, banking details, trust bank account, number
   prefixes, default hourly rate, and (recommended) *Require two-factor sign-in for all users*.
2. **Users**: add each staff member with their role and hourly rate.
3. **Import data** (if moving from another system) – see `docs/ONBOARDING.md`.

## 6. Backups

The `backup` service writes a database dump and a copy of all documents to `/opt/lawpractice/backups/`
every night at `BACKUP_HOUR` and keeps `BACKUP_KEEP_DAYS` days.

**A backup on the same server is not enough.** Copy it off the server every day, for example with
[rclone](https://rclone.org) to cloud storage:

```bash
# once: rclone config   (create a remote called "offsite")
echo '30 2 * * * root rclone sync /opt/lawpractice/backups offsite:lawpractice-smithlaw' > /etc/cron.d/lawpractice-offsite
```

Run a backup immediately: `docker compose exec backup /deploy/backup.sh`

**Test a restore at least once per quarter** (ideally onto a spare server):

```bash
docker compose stop web
docker compose exec backup /deploy/restore.sh /backups/<timestamp>   # type RESTORE to confirm
docker compose start web
```

## 7. Updating to a new version

```bash
cd /opt/lawpractice
docker compose exec backup /deploy/backup.sh     # always back up first
git pull
docker compose up -d --build                     # database migrations run automatically
```

## 8. Monitoring

- `https://<domain>/health/` returns `{"status": "ok"}` — add it to a free uptime monitor
  (UptimeRobot, Better Stack) so you know before the firm does.
- Logs: `docker compose logs -f web`
- Disk space: `df -h` (documents grow over time).

## 9. Security checklist per firm

- [ ] `.env` has a unique secret key and database password, stored in your password manager.
- [ ] Two-factor sign-in required for all users (Firm settings).
- [ ] Off-server backups running and a restore tested.
- [ ] Server firewall allows only ports 22, 80, 443; SSH uses keys, not passwords
      (`PasswordAuthentication no` in `/etc/ssh/sshd_config`).
- [ ] Automatic security updates on the server: `apt-get install -y unattended-upgrades`.
- [ ] Uptime monitor on `/health/`.
- [ ] The firm has signed your service agreement and data processing agreement (see `docs/SALES.md`).

## Running a demo / sales instance

Deploy as above on a separate server (e.g. `demo.yourbrand.com`), then load sample data:

```bash
docker compose exec web python manage.py seed_demo --force
```

Sign in as `admin` / `demo-admin-2026`. Never load demo data on a real firm's system.

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py seed_demo && python manage.py runserver
python manage.py test
```

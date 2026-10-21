# Deploying DairyERP on the VPS (Docker + Nginx)

Live at **https://app.akashdairyfarm.in** on the Hostinger VPS (Ubuntu).

## Layout on the server

| Path | What |
|---|---|
| `/opt/dairyerp` | Clone of the GitHub repo (`docker-compose.yml`, `Dockerfile`, `deploy/`) |
| `/opt/dairyerp/.env` | `SECRET_KEY=...` (not in git). Logins and the saved SMTP password depend on it; never change or lose it |
| `/opt/dairyerp/data/dairy_erp.db` | The database (SQLite) |
| `/opt/dairyerp/data/uploads/` | Claim and delivery photos |
| `/opt/dairyerp/data/download/` | `AkashDairy.apk` for the app download link |
| `/opt/dairyerp/backups/` | Daily backups at 2:30 AM, kept 30 days (`deploy/backup.sh`) |
| `/etc/nginx/sites-available/akashdairyfarm` | Nginx (copy of `deploy/nginx-akashdairyfarm.conf` plus certbot's HTTPS part) |

The app runs in one container (`dairyerp`) on `127.0.0.1:8000`. Only Nginx can reach it.
**Run exactly one container.** The automatic dispatcher and the email sender run inside it, so a second copy would dispatch and send emails twice.

## Everyday commands (on the VPS)

```sh
cd /opt/dairyerp
sh deploy/update.sh          # backup, git pull, rebuild, restart
docker compose logs -f --tail 100   # live log
docker compose restart       # restart
sh deploy/backup.sh          # backup now
```

## Releasing new code

1. On the PC: commit and `git push`.
2. On the VPS: `sh /opt/dairyerp/deploy/update.sh`.

## Restoring a backup

```sh
cd /opt/dairyerp
docker compose stop
gunzip -c backups/dairy_erp_YYYYMMDD_HHMM.db.gz > data/dairy_erp.db
chown 1000:1000 data/dairy_erp.db
docker compose start
```

## Other settings (environment, in docker-compose.yml)

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:////data/dairy_erp.db` | |
| `APP_TIMEZONE` | `Asia/Kolkata` | Order cut-off and the 4 AM dispatch use Indian time |
| `DAIRY_UPLOAD_DIR` | `/data/uploads` | |
| `DAIRY_DOCS` | off | `1` shows the API docs at `/docs` |
| `DAIRY_AUTO_DISPATCH` | on | `0` stops the automatic dispatcher |
| `DAIRY_EMAIL_WORKER` | on | `0` stops sending emails |

## After it is live

- **Admin, Billing → Dairy Settings:** fill contact email and address.
- **Admin, Email (SMTP):** fill the Hostinger mailbox details. Set the portal address to `https://app.akashdairyfarm.in` and send a test email.
- **Admin, B2B Customers:** add customer email addresses.
- **Flutter app:** build with `--dart-define=API_BASE_URL=https://app.akashdairyfarm.in/api/v1`.
- **Default passwords:** change the admin and staff passwords.

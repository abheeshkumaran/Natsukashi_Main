# Deploying to AWS (Lightsail + RDS)

I can't create AWS resources myself (no account access) — this is the checklist to run yourself. Everything code-side is already prepared in this repo/`deploy/` folder.

## 1. Create the RDS Postgres instance

AWS Console → RDS → Create database:
- Engine: PostgreSQL (match the version Railway is on — check with `SELECT version();` on the current DB)
- Templates: Free tier (to start) or Production, your call
- DB instance identifier: `natsukashi-db`
- Master username/password: set a strong password, save it somewhere safe
- Instance size: `db.t4g.micro` is enough to start
- Storage: 20GB gp3 is plenty to start
- **VPC**: same region you'll put the Lightsail instance in (matters for latency)
- Public access: **No** if RDS and the app are in the same VPC (more secure); otherwise Yes with a locked-down security group allowing only your app server's IP on port 5432
- Note the endpoint hostname once it's created (looks like `natsukashi-db.xxxxx.<region>.rds.amazonaws.com`)

## 2. Migrate the data from Railway to RDS

From your machine (with `psql`/`pg_dump` installed, or via this repo's `.venv`):

```bash
# Dump from Railway - get the current connection string from the Railway
# dashboard (Postgres service > Connect tab), don't hardcode it in any file
pg_dump "<railway-connection-string>" \
    --no-owner --no-acl -F c -f natsukashi_backup.dump

# Restore into RDS
pg_restore --no-owner --no-acl -h <rds-endpoint> -U postgres -d postgres -c natsukashi_backup.dump
```

Verify row counts match on both sides (`SELECT count(*) FROM orders;` etc.) before cutting over.

## 3. Create the Lightsail instance

AWS Console → Lightsail → Create instance:
- Platform: Linux/Unix
- Blueprint: OS Only → Ubuntu 24.04 LTS
- Instance plan: $7/month (1GB RAM) is a reasonable starting point
- Same region as the RDS instance
- Name it, create it, note its public IP

Once running, SSH in (Lightsail gives you a browser SSH button, or download the key and `ssh ubuntu@<ip>`).

## 4. Server setup (run on the Lightsail instance)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx git libpq-dev

git clone <your-repo-url> Natsukashi_Main
cd Natsukashi_Main

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env here with production values - DATABASE_URL pointing at RDS,
# DJANGO_DEBUG=False, a fresh DJANGO_SECRET_KEY, Razorpay/Cloudinary/email
# keys, RAZORPAY_WEBHOOK_SECRET. See .env.example for the full list.
nano .env

python manage.py migrate
python manage.py collectstatic --noinput
```

## 5. Wire up gunicorn + nginx

```bash
sudo cp deploy/natsukashi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now natsukashi
sudo systemctl status natsukashi   # confirm it's running

sudo cp deploy/nginx_natsukashi.conf /etc/nginx/sites-available/natsukashi
sudo ln -s /etc/nginx/sites-available/natsukashi /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
# Edit server_name in the nginx config to your actual domain/IP first
sudo nginx -t && sudo systemctl reload nginx
```

Site should now be reachable on port 80 at the Lightsail static IP.

## 6. Domain + HTTPS

- Point your domain's DNS A record at the Lightsail static IP (attach a static IP to the instance first, in Lightsail's Networking tab, so it survives reboots)
- `sudo apt install -y certbot python3-certbot-nginx`
- `sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com`
- Update `ALLOWED_HOSTS` in `settings.py` from `['*']` to `['yourdomain.com', 'www.yourdomain.com']`

## 7. Update external configs pointing at the old Vercel URL

- Razorpay Dashboard webhook URL → new domain's `/razorpay/webhook/`
- Any hardcoded `natsukashi-main.vercel.app` references

## Redeploying after code changes

```bash
cd ~/Natsukashi_Main
git pull
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart natsukashi
```

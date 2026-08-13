# Deploying to AWS (Lightsail + RDS + S3)

I can't create AWS resources myself (no account access) — this is the checklist to run yourself, in order. Everything code-side is already prepared in this repo.

## 1. Create the RDS Postgres instance

AWS Console → RDS → Create database:
- Engine: PostgreSQL (match the version Railway is on — check with `SELECT version();` on the current DB)
- Templates: Free tier (to start) or Production, your call
- DB instance identifier: `natsukashi-db`
- Master username/password: set a strong password, save it somewhere safe (password manager, not a repo file)
- Instance size: `db.t4g.micro` is enough to start
- Storage: 20GB gp3 is plenty to start
- **VPC**: same region you'll put the Lightsail instance in (matters for latency)
- Public access: **No** if RDS and the app end up in the same VPC (more secure); otherwise Yes with a security group locked down to only your app server's IP on port 5432
- Note the endpoint hostname once it's created (looks like `natsukashi-db.xxxxx.<region>.rds.amazonaws.com`)

### Migrate the data from Railway to RDS

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

## 2. Create the Lightsail instance

AWS Console → Lightsail → Create instance:
- Platform: Linux/Unix
- Blueprint: OS Only → Ubuntu 24.04 LTS
- Instance plan: $7/month (1GB RAM) is a reasonable starting point
- Same region as the RDS instance
- Name it, create it, note its public IP
- Networking tab → attach a **static IP** to the instance (so it survives reboots) before pointing DNS at it

Once running, SSH in (Lightsail gives you a browser SSH button, or download the key and `ssh ubuntu@<ip>`).

## 3. Server setup

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx git libpq-dev

git clone <your-repo-url> Natsukashi_Main
cd Natsukashi_Main

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env here with production values. See .env.example for the full
# list - at minimum: DATABASE_URL (pointing at RDS), DJANGO_DEBUG=False,
# a fresh DJANGO_SECRET_KEY, Razorpay/Cloudinary/email keys,
# RAZORPAY_WEBHOOK_SECRET, and the AWS_* keys below if using S3.
nano .env

python manage.py migrate
python manage.py collectstatic --noinput
```

## 4. Process manager: PM2

```bash
sudo apt install -y nodejs npm
sudo npm install -g pm2

cd ~/Natsukashi_Main
pm2 start deploy/ecosystem.config.js
pm2 save
pm2 startup    # prints a command - copy/paste and run it, enables PM2 on reboot
```

Useful commands: `pm2 status`, `pm2 logs natsukashi`, `pm2 restart natsukashi`.

(`deploy/natsukashi.service` is also included as a systemd-based alternative to PM2, in case you'd rather not run Node.js on the box just to manage a Python process - use one or the other, not both.)

## 5. Nginx reverse proxy

```bash
sudo cp deploy/nginx_natsukashi.conf /etc/nginx/sites-available/natsukashi
sudo ln -s /etc/nginx/sites-available/natsukashi /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
# Edit server_name in the nginx config to your actual domain first
sudo nginx -t && sudo systemctl reload nginx
```

Site should now be reachable on port 80 at the Lightsail static IP.

## 6. Domain + HTTPS

- Point your domain's DNS **A record** at the Lightsail static IP (with your registrar, or Route 53 if you move DNS to AWS)
- `sudo apt install -y certbot python3-certbot-nginx`
- `sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com`
- Certbot auto-configures nginx for HTTPS and sets up auto-renewal
- Update `ALLOWED_HOSTS` in `natsukashi_design/settings.py` from `['*']` to `['yourdomain.com', 'www.yourdomain.com']`

## 7. S3 for media (optional)

`settings.py` already has an opt-in S3 block (`natsukashi_design/settings.py`, search for `AWS_STORAGE_BUCKET_NAME`) using `django-storages` + `boto3` (already in `requirements.txt`). It's inert until you set the env vars below - nothing changes unless you do this.

**AWS side:**
- S3 → Create bucket, e.g. `natsukashi-media`, same region as everything else
- Keep "Block all public access" **ON** - the bucket stays private; the app serves images via time-limited signed URLs instead (`AWS_QUERYSTRING_AUTH = True` in settings.py, 1 hour expiry)
- IAM → create a user (or better, if the app runs on EC2/Lightsail with an instance role, prefer that over long-lived keys) with a policy scoped to just this bucket (`s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket` on `arn:aws:s3:::natsukashi-media` and `arn:aws:s3:::natsukashi-media/*`)
- Generate an access key pair for that user

**Add to `.env`:**
```
AWS_STORAGE_BUCKET_NAME=natsukashi-media
AWS_ACCESS_KEY_ID=<your key>
AWS_SECRET_ACCESS_KEY=<your secret>
AWS_S3_REGION_NAME=ap-south-1
```

**Important - this does NOT move existing images automatically.** `Product.image`, `Category.image`, and the `related_image` field currently use `CloudinaryField` (`product/models.py`), which has its own storage baked in and doesn't go through Django's `STORAGES["default"]` at all - so setting the env vars above only affects *new* plain `ImageField`/`FileField`s, not these existing Cloudinary-backed ones.

To actually cut product/category images over to S3, tell me when you're ready and I'll:
1. Change those 3 fields from `CloudinaryField` to `models.ImageField`
2. Generate the migration
3. Write a one-off script to download each image from its current Cloudinary URL and re-upload it into S3 under the new field, so existing product photos aren't lost

That's a deliberate step involving your live product images, so I'm not doing it as part of this deploy prep without your go-ahead on timing.

## 8. Update external configs pointing at the old Vercel URL

- Razorpay Dashboard → webhook URL → your new domain's `/razorpay/webhook/`
- Anywhere else `natsukashi-main.vercel.app` was hardcoded or shared

## Redeploying after code changes

```bash
cd ~/Natsukashi_Main
git pull
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
pm2 restart natsukashi        # or: sudo systemctl restart natsukashi
```

# Redeploying (quick reference)

Run on the Lightsail server, in order, whenever new code needs to go live.

```bash
cd ~/Natsukashi_Main
source .venv/bin/activate

git pull
```

**If `git pull` fails with `.env` conflicts** (happens if `.env` still shows up in `git status` as modified/tracked): back it up first, then resolve.
```bash
cp .env .env.backup
git stash push -- .env
git pull
git stash pop          # if this reports a conflict on .env, that's OK - see below
```
If `git stash pop` reports `CONFLICT (modify/delete): .env` — that's expected once `.env` is untracked upstream. The real file content on disk is already correct at that point (confirm with `diff .env .env.backup`, should show nothing). Just resolve the git state and move on:
```bash
git rm --cached .env
git stash drop
```

Then continue:

```bash
pip install -r requirements.txt

python manage.py migrate

# Only needed once, the first time media moves to a new S3 bucket -
# safe to skip on routine redeploys once it's already been run successfully.
python manage.py migrate_media_to_s3

python manage.py collectstatic --noinput

pm2 restart natsukashi
```

**Confirm it's actually up**, don't just trust the restart succeeded:
```bash
pm2 status                              # should show natsukashi as "online" with a low/zero restart count (↺) right after this restart
pm2 logs natsukashi --lines 30 --nostream   # check for a traceback near the bottom
```

If `pm2 status` shows the restart count (`↺`) climbing on its own a few seconds after this, the app is crash-looping — check the traceback in `pm2 logs` before assuming the deploy worked.

Finally, check the site actually responds:
```bash
curl -I http://localhost/
```
Expect a `200` (or a redirect), not `502`.

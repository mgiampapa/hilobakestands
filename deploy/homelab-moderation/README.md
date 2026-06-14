# Homelab moderation fallback (media.home)

Fallback NSFW check for owner photo uploads. The site tries Google Vision
SafeSearch first (free 1,000/month); this service only gets called when
Google errors or the quota is gone. Score ≥ 0.5 → photo held for review.

Model: Falconsai/nsfw_image_detection (ViT, ~350 MB, CPU). RAM use is
~1.5 GB resident — nothing on a 16 GB box.

## Install (paste on media.home)

```bash
sudo mkdir -p /srv/hilobakestand_moderation && sudo chown $USER /srv/hilobakestand_moderation && cd /srv/hilobakestand_moderation && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt && echo "MODERATION_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')" > .env && chmod 600 .env && cat .env
```

(Copy `app.py`, `requirements.txt`, and the `.service` file into
`/srv/hilobakestand_moderation/` first — or scp them from the repo's
`deploy/homelab-moderation/`.)

Note the token it prints — the same value goes on the Oracle box.

## Run as a service

```bash
sudo cp hilobake-moderation.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now hilobake-moderation && sleep 5 && curl -s localhost:8788/healthz
```

First start downloads the model from Hugging Face (~350 MB, one time).

## Reachability from the Oracle box

The Oracle box needs to reach `media.home.giampapa.com:8788`. Either
forward port 8788 on the router (token auth protects the endpoint; it
only ever returns a number), or put it behind the existing reverse proxy
with HTTPS. Then on the Oracle box add to `/opt/hilobakestands/.env`:

```
MODERATION_FALLBACK_URL=http://media.home.giampapa.com:8788/check
MODERATION_FALLBACK_TOKEN=<the token from install>
```

and `sudo systemctl restart hilobakestands`.

## Test it

```bash
curl -s -X POST -H "X-Auth-Token: $(grep -o '=.*' .env | cut -c2-)" --data-binary @/some/photo.jpg localhost:8788/check
```

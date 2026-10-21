#!/bin/sh
# Pull the latest code from GitHub and restart the app. Takes a backup first.
set -eu
cd /opt/dairyerp
sh deploy/backup.sh
git pull --ff-only
docker compose up -d --build
docker image prune -f >/dev/null
docker compose ps

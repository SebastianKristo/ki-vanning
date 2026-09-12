#!/bin/bash
# Bruk: bash ~/ki-push-vanning.sh 1.0.0
# Pakker ut ki-vanning-<versjon>.zip fra ~/Downloads og pusher til GitHub.
set -e
V=$1
[ -z "$V" ] && { echo "Bruk: ki-push-vanning.sh 1.0.0"; exit 1; }
REPO=~/Documents/HomeAssistant/ki-vanning
cd ~/Downloads
rm -rf "ki-vanning-$V" && unzip -oq "ki-vanning-$V.zip" -d "ki-vanning-$V"
# Første gang: klon repoet som allerede finnes på GitHub
[ -d "$REPO/.git" ] || git clone -q https://github.com/SebastianKristo/ki-vanning.git "$REPO"
cp -r "ki-vanning-$V/ki-vanning/." "$REPO/"
cd "$REPO"
# hold manifest-versjonen i takt med taggen
perl -pi -e "s/\"version\": \"[^\"]*\"/\"version\": \"$V\"/" custom_components/ki_vanning/manifest.json
git add .
git commit -m "KI Vanning v$V" || true
git push origin main
git tag -f "v$V" && git push -f origin "v$V"
echo "Ferdig. Lag release: https://github.com/SebastianKristo/ki-vanning/releases/new?tag=v$V"

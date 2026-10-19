#!/bin/sh
# Run only after unpacking a new, reviewed release and passing its tests.
set -eu
release=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
base="$HOME/windtunnel-control"
case "$release" in "$base"/releases/*) ;; *) echo 'Unexpected release directory' >&2; exit 1 ;; esac
stamp=$(date +%Y%m%dT%H%M%S)
backup="$base/backups/$stamp"
mkdir -p "$backup" "$base/evidence" "$HOME/.config/systemd/user" "$HOME/.config/autostart"
chmod 700 "$backup"
for item in .config/systemd/user/windtunnel-kiosk.service .config/autostart/windtunnel-kiosk.desktop; do
    if test -e "$HOME/$item"; then cp -p "$HOME/$item" "$backup/$(basename "$item")"; fi
done
if test -L "$base/current"; then readlink "$base/current" > "$backup/previous-release.txt"; fi
if test -e "$base/current" && ! test -L "$base/current"; then echo 'current is not a managed symlink' >&2; exit 1; fi
systemctl --user stop windtunnel-kiosk.service 2>/dev/null || true
ln -sfn "$release" "$base/current"
install -m 644 "$release/deploy/pi/windtunnel-kiosk.service" "$HOME/.config/systemd/user/windtunnel-kiosk.service"
install -m 644 "$release/deploy/pi/windtunnel-kiosk.desktop" "$HOME/.config/autostart/windtunnel-kiosk.desktop"
systemctl --user daemon-reload
systemd-analyze --user verify "$HOME/.config/systemd/user/windtunnel-kiosk.service"
printf 'Installed %s\nBackup %s\n' "$release" "$backup"

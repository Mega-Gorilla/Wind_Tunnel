#!/bin/sh
set -eu
# Import only the graphical-session variables needed by this dedicated user unit.
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP
exec systemctl --user start windtunnel-kiosk.service

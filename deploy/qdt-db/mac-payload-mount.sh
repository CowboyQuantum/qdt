#!/bin/bash
# Mac laptop: mount the qdt-db payload share at every login, without Finder (deploy/qdt-db/README.md,
# Part 5 step 5). Safe to run again: every step checks before it changes anything.
#
#   bash deploy/qdt-db/mac-payload-mount.sh            # install (default) and mount now
#   bash deploy/qdt-db/mac-payload-mount.sh check      # is the share mounted, what did the last login do
#   bash deploy/qdt-db/mac-payload-mount.sh uninstall  # undo everything install did
#
# Names can be changed with environment variables when the share is not the runbook's default:
#   QDT_DB_HOST=qdt-db  QDT_SHARE=qdt-payloads  QDT_SHARE_USER=qdtshare  QDT_MOUNT_POINT=$HOME/qdt-payloads
#
# What install does, and why (the runbook explains each in prose):
#   1. Requires the keychain entry Finder saved when you connected once by hand (Cmd-K, Remember password):
#      the share password is read from there and written in no file.
#   2. Creates the mount point, an empty folder in your home directory, read-only (chmod 555) so that an
#      unmounted share refuses writes instead of swallowing payloads locally, and locked (chflags uchg) so
#      it cannot be moved, renamed or deleted by accident.
#   3. Writes ~/Library/Scripts/mount-qdt-payloads.sh: mount_smbfs onto the mount point, retrying for five
#      minutes while the network (or Tailscale) comes up; it logs to ~/Library/Logs/mount-qdt-payloads.log.
#   4. Writes and loads a Launch Agent, ~/Library/LaunchAgents/com.qdt.mount-payloads.plist, that runs the
#      script at every login.
#   5. Runs the script once now. The first run opens a dialog asking whether `security` may read the
#      password from the keychain: click "Always Allow".
set -eu

HOST="${QDT_DB_HOST:-qdt-db}"
SHARE="${QDT_SHARE:-qdt-payloads}"
USER_="${QDT_SHARE_USER:-qdtshare}"
MP="${QDT_MOUNT_POINT:-$HOME/qdt-payloads}"
SCRIPT="$HOME/Library/Scripts/mount-qdt-payloads.sh"
LABEL="com.qdt.mount-payloads"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/mount-qdt-payloads.log"
DOMAIN="gui/$(id -u)"

say() { printf '%s\n' "$*"; }
die() { printf 'mac-payload-mount: %s\n' "$*" >&2; exit 1; }
mounted() { mount | grep -q " $MP "; }

[ "$(uname)" = Darwin ] || die "this script is for a Mac; a Windows laptop needs no mount (README Part 5)"

check() {
  if mounted; then
    say "mounted: $(mount | grep " $MP " | cut -d' ' -f1) on $MP"
  else
    say "NOT mounted: $MP"
  fi
  if [ -f "$PLIST" ]; then
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      say "launch agent: loaded ($PLIST)"
    else
      say "launch agent: file present but NOT loaded; run install again"
    fi
  else
    say "launch agent: not installed"
  fi
  if [ -f "$LOG" ]; then
    say "last log lines ($LOG):"
    tail -n 3 "$LOG" | sed 's/^/  /'
  fi
  if [ -d "$MP" ] && ! mounted; then
    if touch "$MP/.qdt-write-test" 2>/dev/null; then
      rm -f "$MP/.qdt-write-test"
      say "WARNING: the unmounted mount point accepts writes; run install again to make it read-only"
    else
      say "safeguard: the unmounted mount point refuses writes (good)"
    fi
  fi
  mounted
}

install() {
  # 1. the keychain entry
  security find-internet-password -s "$HOST" -a "$USER_" >/dev/null 2>&1 \
    || die "no keychain entry for $USER_ on $HOST. In Finder press Cmd-K, connect to smb://$HOST/$SHARE as $USER_, tick 'Remember this password in my keychain', then run this again"
  say "keychain: entry for $USER_ on $HOST found"

  # 2. the mount point: empty, read-only, locked
  if mounted; then
    umount "$MP" || die "could not unmount $MP; close anything using it and run again"
  fi
  if [ -e "$MP" ]; then
    [ -d "$MP" ] || die "$MP exists and is not a folder"
    [ -z "$(ls -A "$MP")" ] || die "$MP is not empty; it must be an empty folder (move its contents elsewhere)"
    chflags nouchg "$MP"
  else
    mkdir -p "$MP"
  fi
  chmod 555 "$MP"
  chflags uchg "$MP"
  say "mount point: $MP (empty, read-only, locked)"

  # 3. the mount script
  mkdir -p "$(dirname "$SCRIPT")" "$(dirname "$LOG")"
  cat > "$SCRIPT" <<EOF
#!/bin/sh
# Written by deploy/qdt-db/mac-payload-mount.sh. Mount the $SHARE share at login, bypassing Finder;
# retry for ~5 min while the network comes up. The password comes from the keychain entry Finder saved.
MP="$MP"
LOG="$LOG"
echo "\$(date) start" >> "\$LOG"
PW=\$(security find-internet-password -s "$HOST" -a "$USER_" -w) || { echo "\$(date) no keychain entry" >> "\$LOG"; exit 1; }
for i in \$(seq 1 30); do
  if mount | grep -q " \$MP "; then echo "\$(date) mounted" >> "\$LOG"; exit 0; fi
  mount_smbfs -N "//$USER_:\$PW@$HOST/$SHARE" "\$MP" >> "\$LOG" 2>&1 && { echo "\$(date) mounted" >> "\$LOG"; exit 0; }
  sleep 10
done
echo "\$(date) gave up" >> "\$LOG"
exit 1
EOF
  chmod 700 "$SCRIPT"
  say "mount script: $SCRIPT"

  # 4. the launch agent
  mkdir -p "$(dirname "$PLIST")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>$SCRIPT</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
EOF
  plutil -lint "$PLIST" >/dev/null || die "the launch agent file did not validate: $PLIST"
  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  launchctl bootstrap "$DOMAIN" "$PLIST"
  say "launch agent: $LABEL loaded (runs at every login)"

  # 5. mount now
  say "mounting now; if a dialog asks whether 'security' may use the keychain, click Always Allow..."
  if sh "$SCRIPT"; then
    say "mounted: $MP"
  else
    say "mount failed; the reason is in $LOG:"
    tail -n 3 "$LOG" | sed 's/^/  /'
    exit 1
  fi
  say ""
  say "Give the measurement PC this path in Part 7:  $MP"
  say "Test that counts: log out and in again, wait a minute, then:  bash $0 check"
}

uninstall() {
  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  rm -f "$PLIST" "$SCRIPT"
  if mounted; then umount "$MP" || die "could not unmount $MP; close anything using it and run again"; fi
  if [ -d "$MP" ]; then
    chflags nouchg "$MP"
    rmdir "$MP" || die "$MP is not empty; left in place"
  fi
  say "removed: launch agent, mount script and $MP (the keychain entry and $LOG are kept)"
}

case "${1:-install}" in
  install) install ;;
  check) check ;;
  uninstall) uninstall ;;
  *) die "unknown command '$1'; use install, check or uninstall" ;;
esac

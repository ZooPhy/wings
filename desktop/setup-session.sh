#!/bin/bash
# Setup is independent of the interactive launcher and the browser status tab.
set -uo pipefail
resources="${1:?Resources required}"
workspace="${2:?Workspace required}"
email="${3:-}"
done_path="${4:?Completion path required}"
log_path="${5:?Log path required}"
backend="$resources/desktop.sh"
umask 077
mkdir -p "$workspace/.desktop" "$workspace/logs"
touch "$log_path"
lock="$workspace/.desktop/setup-session.lock"
if ! mkdir "$lock" 2>/dev/null; then
    prior="$(cat "$lock/pid" 2>/dev/null || true)"
    if [[ "$prior" =~ ^[0-9]+$ ]] && kill -0 "$prior" 2>/dev/null; then
        page="$(cat "$lock/page" 2>/dev/null || true)"
        case "$page" in "$workspace"/logs/*.log.status/index.html)
            /usr/bin/open "$page" >/dev/null 2>&1 || true;;
        esac
        echo 'Setup is already running. Showing its progress page.' >> "$log_path"
        exit 0
    fi
    rm -f "$lock/pid" "$lock/page"
    rmdir "$lock" 2>/dev/null && mkdir "$lock" || exit 13
fi
printf '%s\n' "$$" > "$lock/pid"
finished=false
progress_dir=''
cleanup() {
    code=$?
    trap - EXIT
    if [[ "$finished" == false && -n "$progress_dir" ]]; then
        progress_status=interrupted
        progress_tick || true
    fi
    rm -f "$lock/pid" "$lock/page"
    rmdir "$lock" 2>/dev/null || true
    exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
. "$resources/setup-progress.sh"
progress_init || exit 1
printf '%s\n' "$progress_dir/index.html" > "$lock/page"
printf '%s\n' "$progress_dir/index.html" > "$workspace/.desktop/setup-page.tmp"
mv -f "$workspace/.desktop/setup-page.tmp" "$workspace/.desktop/setup-page"
# Launch the progress tab before any expensive setup work. No native Cocoa
# helper, loopback HTTP server, or host Python/Node installation is needed.
if ! /usr/bin/open "$progress_dir/index.html" >/dev/null 2>&1; then
    printf 'The setup progress page could not open. Setup will continue.\n' >> "$log_path"
    /usr/bin/osascript -e 'display dialog "WINGS could not open the setup progress page. Setup is continuing. Reopen WINGS and choose Settings → View setup progress to try again." buttons {"OK"} with title "WINGS setup"' >/dev/null 2>&1 &
fi
printf 'Starting WINGS setup…\n' > "$workspace/.desktop/progress"
/bin/bash "$backend" launch "$workspace" "$email" >> "$log_path" 2>&1 &
setup_pid=$!
email=''
while kill -0 "$setup_pid" 2>/dev/null; do
    progress_tick
    sleep 1
done
wait "$setup_pid"
setup_status=$?
printf '%s\n' "$setup_status" > "$done_path.tmp"
/bin/mv -f "$done_path.tmp" "$done_path"
if [[ "$setup_status" -ne 0 ]]; then
    progress_status=failed
    progress_tick
    finished=true
    exit "$setup_status"
fi
# Never expose the authenticated session URL in the progress file or logs.
if start_url="$(/bin/bash "$backend" url "$workspace" 2>> "$log_path")"; then
    if /usr/bin/open "$start_url" >/dev/null 2>&1; then
        progress_opened=true
        printf 'Opened WINGS in the browser.\n' >> "$log_path"
    else
        printf 'WINGS is running, but the browser could not open. Reopen WINGS to retry.\n' >> "$log_path"
    fi
else
    printf 'Could not obtain the running WINGS address. Reopen WINGS to retry.\n' >> "$log_path"
fi
start_url=''
progress_phase=6
progress_status=ready
progress_tick
finished=true
exit 0

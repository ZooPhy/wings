#!/bin/bash
# Package an already signed app without rebuilding or re-signing it.
set -euo pipefail
app="${1:?Usage: package-wings-dmg.sh /path/to/WINGS.app output-directory}"
destination="${2:?Output directory required}"
[[ "$(uname -s)" == Darwin ]] || { echo 'This packaging step needs macOS.' >&2; exit 1; }
[[ -d "$app/Contents" ]] || { echo 'Input app was not found.' >&2; exit 1; }
app="$(cd "$app" && pwd -P)"
mkdir -p "$destination"
destination="$(cd "$destination" && pwd -P)"
final="$destination/WINGS-Desktop-Preview.dmg"
pending="$destination/.WINGS-Desktop-Preview.pending.dmg"
log="$destination/packaging.log"
[[ ! -e "$final" && ! -e "$pending" && ! -e "$log" ]] || {
    echo 'Choose a fresh output directory; existing outputs will not be replaced.' >&2
    exit 1
}
: > "$log"
scratch="$(mktemp -d /private/tmp/wings-package.XXXXXX)"
mountpoint="$scratch/volume"
working="$scratch/working.dmg"
mounted=0
mkdir -p "$mountpoint"

cleanup() {
    status=$?
    trap - EXIT
    if [[ "$mounted" == 1 ]]; then
        if /usr/bin/hdiutil detach "$mountpoint" >> "$log" 2>&1; then
            mounted=0
        fi
    fi
    if [[ "$status" == 0 && "$mounted" == 0 ]]; then
        /bin/rm -rf "$scratch"
    else
        printf '\nPackaging stopped. Diagnostics: %s\nWorking files preserved: %s\n' "$log" "$scratch" >&2
        if [[ "$mounted" == 1 ]]; then
            printf 'Temporary image remains mounted at: %s\n' "$mountpoint" >&2
        fi
    fi
    exit "$status"
}
trap cleanup EXIT

run() {
    printf '\nCOMMAND:' >> "$log"
    printf ' %q' "$@" >> "$log"
    printf '\n' >> "$log"
    if "$@" >> "$log" 2>&1; then
        return 0
    else
        status=$?
        tail -n 60 "$log" >&2
        return "$status"
    fi
}

detach_image() {
    local attempt
    /bin/sync
    for attempt in 1 2 3 4; do
        if /usr/bin/hdiutil detach "$mountpoint" >> "$log" 2>&1; then
            mounted=0
            return 0
        fi
        if [[ "$attempt" != 4 ]]; then
            printf 'Waiting for temporary image to close (attempt %s/4)...\n' "$attempt"
            sleep "$attempt"
        fi
    done
    printf '\nOpen-file diagnostics for the private mount point:\n' >> "$log"
    /usr/sbin/lsof -nP +D "$mountpoint" >> "$log" 2>&1 || true
    /usr/sbin/diskutil info "$mountpoint" >> "$log" 2>&1 || true
    tail -n 80 "$log" >&2
    return 1
}

echo '1/6 Verify the existing app.'
run /usr/bin/codesign --verify --deep --strict --verbose=2 "$app"
app_kb="$(/usr/bin/du -sk "$app" | /usr/bin/awk '{print $1}')"
size_mb=$((app_kb * 3 / 2 / 1024 + 64))
echo '2/6 Create and privately mount an empty writable image.'
run /usr/bin/hdiutil create -size "${size_mb}m" -fs HFS+ \
    -volname 'WINGS Desktop Preview' -type UDIF "$working"
# Mark before attaching so cleanup also handles a partially successful attach.
mounted=1
run /usr/bin/hdiutil attach -nobrowse -noautoopen -owners on \
    -mountpoint "$mountpoint" "$working"
# Apply only to this new image. No system-wide indexing or security changes.
touch "$mountpoint/.metadata_never_index"
echo '3/6 Copy the app and verify its signature inside the image.'
run /usr/bin/ditto "$app" "$mountpoint/WINGS.app"
ln -s /Applications "$mountpoint/Applications"
run /usr/bin/codesign --verify --deep --strict --verbose=2 "$mountpoint/WINGS.app"
echo '4/6 Unmount the writable image.'
detach_image
echo '5/6 Compress the unmounted image and verify its checksum.'
run /usr/bin/hdiutil convert "$working" -format UDZO -o "$pending"
run /usr/bin/hdiutil verify "$pending"
echo '6/6 Mount the final image read-only and verify the packaged app.'
mkdir -p "$mountpoint"
mounted=1
run /usr/bin/hdiutil attach -readonly -nobrowse -noautoopen \
    -mountpoint "$mountpoint" "$pending"
run /usr/bin/codesign --verify --deep --strict --verbose=2 "$mountpoint/WINGS.app"
[[ -L "$mountpoint/Applications" && "$(readlink "$mountpoint/Applications")" == /Applications ]] || {
    echo 'Packaged Applications shortcut is missing or incorrect.' >&2
    exit 1
}
detach_image
[[ ! -e "$final" ]] || { echo 'Output appeared during packaging; stopping.' >&2; exit 1; }
/bin/mv "$pending" "$final"
/usr/bin/shasum -a 256 "$final" > "$destination/SHA256SUMS.txt"
printf '\nPASS: DMG checksum and packaged app signature verified.\nCreated: %s\n' "$final"

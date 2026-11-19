#!/bin/bash
# Run on macOS after package.py, or on a downloaded preview bundle.
# Build a universal launcher using the osascript host, then sign and package it.
set -euo pipefail
echo 'WINGS macOS builder: stdin launcher with verified DMG packaging'
root="$(cd "$(dirname "$0")" && pwd -P)"
preview="${1:?Usage: build-macos.sh /path/to/WINGS.app output-directory}"
destination="${2:?Output directory required}"
[[ "$(uname -s)" == Darwin ]] || { echo 'This build needs macOS.' >&2; exit 1; }
[[ -f "$preview/Contents/Resources/WINGS.applescript" ]] || { echo 'Missing WINGS.applescript in input bundle.' >&2; exit 1; }
[[ -f "$preview/Contents/Resources/WINGS.icns" ]] || { echo 'Missing WINGS.icns in input bundle.' >&2; exit 1; }
if [[ -n "${WINGS_NOTARY_PROFILE:-}" && -z "${WINGS_SIGN_IDENTITY:-}" ]]; then
    echo 'Notarization requires WINGS_SIGN_IDENTITY.' >&2
    exit 1
fi
/usr/bin/xcrun --find clang >/dev/null
mkdir -p "$destination"
destination="$(cd "$destination" && pwd -P)"
app="$destination/WINGS.app"
[[ ! -e "$app" ]] || { echo 'Choose an empty output directory.' >&2; exit 1; }
[[ ! -e "$destination/WINGS-Desktop-Preview.dmg" ]] || { echo 'Output DMG already exists.' >&2; exit 1; }
scratch="$(mktemp -d "${TMPDIR:-/tmp}/wings-build.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

# Keep the standard app bundle layout, but replace the applet host below.
/usr/bin/osacompile -o "$app" "$preview/Contents/Resources/WINGS.applescript"
/usr/bin/ditto "$preview/Contents/Resources" "$app/Contents/Resources"
# Never execute a writable compiled script inside a signed bundle: its saved
# state can change after launch. osacompile above validates the source syntax.
/bin/rm -f "$app/Contents/Resources/Scripts/main.scpt"

cat > "$scratch/launcher.c" <<'WINGS_LAUNCHER_C'
#include <mach-o/dyld.h>
#include <stdint.h>
#include <limits.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char executable[PATH_MAX], resolved[PATH_MAX];
    char resources[PATH_MAX], script[PATH_MAX];
    uint32_t size = sizeof executable;
    if (_NSGetExecutablePath(executable, &size) != 0) {
        fputs("WINGS: executable path is too long.\n", stderr);
        return 1;
    }
    if (realpath(executable, resolved) == NULL) {
        perror("WINGS: resolve executable");
        return 1;
    }
    char *slash = strrchr(resolved, '/');
    if (slash == NULL) return 1;
    *slash = '\0';
    slash = strrchr(resolved, '/');
    if (slash == NULL || strcmp(slash, "/MacOS") != 0) {
        fputs("WINGS: launcher must be inside Contents/MacOS.\n", stderr);
        return 1;
    }
    *slash = '\0';
    if (snprintf(resources, sizeof resources, "%s/Resources", resolved) >= (int)sizeof resources ||
        snprintf(script, sizeof script, "%s/WINGS.applescript", resources) >= (int)sizeof script) {
        fputs("WINGS: resource path is too long.\n", stderr);
        return 1;
    }
    if (access(script, R_OK) != 0) {
        perror("WINGS: read bundled script");
        return 1;
    }
    if (setenv("WINGS_APP_RESOURCES", resources, 1) != 0) {
        perror("WINGS: set resource directory");
        return 1;
    }
    if (argc == 2 && strcmp(argv[1], "--wings-launcher-check") == 0) {
        printf("WINGS launcher resources: %s\n", resources);
        return 0;
    }
    /* Read the source as a stream: osascript gets no script filename to save
       back into the signed bundle. No shell expansion or temporary script. */
    int source = open(script, O_RDONLY);
    if (source < 0) {
        perror("WINGS: open script source");
        return 1;
    }
    if (dup2(source, STDIN_FILENO) < 0) {
        perror("WINGS: connect script input");
        close(source);
        return 1;
    }
    if (source != STDIN_FILENO) close(source);
    /* exec preserves the process lifetime and osascript's exit status. */
    execl("/usr/bin/osascript", "osascript", "-", (char *)NULL);
    perror("WINGS: launch osascript");
    return 1;
}
WINGS_LAUNCHER_C

/usr/bin/xcrun clang -std=c11 -O2 -Wall -Wextra -Werror \
    -arch arm64 -arch x86_64 -mmacosx-version-min=13.0 \
    "$scratch/launcher.c" -o "$scratch/WINGS"
# Remove the inherited executable so no stale applet signature is retained.
/bin/rm "$app/Contents/MacOS/applet"
/bin/mv "$scratch/WINGS" "$app/Contents/MacOS/WINGS"
/bin/chmod 755 "$app/Contents/MacOS/WINGS"

plist="$app/Contents/Info.plist"
put_string() {
    /usr/libexec/PlistBuddy -c "Set :$1 $2" "$plist" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :$1 string $2" "$plist"
}
put_string CFBundleIdentifier org.zoophy.wings.desktop.preview
put_string CFBundleName WINGS
put_string CFBundleDisplayName WINGS
put_string CFBundleExecutable WINGS
put_string CFBundleShortVersionString 0.1.12
put_string CFBundleVersion 13
put_string LSMinimumSystemVersion 13.0
put_string CFBundleIconFile WINGS.icns
put_string NSAppleEventsUsageDescription 'WINGS opens your browser and local workspace.'
if /usr/libexec/PlistBuddy -c "Print :CFBundleIconName" "$plist" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$plist"
fi
/usr/bin/plutil -lint "$plist"
architectures="$(/usr/bin/lipo -archs "$app/Contents/MacOS/WINGS")"
printf 'Launcher architectures: %s\n' "$architectures"
for required_arch in arm64 x86_64; do
    case " $architectures " in
        *" $required_arch "*) ;;
        *) echo "Launcher is missing architecture: $required_arch" >&2; exit 1 ;;
    esac
done

# Sign AFTER every bundle mutation. Preview builds also need a valid signature.
if [[ -n "${WINGS_SIGN_IDENTITY:-}" ]]; then
    /usr/bin/codesign --force --options runtime --timestamp --sign "$WINGS_SIGN_IDENTITY" "$app"
else
    /usr/bin/codesign --force --sign - "$app"
fi
/usr/bin/codesign --verify --deep --strict --verbose=2 "$app"
"$app/Contents/MacOS/WINGS" --wings-launcher-check

if [[ "${WINGS_BUILD_APP_ONLY:-0}" == 1 ]]; then
    printf 'Built app for interactive testing: %s\n' "$app"
    exit 0
fi

# Use the same private-mount packaging path validated on a downloaded app.
/bin/bash "$root/package-wings-dmg.sh" "$app" "$destination"
if [[ -n "${WINGS_NOTARY_PROFILE:-}" ]]; then
    /usr/bin/xcrun notarytool submit "$destination/WINGS-Desktop-Preview.dmg" --keychain-profile "$WINGS_NOTARY_PROFILE" --wait
    /usr/bin/xcrun stapler staple "$destination/WINGS-Desktop-Preview.dmg"
    /usr/bin/xcrun stapler validate "$destination/WINGS-Desktop-Preview.dmg"
    /usr/bin/hdiutil verify "$destination/WINGS-Desktop-Preview.dmg"
fi
# Stapling can change the DMG; publish the checksum of the final bytes.
/usr/bin/shasum -a 256 "$destination/WINGS-Desktop-Preview.dmg" > "$destination/SHA256SUMS.txt"
printf 'Built %s\n' "$destination/WINGS-Desktop-Preview.dmg"

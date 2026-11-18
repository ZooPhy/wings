#!/bin/bash
# Run on macOS after package.py, or on a downloaded preview bundle.
# Compiles a native AppleScript applet and optionally signs/notarizes a DMG.
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd -P)"
preview="${1:?Usage: build-macos.sh /path/to/WINGS.app output-directory}"
destination="${2:?Output directory required}"
[[ "$(uname -s)" == Darwin ]] || { echo 'This build needs macOS.' >&2; exit 1; }
mkdir -p "$destination"
destination="$(cd "$destination" && pwd -P)"
[[ ! -e "$destination/WINGS.app" ]] || { echo 'Choose an empty output directory.' >&2; exit 1; }
/usr/bin/osacompile -o "$destination/WINGS.app" "$preview/Contents/Resources/WINGS.applescript"
/usr/bin/ditto "$preview/Contents/Resources" "$destination/WINGS.app/Contents/Resources"
plist="$destination/WINGS.app/Contents/Info.plist"
put_string() {
    /usr/libexec/PlistBuddy -c "Set :$1 $2" "$plist" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :$1 string $2" "$plist"
}
put_string CFBundleIdentifier org.zoophy.wings.desktop.preview
put_string CFBundleName WINGS
put_string CFBundleShortVersionString 0.1.12
put_string CFBundleVersion 13
put_string CFBundleIconFile WINGS.icns
if [[ -n "${WINGS_SIGN_IDENTITY:-}" ]]; then
    /usr/bin/codesign --force --options runtime --timestamp --sign "$WINGS_SIGN_IDENTITY" "$destination/WINGS.app"
    /usr/bin/codesign --verify --strict --verbose=2 "$destination/WINGS.app"
fi
stage="$(mktemp -d "$destination/.dmg.XXXXXX")"
trap 'rm -rf "$stage"' EXIT
/usr/bin/ditto "$destination/WINGS.app" "$stage/WINGS.app"
ln -s /Applications "$stage/Applications"
/usr/bin/hdiutil create -volname 'WINGS Desktop Preview' -srcfolder "$stage" -ov -format UDZO "$destination/WINGS-Desktop-Preview.dmg"
if [[ -n "${WINGS_NOTARY_PROFILE:-}" ]]; then
    [[ -n "${WINGS_SIGN_IDENTITY:-}" ]] || { echo 'Notarization requires WINGS_SIGN_IDENTITY.' >&2; exit 1; }
    xcrun notarytool submit "$destination/WINGS-Desktop-Preview.dmg" --keychain-profile "$WINGS_NOTARY_PROFILE" --wait
    xcrun stapler staple "$destination/WINGS-Desktop-Preview.dmg"
    xcrun stapler validate "$destination/WINGS-Desktop-Preview.dmg"
fi
printf 'Built %s\n' "$destination/WINGS-Desktop-Preview.dmg"

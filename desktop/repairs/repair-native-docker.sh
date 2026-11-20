#!/bin/bash
# Run in Mac Terminal. Tests the official ARM64 client inside WINGS before
# making any change. --apply additionally backs up and replaces the live CLI.
set -euo pipefail
case "${1:-}" in
    ''|--apply) repair_mode="${1:-}";;
    *) echo 'Usage: bash repair-native-docker.sh [--apply]' >&2; exit 2;;
esac
root="$(cd "$(dirname "$0")" && pwd -P)"
container='wings-desktop-d078904931383a3f'
image='docker:28.3.3-cli@sha256:0135662b510037ea581d99c2e5929c5e01185139c0b86986a418bd4da0b98a44'
[[ -f "$root/native_docker_cli.py" ]] || { echo 'Keep the repair files together.' >&2; exit 1; }
[[ "$(docker inspect --format '{{index .Config.Labels "org.wings.desktop.workspace"}}' "$container")" == d078904931383a3f ]] || {
    echo 'The expected WINGS workspace container was not found.' >&2; exit 1;
}
[[ "$(docker inspect --format '{{.State.Running}}' "$container")" == true ]] || {
    echo 'Open WINGS before running this repair.' >&2; exit 1;
}
case "$(docker info --format '{{.Architecture}}')" in
    arm64|aarch64) ;;
    *) echo 'This live repair is for an ARM64 Docker engine.' >&2; exit 1;;
esac
host_tmp="$(mktemp -d "${TMPDIR:-/tmp}/wings-native-cli.XXXXXX")"
container_tmp=''
cleanup() {
    rm -rf "$host_tmp"
    if [[ "$container_tmp" == /tmp/wings-native-cli.* ]]; then
        docker exec "$container" rm -rf "$container_tmp" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT
printf 'Extracting Docker CLI 28.3.3 for Linux ARM64…\n'
docker run --rm --platform linux/arm64 --entrypoint /bin/cat "$image" \
    /usr/local/bin/docker > "$host_tmp/docker-arm64"
[[ -s "$host_tmp/docker-arm64" ]] || { echo 'The extracted CLI is empty.' >&2; exit 1; }
container_tmp="$(docker exec "$container" mktemp -d /tmp/wings-native-cli.XXXXXX)"
[[ "$container_tmp" == /tmp/wings-native-cli.* ]] || exit 1
docker cp "$host_tmp/docker-arm64" "$container:$container_tmp/docker-arm64"
docker exec "$container" chmod 755 "$container_tmp/docker-arm64"
set -- --candidate "$container_tmp/docker-arm64"
if [[ "$repair_mode" == --apply ]]; then set -- "$@" --apply; fi
docker exec -i "$container" /opt/conda/bin/python - "$@" \
    < "$root/native_docker_cli.py"

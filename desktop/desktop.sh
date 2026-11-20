#!/bin/bash
# macOS /bin/bash 3.2 compatible. No host Python, Conda, or Node required.
set -euo pipefail
umask 077
RESOURCES="$(cd "$(dirname "$0")" && pwd -P)"
DOCKER="${WINGS_DOCKER_BIN:-}"
if [[ -n "$DOCKER" && ! -x "$DOCKER" ]]; then echo 'Configured Docker executable is unavailable.' >&2; exit 10; fi
if [[ -z "$DOCKER" ]]; then
    for candidate in /Applications/Docker.app/Contents/Resources/bin/docker "$HOME/Applications/Docker.app/Contents/Resources/bin/docker" "$HOME/.docker/bin/docker" /usr/local/bin/docker; do
        if [[ -x "$candidate" ]]; then DOCKER="$candidate"; break; fi
    done
fi
if [[ -z "$DOCKER" ]]; then DOCKER="$(command -v docker || true)"; fi
[[ -n "$DOCKER" ]] || { echo 'Install Docker Desktop, then reopen WINGS.' >&2; exit 10; }
# Finder/osascript do not load interactive shell startup files. Docker can be
# invoked by absolute path but still needs its credential helpers on PATH.
# Follow CLI symlinks so a user/system symlink also finds the app's helpers.
docker_cli_dir="$(cd "$(dirname "$DOCKER")" && pwd -P)"
docker_target="$DOCKER"
link_count=0
while [[ -L "$docker_target" ]]; do
    link_count=$((link_count + 1))
    [[ "$link_count" -le 40 ]] || { echo 'Docker executable has a symlink loop.' >&2; exit 10; }
    link="$(readlink "$docker_target")"
    case "$link" in
        /*) docker_target="$link";;
        *) docker_target="$(dirname "$docker_target")/$link";;
    esac
done
docker_helper_dir="$(cd "$(dirname "$docker_target")" && pwd -P)"
export PATH="$docker_helper_dir:$docker_cli_dir:/Applications/Docker.app/Contents/Resources/bin:$HOME/Applications/Docker.app/Contents/Resources/bin:$HOME/.docker/bin:${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"
# A remote Docker daemon cannot access the selected Mac workspace.
if [[ -n "${DOCKER_HOST:-}" && "${DOCKER_HOST}" != unix://* ]]; then
    echo 'WINGS requires a local Docker Desktop connection.' >&2; exit 11
fi
docker_cmd=("$DOCKER")
if [[ -n "${DOCKER_HOST:-}" ]]; then
    docker_cmd+=(--host "$DOCKER_HOST")
    unset DOCKER_CONTEXT
else
    if "$DOCKER" context inspect desktop-linux >/dev/null 2>&1; then
        docker_cmd+=(--context desktop-linux)
    fi
    endpoint="$("${docker_cmd[@]}" context inspect --format '{{.Endpoints.docker.Host}}')"
    [[ "$endpoint" == unix://* ]] || { echo 'Select a local Docker Desktop context.' >&2; exit 11; }
fi
d() { "${docker_cmd[@]}" "$@"; }
action="${1:-doctor}"
if [[ "$action" == doctor ]]; then d info --format '{{.OSType}} {{.Architecture}}'; exit; fi
workspace="${2:?Workspace required}"
case "$workspace" in /*) ;; *) echo 'Use an absolute workspace path.' >&2; exit 12;; esac
case "$workspace" in *','*|*':'*|*$'\n'*|*$'\r'*) echo 'Choose a folder without commas, colons, or line breaks.' >&2; exit 12;; esac
mkdir -p "$workspace"
workspace="$(cd "$workspace" && pwd -P)"
[[ "$workspace" != / && "$workspace" != "$HOME" ]] || { echo 'Choose a dedicated WINGS workspace.' >&2; exit 12; }
state="$workspace/.desktop"
mkdir -p "$state" "$workspace/logs" "$workspace/cache" "$workspace/runs"
workspace_id="$(printf '%s' "$workspace" | shasum -a 256 | cut -c 1-16)"
container="wings-desktop-$workspace_id"
owned() { [[ "$(d inspect --format '{{index .Config.Labels "org.wings.desktop.workspace"}}' "$container" 2>/dev/null)" == "$workspace_id" ]]; }
running() { [[ "$(d inspect --format '{{.State.Running}}' "$container" 2>/dev/null)" == true ]]; }
stage() { printf '%s\n' "$1" > "$state/progress"; printf '%s\n' "$1"; }
url() {
    owned && running || { echo 'WINGS is not running.' >&2; return 1; }
    port="$(d port "$container" 8766/tcp | sed -n 's/^127\.0\.0\.1://p')"
    [[ "$port" =~ ^[0-9]+$ ]] || { echo 'Unexpected published port.' >&2; return 1; }
    token="$(cat "$state/session")"
    [[ "$token" =~ ^[0-9a-f]{64}$ ]] || return 1
    printf 'http://127.0.0.1:%s/desktop/session?token=%s\n' "$port" "$token"
}
case "$action" in
url) url; exit;;
ollama-check)
    owned && running || { echo 'Open WINGS first and wait until setup is ready, then return to Settings → Check Ollama connection.' >&2; exit 21; }
    installed_source="$(d inspect --format '{{index .Config.Labels "org.wings.desktop.source"}}' "$container")"
    [[ "$installed_source" == "$(cat "$RESOURCES/source.sha256")" ]] || { echo 'An earlier WINGS service is running. Finish its jobs, use Settings → Stop WINGS service, then open this version before checking Ollama.' >&2; exit 17; }
    # Test from the same network namespace used by analysis jobs, not the Mac shell.
    d exec -i "$container" /opt/conda/bin/python - --workspace "$workspace" < "$RESOURCES/wings_ollama.py"
    exit;;
diagnostics)
    report="$workspace/logs/desktop-diagnostics.txt"
    { printf 'WINGS desktop developer preview 0.1.14\n'; sw_vers; uname -m
      d version --format 'Docker client {{.Client.Version}}; server {{.Server.Version}}'
      d info --format 'Engine {{.OSType}}/{{.Architecture}}; CPUs {{.NCPU}}; memory {{.MemTotal}}'
      if owned; then d inspect --format 'Container state: {{.State.Status}}; image: {{.Image}}' "$container"; fi
      printf 'Source: '; cat "$RESOURCES/source.sha256"
    } > "$report" 2>&1
    printf '%s\n' "$report"; exit;;
stop)
    if owned; then d stop --time 30 "$container"; fi
    exit;;
launch) ;;
*) echo 'Unknown desktop command.' >&2; exit 2;;
esac

if ! mkdir "$state/setup.lock" 2>/dev/null; then
    prior="$(cat "$state/setup.lock/pid" 2>/dev/null || true)"
    if [[ "$prior" =~ ^[0-9]+$ ]] && kill -0 "$prior" 2>/dev/null; then
        echo 'WINGS setup is already running. Reopen it after setup finishes.' >&2; exit 13
    fi
    # Remove only the stale lock that this app owns, never workspace content.
    rm -f "$state/setup.lock/pid"
    rmdir "$state/setup.lock"
    mkdir "$state/setup.lock"
fi
printf '%s\n' "$$" > "$state/setup.lock/pid"
rm -f "$state/launch.done"
finish() {
    status=$?
    trap - EXIT
    printf '%s\n' "$status" > "$state/launch.done"
    rm -f "$state/setup.lock/pid" "$state/container.env"
    rmdir "$state/setup.lock" 2>/dev/null || true
    exit "$status"
}
trap finish EXIT
stage 'Checking Docker Desktop…'
[[ "$(d info --format '{{.OSType}}')" == linux ]] || { echo 'Docker must run Linux containers.' >&2; exit 14; }
email="${3:-}"
if [[ -n "$email" ]]; then
    [[ "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo 'Enter a valid contact email address.' >&2; exit 15; }
    printf '%s\n' "$email" > "$state/ncbi-email"
fi
# Expose Mac input folders at their original paths; workspace remains writable.
host_home="$(cd "$HOME" && pwd -P)"
input_roots=("$host_home")
[[ ! -d /Volumes ]] || input_roots+=(/Volumes)
if [[ -f "$state/shared-folders" ]]; then
    while IFS= read -r input_root || [[ -n "$input_root" ]]; do
        [[ -z "$input_root" ]] || input_roots+=("$input_root")
    done < "$state/shared-folders"
fi
input_mounts=()
browse_roots=""
for input_root in "${input_roots[@]}"; do
    case "$input_root" in /*) ;; *) echo 'A shared folder needs an absolute Mac path.' >&2; exit 12;; esac
    case "$input_root" in /|*','*|*':'*|*$'\n'*|*$'\r'*) echo 'Choose shared folders without commas, colons or line breaks; do not share the filesystem root.' >&2; exit 12;; esac
    [[ -d "$input_root" ]] || { echo "A shared folder is unavailable: $input_root. Reconnect the drive or remove it in Settings." >&2; exit 12; }
    input_root="$(cd "$input_root" && pwd -P)"
    case "$input_root" in /|*','*|*':'*|*$'\n'*|*$'\r'*) echo 'The resolved shared-folder path cannot be mounted.' >&2; exit 12;; esac
    case ":$browse_roots:" in *":$input_root:"*) continue;; esac
    browse_roots="${browse_roots:+$browse_roots:}$input_root"
    case "$input_root" in "$workspace"|"$workspace"/*) ;; *) input_mounts+=(--mount "type=bind,source=$input_root,target=$input_root,readonly");; esac
done
folders_hash="$(printf '%s' "$browse_roots" | shasum -a 256 | cut -d ' ' -f 1)"
source_hash="$(cat "$RESOURCES/source.sha256")"
[[ "$source_hash" =~ ^[0-9a-f]{64}$ ]] || { echo 'Invalid application manifest.' >&2; exit 16; }
observed="$(shasum -a 256 "$RESOURCES/source.tar.gz" | awk '{print $1}')"
[[ "$observed" == "$source_hash" ]] || { echo 'Application source archive is damaged. Download it again.' >&2; exit 16; }
runtime_hash="$(cat "$RESOURCES/runtime.sha256")"
[[ "$runtime_hash" =~ ^[0-9a-f]{64}$ ]] || exit 16
image="wings-desktop-runtime:${runtime_hash:0:16}"
repo="$workspace/releases/$source_hash/app"
if owned && running; then
    old="$(d inspect --format '{{index .Config.Labels "org.wings.desktop.source"}}' "$container")"
    old_runtime="$(d inspect --format '{{index .Config.Labels "org.wings.desktop.runtime"}}' "$container")"
    [[ "$old" == "$source_hash" && "$old_runtime" == "$runtime_hash" ]] || { echo 'An earlier WINGS version is running. Finish or stop jobs in its browser, then use Settings → Stop WINGS service before opening this version.' >&2; exit 17; }
    old_folders="$(d inspect --format '{{index .Config.Labels "org.wings.desktop.folders"}}' "$container")"
    [[ "$old_folders" == "$folders_hash" ]] || { echo 'Shared folders changed. Finish active jobs, then use Settings → Stop WINGS service and reopen WINGS.' >&2; exit 17; }
    stage 'WINGS is already running.' 
    exit 0
fi
if d inspect "$container" >/dev/null 2>&1; then
    owned || { echo 'Container name conflict. No container was changed.' >&2; exit 17; }
    d rm "$container" >/dev/null
fi
stage 'Installing the bundled workflow…'
if [[ ! -d "$repo" ]]; then
    mkdir -p "$workspace/releases/$source_hash"
    staging="$(mktemp -d "$workspace/releases/$source_hash/.install.XXXXXX")"
    tar -xzf "$RESOURCES/source.tar.gz" -C "$staging"
    mv "$staging" "$repo"
fi
# Shared scientific resources and rule environments survive application updates.
for name in flu_db vadr-models phylodynamics; do
    mkdir -p "$workspace/cache/$name"
    if [[ ! -e "$repo/resources/$name" ]]; then ln -s "$workspace/cache/$name" "$repo/resources/$name"; fi
done
# Reuse the already-verified archive from an older preview after a setup failure.
# The builder verifies its checksum again before use.
reference_archive="$workspace/cache/fluA_reference.fasta.zip"
if [[ ! -e "$reference_archive" ]]; then
    for previous_archive in "$workspace"/releases/*/app/resources/fluA_reference.fasta.zip; do
        if [[ -f "$previous_archive" ]]; then
            cp "$previous_archive" "$reference_archive"
            break
        fi
    done
fi
mkdir -p "$workspace/cache/snakemake"
if [[ ! -e "$repo/.snakemake" ]]; then ln -s "$workspace/cache/snakemake" "$repo/.snakemake"; fi
stage 'Checking the analysis runtime…'
if ! d image inspect "$image" >/dev/null 2>&1; then
    stage 'Preparing the analysis runtime. The first download may take a while…'
    d build --platform linux/amd64 --label org.wings.desktop.runtime="$runtime_hash" \
        -t "$image" "$RESOURCES/runtime"
fi
[[ "$(d image inspect --format '{{index .Config.Labels "org.wings.desktop.runtime"}}' "$image")" == "$runtime_hash" ]] || { echo 'Runtime image identity mismatch.' >&2; exit 18; }
common=(--platform linux/amd64 "${input_mounts[@]}" --env "WINGS_HOST_HOME=$host_home" --env "WINGS_BROWSE_ROOTS=$browse_roots" --mount "type=bind,source=$workspace,target=$workspace" \
    --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
    --env "WINGS_REFERENCE_ARCHIVE=$reference_archive" \
    --workdir "$repo")
stage 'Verifying workflow source…'
d run --rm "${common[@]}" "$image" verify --repo "$repo" --workspace "$workspace"
stage 'Preparing BLAST references, VADR models, and assembly tools…'
d run --rm "${common[@]}" "$image" prepare --repo "$repo" --workspace "$workspace"
stage 'Preparing analysis tool images…'
# Image inspection and downloads use the native Mac CLI. The controller's
# emulated Linux Docker CLI is still used by analysis jobs, not by this setup.
. "$RESOURCES/prepare-images.sh"
wings_prepare_images
stage 'Starting WINGS…'
token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
printf '%s\n' "$token" > "$state/session"
printf 'WINGS_DESKTOP_TOKEN=%s\n' "$token" > "$state/container.env"
d run -d --init --name "$container" "${common[@]}" \
    --publish 127.0.0.1::8766 --env-file "$state/container.env" \
    --label org.wings.desktop.workspace="$workspace_id" \
    --label org.wings.desktop.folders="$folders_hash" \
    --label org.wings.desktop.source="$source_hash" \
    --label org.wings.desktop.runtime="$runtime_hash" \
    --log-opt max-size=10m --log-opt max-file=3 \
    "$image" serve --repo "$repo" --workspace "$workspace" >/dev/null
port="$(d port "$container" 8766/tcp | sed -n 's/^127\.0\.0\.1://p')"
[[ "$port" =~ ^[0-9]+$ ]] || exit 19
ready=false
for ((i=0;i<90;i++)); do
    if curl --silent --fail --max-time 2 "http://127.0.0.1:$port/desktop/health" >/dev/null; then ready=true; break; fi
    running || break
    sleep 1
done
if [[ "$ready" != true ]]; then
    d logs --tail 100 "$container" >&2
    echo 'The service did not become ready. See setup.log.' >&2
    exit 20
fi
stage 'WINGS is ready. Closing the app will leave analyses running.'

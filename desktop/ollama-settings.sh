#!/bin/bash
# Configure before or after setup using built-in Mac tools; no host Python.
set -euo pipefail
umask 077
workspace="${1:?Workspace required}"
url="${2:?Ollama address required}"
model="${3:?Model name required}"
pattern='^http://(localhost|127\.0\.0\.1|\[::1\]|host\.docker\.internal)(:([0-9]{1,5}))?(/api/chat|/)?$'
[[ "$workspace" == /* && "$workspace" != / ]] || { echo 'Use your WINGS workspace.' >&2; exit 2; }
[[ "$url" =~ $pattern ]] || { echo 'Use a local address such as http://localhost:11434.' >&2; exit 2; }
port="${BASH_REMATCH[3]:-11434}"
port=$((10#$port))
[[ "$port" -ge 1 && "$port" -le 65535 ]] || { echo 'Ollama port must be between 1 and 65535.' >&2; exit 2; }
[[ "${#model}" -le 200 && "$model" =~ ^[A-Za-z0-9][A-Za-z0-9._:/-]*$ ]] || { echo 'Enter the model name exactly as shown in Ollama.' >&2; exit 2; }
[[ ! -L "$workspace/.desktop" && ! -L "$workspace/.desktop/ollama.conf" ]] || { echo 'Ollama settings must be stored directly in this workspace.' >&2; exit 2; }
mkdir -p "$workspace/.desktop"
temporary="$(mktemp "$workspace/.desktop/.ollama.XXXXXX")"
trap 'rm -f "$temporary"' EXIT
printf '%s\n%s\n' "$url" "$model" > "$temporary"
chmod 600 "$temporary"
mv -f "$temporary" "$workspace/.desktop/ollama.conf"
printf 'Ollama settings saved. Refresh the WINGS browser page. New briefings will use these settings; existing jobs keep their settings.\n'

#!/bin/bash
# Sourced by setup-session.sh; Bash 3.2 and built-in macOS utilities only.
# The browser receives fixed status codes and numbers, never raw logs or keys.
progress_init() {
    local log_name
    log_name="${log_path##*/}"
    # Only coordinator-generated names enter HTML. The parent path can contain
    # spaces, Unicode or URL-special characters; it is never interpolated.
    [[ "$log_name" =~ ^setup-[A-Za-z0-9-]+\.log$ ]] || {
        echo 'Unexpected setup log filename.' >&2; return 1;
    }
    progress_dir="$log_path.status"
    mkdir -p "$progress_dir"
    sed "s|@@WINGS_SETUP_LOG@@|../$log_name|g" "$resources/setup-progress.html" > "$progress_dir/index.html" || return 1
    cp "$resources/setup-progress.js" "$progress_dir/setup-progress.js"
    cp "$resources/wings_logo.jpg" "$progress_dir/wings_logo.jpg"
    progress_started="$(date +%s)"
    progress_changed="$progress_started"
    progress_bytes=0
    progress_phase=1
    progress_code=docker
    progress_error=generic
    progress_status=running
    progress_opened=false
    progress_tick
}

progress_tick() {
    local now bytes parsed phase code error
    now="$(date +%s)"
    bytes="$(wc -c < "$log_path" | tr -d '[:space:]')"
    if [[ "$bytes" != "$progress_bytes" ]]; then
        progress_changed="$now"
        progress_bytes="$bytes"
    fi
    # Bounded tail: do not repeatedly load large Docker build logs into memory.
    parsed="$(tail -c 65536 "$log_path" | tr '\r' '\n' | awk '
      function step(p, c) { if(p >= phase) { phase=p; code=c } }
      /^Checking Docker Desktop/ {step(1,"docker")}
      /^Installing the bundled workflow/ {step(2,"workflow")}
      /^Checking the analysis runtime/ {step(3,"runtimecheck")}
      /^Preparing the analysis runtime/ {step(3,"runtime")}
      /^Verifying workflow source/ {step(3,"verify")}
      /^Checking Docker access from the analysis runtime/ {step(3,"runtimecheck")}
      /^Preparing BLAST references/ {step(4,"references")}
      /^Attempting to download fluA/ {step(4,"download")}
      /^Extracting influenza reference/ {step(4,"extract")}
      /^Building BLAST database/ {step(4,"build")}
      /^Verifying the new BLAST database/ {step(4,"verifydb")}
      /^Installing the verified BLAST database/ {step(4,"installdb")}
      /^BLAST database successfully created/ {step(4,"refsready")}
      /^Downloading VADR influenza models/ {step(5,"modelsdownload")}
      /^VADR influenza models already installed/ {step(5,"modelscached")}
      /^VADR model installation complete/ {step(5,"modelsready")}
      /^Preparing analysis tool images/ {step(5,"tools")}
      /: Pulling from (cdcgov\/irma|staphb\/vadr)/ {step(5,"tools")}
      /^Starting WINGS/ {step(6,"start")}
      /^WINGS is ready\.|^WINGS is already running\./ {step(6,"opening")}
      /An earlier WINGS version is running/ {error="older"}
      /Shared folders changed/ {error="folders"}
      /A shared folder is unavailable/ {error="missingfolder"}
      /[Cc]hecksum mismatch|archive is damaged|Source checksum mismatch|SHA-256 verification failed/ {error="checksum"}
      /[Nn]o space left on device/ {error="disk"}
      END {printf "%d %s %s\n",phase,code ? code : "none",error ? error : "generic"}
    ')"
    read -r phase code error <<< "$parsed"
    if [[ "$phase" =~ ^[1-6]$ && "$phase" -ge "$progress_phase" ]]; then
        progress_phase="$phase"
        progress_code="$code"
    fi
    [[ "$error" == generic ]] || progress_error="$error"
    # All interpolated strings are controlled enums above or in the coordinator.
    printf 'window.WINGSSetup.update({"phase":%s,"code":"%s","status":"%s","error":"%s","started":%s,"heartbeat":%s,"lastOutput":%s,"browserOpened":%s});\n' \
        "$progress_phase" "$progress_code" "$progress_status" "$progress_error" \
        "$progress_started" "$now" "$progress_changed" "$progress_opened" > "$progress_dir/state.js.tmp"
    mv -f "$progress_dir/state.js.tmp" "$progress_dir/state.js"
}

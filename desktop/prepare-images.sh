#!/bin/bash
# Sourced by desktop.sh. Uses its native Docker CLI, selected context and PATH.
# Bash 3.2 compatible; no Python or Conda installation is needed on the Mac.

wings_image_record() {
    d image inspect --platform linux/amd64 --format \
        '{{.Os}}/{{.Architecture}}|{{.Id}}|{{range .RepoDigests}}{{.}} {{end}}' "$1"
}

wings_amd64_record() {
    [[ "$1" == linux/amd64\|sha256:*\|* ]]
}

wings_prepare_images() {
    local irma_tag irma_digest irma_index irma_source candidate record source_id target_record
    irma_tag='ghcr.io/cdcgov/irma:v1.3.5'
    # The linux/amd64 manifest in CDC's v1.3.5 index, verified 2026-11-20.
    # Pin the platform manifest, not the multi-platform index or an attestation.
    irma_digest='sha256:96357063a678fd5887598b093a53373ae286a2eb0155520feae8b72904bcdda8'
    irma_index='sha256:cda47ea17971ee02195160fccbc76b4b97a8a0115c3f0c322b00d195b29e4785'
    irma_source="docker.io/cdcgov/irma@$irma_digest"
    source_id=''
    for candidate in "$irma_source" "$irma_tag" docker.io/cdcgov/irma:v1.3.5; do
        record="$(wings_image_record "$candidate" 2>/dev/null)" || continue
        wings_amd64_record "$record" || continue
        # A locally retagged unrelated image must not count as the official cache.
        case " ${record##*|} " in
            *" cdcgov/irma@$irma_digest "*|*" docker.io/cdcgov/irma@$irma_digest "*|*" ghcr.io/cdcgov/irma@$irma_digest "*|\
            *" cdcgov/irma@$irma_index "*|*" docker.io/cdcgov/irma@$irma_index "*|*" ghcr.io/cdcgov/irma@$irma_index "*)
                source_id="${record#*|}"; source_id="${source_id%%|*}"; break;;
        esac
    done
    if [[ -z "$source_id" ]]; then
        printf 'Downloading IRMA v1.3.5 (linux/amd64) from CDC on Docker Hub…\n'
        d pull --platform linux/amd64 "$irma_source" || return 1
        record="$(wings_image_record "$irma_source")" || return 1
        wings_amd64_record "$record" || { echo 'IRMA image is not linux/amd64.' >&2; return 1; }
        source_id="${record#*|}"; source_id="${source_id%%|*}"
    else
        printf 'Reusing verified IRMA v1.3.5 (linux/amd64).\n'
    fi
    # Preserve the workflow's existing image name. Tag the verified local ID
    # and check that the alias resolves to the same image for linux/amd64.
    target_record="$(wings_image_record "$irma_tag" 2>/dev/null)" || target_record=''
    if [[ "$target_record" != "linux/amd64|$source_id|"* ]]; then
        d tag "$source_id" "$irma_tag" || return 1
    fi
    target_record="$(wings_image_record "$irma_tag")" || return 1
    [[ "$target_record" == "linux/amd64|$source_id|"* ]] || {
        echo 'IRMA workflow image does not match the verified AMD64 image.' >&2; return 1;
    }

    candidate='staphb/vadr:1.7'
    record="$(wings_image_record "$candidate" 2>/dev/null)" || record=''
    if wings_amd64_record "$record"; then
        printf 'Reusing VADR 1.7 (linux/amd64).\n'
    else
        printf 'Downloading VADR 1.7 (linux/amd64)…\n'
        d pull --platform linux/amd64 "$candidate" || return 1
        record="$(wings_image_record "$candidate")" || return 1
        wings_amd64_record "$record" || { echo 'VADR image is not linux/amd64.' >&2; return 1; }
    fi
}

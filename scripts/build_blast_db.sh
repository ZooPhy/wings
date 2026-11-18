#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

RESOURCE_DIR="${ROOT_DIR}/resources"
ZIP="${WINGS_REFERENCE_ARCHIVE:-${RESOURCE_DIR}/fluA_reference.fasta.zip}"
DB_DIR="${RESOURCE_DIR}/flu_db"
FASTA="${DB_DIR}/fluA_reference.fasta"
DB_PREFIX="${DB_DIR}/fluA_db"
TMP_DIR="${DB_DIR}/_extract_tmp"
MANIFEST="${DB_DIR}/database_manifest.tsv"

# The reference archive currently comes from the APGAP influenza pipeline release.
GITHUB_REPO="${GITHUB_REPO:-ZooPhy/apgap-influenza-pipeline}"
RELEASE_TAG="${RELEASE_TAG:-v0.1.0}"
ASSET_NAME="${ASSET_NAME:-fluA_reference.fasta.zip}"
ZIP_URL="${ZIP_URL:-https://github.com/${GITHUB_REPO}/releases/download/${RELEASE_TAG}/${ASSET_NAME}}"
BLAST_IMAGE="${BLAST_IMAGE:-ncbi/blast-static:2.17.0}"
BLAST_DB_VERSION="${BLAST_DB_VERSION:-4}"
DEFAULT_ARCHIVE_SHA256="36645a72b290f3043b67c7f43196b438da5defbca24c00c1a592ce92fa6ba0e6"
EXPECTED_ARCHIVE_SHA256="${EXPECTED_ARCHIVE_SHA256:-}"

mkdir -p "${RESOURCE_DIR}" "${DB_DIR}" "$(dirname "${ZIP}")"

sha256_file() {
    local file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "${file}" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "${file}" | awk '{print $1}'
    else
        echo "ERROR: sha256sum or shasum is required to record BLAST database provenance." >&2
        exit 1
    fi
}

if [[ ! -f "${ZIP}" ]]; then
    echo "Compressed reference not found locally: ${ZIP}"
    echo "Attempting to download ${ASSET_NAME} from ${GITHUB_REPO} (${RELEASE_TAG})"

    download_ok=false

    if command -v gh >/dev/null 2>&1; then
        echo "Trying GitHub CLI..."
        if gh release download "${RELEASE_TAG}" \
            --repo "${GITHUB_REPO}" \
            --pattern "${ASSET_NAME}" \
            --dir "$(dirname "${ZIP}")" \
            --clobber; then
            [[ -s "${ZIP}" ]] && download_ok=true
        else
            rm -f "${ZIP}"
        fi
    fi

    if [[ "${download_ok}" != true ]]; then
        echo "Trying direct download: ${ZIP_URL}"
        if curl -fL --retry 3 --retry-delay 2 -o "${ZIP}" "${ZIP_URL}"; then
            download_ok=true
        else
            rm -f "${ZIP}"
        fi
    fi

    if [[ "${download_ok}" != true ]]; then
        cat >&2 <<ERROR
ERROR: Unable to obtain ${ASSET_NAME}.

You can fix this by doing one of the following:
  - Authenticate GitHub CLI with: gh auth login
  - Place the archive manually at:
      ${ZIP}
  - Override the source URL:
      ZIP_URL='https://example.org/${ASSET_NAME}' ./scripts/build_blast_db.sh
  - Override the release source:
      GITHUB_REPO='owner/repository' RELEASE_TAG='vX.Y.Z' ./scripts/build_blast_db.sh
ERROR
        exit 1
    fi
fi

if [[ ! -s "${ZIP}" ]]; then
    echo "ERROR: Reference archive is missing or empty: ${ZIP}" >&2
    exit 1
fi

ARCHIVE_SHA256="$(sha256_file "${ZIP}")"

# Verify the pinned default reference archive. Custom reference sources may
# provide their own checksum with EXPECTED_ARCHIVE_SHA256.
if [[ -n "${EXPECTED_ARCHIVE_SHA256}" ]]; then
    EXPECTED_SHA256="${EXPECTED_ARCHIVE_SHA256}"
elif [[ "${GITHUB_REPO}" == "ZooPhy/apgap-influenza-pipeline" \
     && "${RELEASE_TAG}" == "v0.1.0" \
     && "${ASSET_NAME}" == "fluA_reference.fasta.zip" \
     && "${ZIP_URL}" == "https://github.com/ZooPhy/apgap-influenza-pipeline/releases/download/v0.1.0/fluA_reference.fasta.zip" ]]; then
    EXPECTED_SHA256="${DEFAULT_ARCHIVE_SHA256}"
else
    EXPECTED_SHA256=""
fi

if [[ -n "${EXPECTED_SHA256}" ]]; then
    if [[ "${ARCHIVE_SHA256}" != "${EXPECTED_SHA256}" ]]; then
        cat >&2 <<ERROR
ERROR: BLAST reference archive SHA-256 verification failed.

Archive:
  ${ZIP}

Expected:
  ${EXPECTED_SHA256}

Observed:
  ${ARCHIVE_SHA256}

The archive will not be used to build the BLAST database.
Remove or replace the archive and rerun the script.
ERROR
        exit 1
    fi

    echo "Reference archive SHA-256 verified:"
    echo "  ${ARCHIVE_SHA256}"
else
    echo "WARNING: No expected SHA-256 is configured for this custom reference source." >&2
    echo "         Archive SHA-256 will be recorded but cannot be independently verified." >&2
fi

echo "Extracting influenza reference..."
rm -rf "${TMP_DIR}"
mkdir -p "${TMP_DIR}"
unzip -oq "${ZIP}" -d "${TMP_DIR}"

FASTA_SRC="$(find "${TMP_DIR}" -type f \( -iname '*.fasta' -o -iname '*.fa' -o -iname '*.fna' \) | head -n 1 || true)"

if [[ -z "${FASTA_SRC}" ]]; then
    echo "ERROR: No FASTA file found inside ${ZIP}" >&2
    rm -rf "${TMP_DIR}"
    exit 1
fi

cp -f "${FASTA_SRC}" "${FASTA}"
FASTA_SHA256="$(sha256_file "${FASTA}")"

# Build into a unique, physically space-free directory. makeblastdb can reopen
# its output using an absolute path internally, even when -out is a basename.
# Keep any installed database intact until the replacement has been verified.
BUILD_DIR="$(mktemp -d /tmp/wings-blast.XXXXXXXX)"
cleanup_build() { rm -rf "${BUILD_DIR}" "${TMP_DIR}"; }
trap cleanup_build EXIT

BUILD_METHOD=""
MAKEBLASTDB_VERSION=""

build_with_local_blast() {
    echo "Building BLAST database version ${BLAST_DB_VERSION} with local makeblastdb..."
    BUILD_METHOD="local"
    MAKEBLASTDB_VERSION="$(makeblastdb -version 2>&1 | awk '/^makeblastdb:/{print; found=1} END{if(!found) print "unknown"}' | tr '\t' ' ')"
    # makeblastdb parses -in as a list and can split a quoted path at spaces.
    # Stage the actual bytes, not a symlink back to the space-containing path.
    echo "Staging FASTA input in the temporary build directory..."
    cp "${FASTA}" "${BUILD_DIR}/fluA_reference.fasta"
    makeblastdb \
        -in "${BUILD_DIR}/fluA_reference.fasta" \
        -dbtype nucl \
        -blastdb_version "${BLAST_DB_VERSION}" \
        -out "${BUILD_DIR}/fluA_db"
    echo "Verifying the new BLAST database..."
    blastdbcmd -db "${BUILD_DIR}/fluA_db" -info
}

build_with_docker() {
    echo "Building BLAST database version ${BLAST_DB_VERSION} with Docker..."
    BUILD_METHOD="docker"
    MAKEBLASTDB_VERSION="$(docker run --rm "${BLAST_IMAGE}" makeblastdb -version 2>&1 | awk '/^makeblastdb:/{print; found=1} END{if(!found) print "unknown"}' | tr '\t' ' ')"
    docker run --rm \
        -v "${DB_DIR}:/db" \
        -v "${BUILD_DIR}:/build" \
        -w /db \
        "${BLAST_IMAGE}" \
        makeblastdb \
            -in "/db/fluA_reference.fasta" \
            -dbtype nucl \
            -blastdb_version "${BLAST_DB_VERSION}" \
            -out "/build/fluA_db"
    echo "Verifying the new BLAST database..."
    docker run --rm -v "${BUILD_DIR}:/build" "${BLAST_IMAGE}" blastdbcmd -db /build/fluA_db -info
}

build_with_apptainer() {
    echo "Building BLAST database version ${BLAST_DB_VERSION} with Apptainer..."
    BUILD_METHOD="apptainer"
    MAKEBLASTDB_VERSION="$(apptainer exec "docker://${BLAST_IMAGE}" makeblastdb -version 2>&1 | awk '/^makeblastdb:/{print; found=1} END{if(!found) print "unknown"}' | tr '\t' ' ')"
    apptainer exec \
        --bind "${DB_DIR}:/db" \
        --bind "${BUILD_DIR}:/build" \
        "docker://${BLAST_IMAGE}" \
        makeblastdb \
            -in "/db/fluA_reference.fasta" \
            -dbtype nucl \
            -blastdb_version "${BLAST_DB_VERSION}" \
            -out "/build/fluA_db"
    echo "Verifying the new BLAST database..."
    apptainer exec --bind "${BUILD_DIR}:/build" "docker://${BLAST_IMAGE}" blastdbcmd -db /build/fluA_db -info
}

build_with_singularity() {
    echo "Building BLAST database version ${BLAST_DB_VERSION} with Singularity..."
    BUILD_METHOD="singularity"
    MAKEBLASTDB_VERSION="$(singularity exec "docker://${BLAST_IMAGE}" makeblastdb -version 2>&1 | awk '/^makeblastdb:/{print; found=1} END{if(!found) print "unknown"}' | tr '\t' ' ')"
    singularity exec \
        --bind "${DB_DIR}:/db" \
        --bind "${BUILD_DIR}:/build" \
        "docker://${BLAST_IMAGE}" \
        makeblastdb \
            -in "/db/fluA_reference.fasta" \
            -dbtype nucl \
            -blastdb_version "${BLAST_DB_VERSION}" \
            -out "/build/fluA_db"
    echo "Verifying the new BLAST database..."
    singularity exec --bind "${BUILD_DIR}:/build" "docker://${BLAST_IMAGE}" blastdbcmd -db /build/fluA_db -info
}

if command -v makeblastdb >/dev/null 2>&1 && command -v blastdbcmd >/dev/null 2>&1; then
    build_with_local_blast
elif command -v docker >/dev/null 2>&1; then
    if ! docker info >/dev/null 2>&1; then
        echo "ERROR: Docker is installed but the Docker daemon is not running." >&2
        echo "Start Docker Desktop and rerun this script." >&2
        rm -rf "${TMP_DIR}"
        exit 1
    fi
    build_with_docker
elif command -v apptainer >/dev/null 2>&1; then
    build_with_apptainer
elif command -v singularity >/dev/null 2>&1; then
    build_with_singularity
else
    echo "ERROR: makeblastdb, Docker, Apptainer, and Singularity were not found." >&2
    rm -rf "${TMP_DIR}"
    exit 1
fi

# Publish only after makeblastdb and blastdbcmd both succeed. A failed build
# must never leave a success manifest that makes the desktop skip preparation.
echo "Installing the verified BLAST database..."
rm -f "${MANIFEST}"
find "${DB_DIR}" -maxdepth 1 -type f \
    \( -name 'fluA_db.n*' -o -name 'fluA_db.*.n*' -o -name 'fluA_db.*db' \) -delete
for database_file in "${BUILD_DIR}"/fluA_db.*; do
    [[ -f "${database_file}" ]] || { echo "ERROR: No BLAST database files were produced." >&2; exit 1; }
    cp "${database_file}" "${DB_DIR}/"
done

CREATED_AT_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

{
    printf 'database_name\tsource_archive\tsource_url\tgithub_repo\trelease_tag\tasset_name\tcreated_at_utc\tarchive_sha256\tfasta_sha256\tmakeblastdb_version\tblast_db_version\tbuild_method\tblast_image\tdb_prefix\n'
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        'fluA_db' \
        "resources/$(basename "${ZIP}")" \
        "${ZIP_URL}" \
        "${GITHUB_REPO}" \
        "${RELEASE_TAG}" \
        "${ASSET_NAME}" \
        "${CREATED_AT_UTC}" \
        "${ARCHIVE_SHA256}" \
        "${FASTA_SHA256}" \
        "${MAKEBLASTDB_VERSION}" \
        "${BLAST_DB_VERSION}" \
        "${BUILD_METHOD}" \
        "${BLAST_IMAGE}" \
        'resources/flu_db/fluA_db'
} > "${MANIFEST}"

rm -rf "${TMP_DIR}"

echo
echo "BLAST database successfully created:"
echo "  ${DB_PREFIX}"
echo "Provenance manifest written:"
echo "  ${MANIFEST}"
echo
echo "Use this value in config.yaml:"
echo "  blast_db: \"resources/flu_db/fluA_db\""

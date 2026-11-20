#!/bin/sh
# Native Docker client for the daemon's Linux VM. The scientific environment
# remains linux/amd64; DOCKER_DEFAULT_PLATFORM and explicit --platform survive.
# Default to amd64 for CI and direct use of this amd64 controller image.
case "${WINGS_DOCKER_CLI_ARCH:-amd64}" in
    amd64|arm64) exec "/opt/wings-desktop/bin/docker-${WINGS_DOCKER_CLI_ARCH:-amd64}" "$@" ;;
    *) printf '%s\n' 'Unsupported WINGS_DOCKER_CLI_ARCH; expected amd64 or arm64.' >&2; exit 64 ;;
esac

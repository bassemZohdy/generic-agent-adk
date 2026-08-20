#!/bin/sh
set -eu

image="${1:?usage: $0 IMAGE}"
case "$image" in
  *@sha256:*) digest="${image##*@sha256:}" ;;
  *)
    echo "Sandbox image must be pinned by digest: $image" >&2
    exit 1
    ;;
esac

if [ "${#digest}" -ne 64 ] || ! printf '%s\n' "$digest" | tr -d '0123456789abcdefABCDEF' | grep -q '^$'; then
  echo "Sandbox image digest is not a valid SHA-256: $image" >&2
  exit 1
fi

if command -v trivy >/dev/null 2>&1; then
  # The official Python image embeds a third-party SBOM for build-time wheel
  # contents (including packages that are not installed in the runtime layer).
  # Scan the Debian runtime packages here; application images separately scan
  # their resolved Python dependencies with the full Trivy package set.
  trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed \
    --pkg-types os "$image"
else
  echo "trivy is required to scan the sandbox image" >&2
  exit 1
fi

if command -v syft >/dev/null 2>&1; then
  syft "$image" --output "cyclonedx-json=${SYFT_OUTPUT:-sandbox-image-sbom.json}"
else
  echo "syft is required to generate the sandbox image SBOM" >&2
  exit 1
fi

echo "Sandbox image verification passed: $image"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/godot_project"
EXPORT_SCRIPT="$ROOT_DIR/scripts/export_godot_platforms.sh"
WATCH_INTERVAL_SECONDS="${WATCH_INTERVAL_SECONDS:-2}"

compute_fingerprint() {
  find "$PROJECT_DIR" -type f \
    ! -path "$PROJECT_DIR/.godot/*" \
    ! -name "*.tmp" \
    -printf '%P %T@\n' | LC_ALL=C sort | sha256sum | awk '{print $1}'
}

if [[ ! -x "$EXPORT_SCRIPT" ]]; then
  echo "[error] Export script is not executable: $EXPORT_SCRIPT" >&2
  exit 1
fi

echo "[watch] Watching $PROJECT_DIR every ${WATCH_INTERVAL_SECONDS}s"
echo "[watch] Output directory: $ROOT_DIR/platform_executables"

last_fingerprint=""

while true; do
  current_fingerprint="$(compute_fingerprint)"
  if [[ "$current_fingerprint" != "$last_fingerprint" ]]; then
    if [[ -n "$last_fingerprint" ]]; then
      echo "[watch] Change detected. Re-exporting..."
    else
      echo "[watch] Initial export..."
    fi

    if ! bash "$EXPORT_SCRIPT"; then
      echo "[watch] Export failed. Watching continues." >&2
    fi

    last_fingerprint="$current_fingerprint"
  fi

  sleep "$WATCH_INTERVAL_SECONDS"
done

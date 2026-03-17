#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/godot_project"
OUTPUT_DIR="$ROOT_DIR/platform_executables"
PRESETS_FILE="$PROJECT_DIR/export_presets.cfg"
GENERATE_CONFIG_SCRIPT="$ROOT_DIR/scripts/generate_godot_runtime_config.sh"

detect_godot_bin() {
  if [[ -n "${GODOT_BIN:-}" ]]; then
    echo "$GODOT_BIN"
    return 0
  fi

  local candidates=("godot4" "godot" "godot4.5")
  local candidate=""
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done

  local app_candidates=(
    "/home/jglossner/Apps/Godot_v4.5.1-stable_linux.x86_64"
    "/home/jglossner/Apps/Godot_v4.5.1-stable_mono_linux_x86_64/Godot_v4.5.1-stable_mono_linux.x86_64"
  )
  for candidate in "${app_candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

find_preset() {
  local preset=""
  for preset in "$@"; do
    if rg -F "name=\"$preset\"" "$PRESETS_FILE" >/dev/null 2>&1; then
      echo "$preset"
      return 0
    fi
  done
  return 1
}

run_export() {
  local label="$1"
  local output_path="$2"
  shift 2

  local preset=""
  if ! preset="$(find_preset "$@")"; then
    echo "[skip] No export preset found for $label ($*)"
    return 0
  fi

  mkdir -p "$(dirname "$output_path")"
  echo "[export] $label via preset '$preset' -> $output_path"
  "$GODOT_BIN_RESOLVED" --headless --path "$PROJECT_DIR" --export-release "$preset" "$output_path"
}

if [[ ! -f "$PRESETS_FILE" ]]; then
  echo "[error] Missing export presets file: $PRESETS_FILE" >&2
  exit 1
fi

if ! GODOT_BIN_RESOLVED="$(detect_godot_bin)"; then
  echo "[error] No Godot CLI binary found. Set GODOT_BIN or install godot4/godot." >&2
  exit 1
fi

bash "$GENERATE_CONFIG_SCRIPT"

mkdir -p "$OUTPUT_DIR"

failed=0
run_export "android" "$OUTPUT_DIR/android/Adaptive Learning 3D.apk" "Android" || failed=1
run_export "linux" "$OUTPUT_DIR/linux/Adaptive Learning 3D.x86_64" "Linux/X11" "Linux/BSD" || failed=1
run_export "windows" "$OUTPUT_DIR/windows/Adaptive Learning 3D.exe" "Windows Desktop" || failed=1
run_export "web" "$OUTPUT_DIR/web/Adaptive Learning 3D Web.zip" "Web" "HTML5" || failed=1

if [[ "$failed" -ne 0 ]]; then
  echo "[error] One or more exports failed." >&2
  exit 1
fi

echo "[done] Exports written under $OUTPUT_DIR"

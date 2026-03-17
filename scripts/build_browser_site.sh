#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/godot_project"
APP_DIR="$ROOT_DIR/html/app"
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

if ! GODOT_BIN_RESOLVED="$(detect_godot_bin)"; then
  echo "[error] No Godot CLI binary found. Set GODOT_BIN or install godot4/godot." >&2
  exit 1
fi

bash "$GENERATE_CONFIG_SCRIPT"

mkdir -p "$APP_DIR" /tmp/godot-config

echo "[export] Web -> $APP_DIR/index.html"
XDG_CONFIG_HOME=/tmp/godot-config \
HOME="${HOME:-/home/jglossner}" \
"$GODOT_BIN_RESOLVED" --headless --path "$PROJECT_DIR" --export-release Web "$APP_DIR/index.html"

ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
import os
from pathlib import Path

index_path = Path(os.environ["ROOT_DIR"]) / "html" / "app" / "index.html"
html = index_path.read_text(encoding="utf-8")

title_from = "<title>Adaptive Learning 3D</title>"
title_to = """<title>Adaptive Tutor | Browser App</title>
\t\t<meta name=\"description\" content=\"Adaptive Tutor browser app for desktop and iPad.\">
\t\t<meta name=\"theme-color\" content=\"#242424\">
\t\t<meta name=\"apple-mobile-web-app-capable\" content=\"yes\">
\t\t<meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">
\t\t<meta name=\"apple-mobile-web-app-title\" content=\"Adaptive Tutor\">"""

if title_from in html and "apple-mobile-web-app-title" not in html:
    html = html.replace(title_from, title_to, 1)

index_path.write_text(html, encoding="utf-8")
PY

echo "[done] Browser site app bundle refreshed under $APP_DIR"

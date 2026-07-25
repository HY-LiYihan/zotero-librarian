#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh [--codex] [--claude] [--force]

Install the canonical zotero-librarian skill for one or more Agent clients.
At least one client flag is required.
EOF
}

install_codex=0
install_claude=0
force=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --codex) install_codex=1 ;;
    --claude) install_claude=1 ;;
    --force) force=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "$install_codex" == 0 && "$install_claude" == 0 ]]; then
  usage >&2
  exit 2
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
source_skill="$script_dir/skills/zotero-librarian"

install_skill() {
  local root="$1"
  local destination="$root/zotero-librarian"
  mkdir -p "$root"
  if [[ -e "$destination" && "$force" == 0 ]]; then
    printf 'Refusing to overwrite %s; rerun with --force.\n' "$destination" >&2
    return 1
  fi
  if [[ -e "$destination" ]]; then
    local backup="${destination}.backup.$(date +%Y%m%d%H%M%S)"
    mv "$destination" "$backup"
    printf 'Backed up existing skill to %s\n' "$backup"
  fi
  cp -R "$source_skill" "$destination"
  printf 'Installed Zotero Librarian to %s\n' "$destination"
}

if [[ "$install_codex" == 1 ]]; then
  install_skill "${CODEX_HOME:-$HOME/.codex}/skills"
fi
if [[ "$install_claude" == 1 ]]; then
  install_skill "${CLAUDE_HOME:-$HOME/.claude}/skills"
fi

if command -v zot >/dev/null 2>&1; then
  printf 'Found zot: %s\n' "$(command -v zot)"
  printf 'Run `zot ping` with Zotero Desktop open to verify the bridge.\n'
else
  cat <<'EOF'
The `zot` command is not installed. Install the MIT-licensed backend and bridge:
  uv tool install zotero-agent
  https://github.com/alex-roc/zotero-agent/releases/latest
Then run:
  zot init
  zot ping
EOF
fi

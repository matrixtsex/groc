#!/bin/sh
set -eu

repo_url="${GROC_REPO_URL:-https://github.com/matrixtsex/groc.git}"
source_dir="${GROC_INSTALL_SOURCE:-$HOME/.local/share/groc-src}"

if ! command -v git >/dev/null 2>&1; then
  echo "groc installer requires git" >&2
  exit 1
fi

mkdir -p "$(dirname "$source_dir")"

if [ -d "$source_dir/.git" ]; then
  git -C "$source_dir" fetch --prune origin
  git -C "$source_dir" reset --hard origin/master
else
  rm -rf "$source_dir"
  git clone "$repo_url" "$source_dir"
fi

"$source_dir/bin/install"

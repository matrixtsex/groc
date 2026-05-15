#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version="${1:-$(git -C "$repo_root" describe --tags --always 2>/dev/null || echo dev)}"
name="groc-$version"
dist="$repo_root/dist"
stage="$dist/$name"

rm -rf "$stage"
mkdir -p "$stage/bin" "$stage/config"

cp "$repo_root/README.md" "$stage/README.md"
cp "$repo_root/LICENSE" "$stage/LICENSE"
cp "$repo_root/SECURITY.md" "$stage/SECURITY.md"
cp "$repo_root/CONTRIBUTING.md" "$stage/CONTRIBUTING.md"
cp "$repo_root/CODE_OF_CONDUCT.md" "$stage/CODE_OF_CONDUCT.md"
cp "$repo_root/pyproject.toml" "$stage/pyproject.toml"
cp "$repo_root/Makefile" "$stage/Makefile"
cp "$repo_root/install.sh" "$stage/install.sh"
cp "$repo_root/bin/groc" "$stage/bin/groc"
cp "$repo_root/bin/groc-bridge" "$stage/bin/groc-bridge"
cp "$repo_root/bin/install" "$stage/bin/install"
cp -R "$repo_root/groc" "$stage/groc"
cp -R "$repo_root/tests" "$stage/tests"
cp -R "$repo_root/docs" "$stage/docs"
cp "$repo_root/config/groc.config.toml" "$stage/config/groc.config.toml"
chmod +x "$stage/install.sh" "$stage/bin/groc" "$stage/bin/groc-bridge" "$stage/bin/install"
find "$stage" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$stage" -type f -name "*.pyc" -delete

mkdir -p "$dist"
tar -C "$dist" -czf "$dist/$name.tar.gz" "$name"
if command -v zip >/dev/null 2>&1; then
  (cd "$dist" && zip -qr "$name.zip" "$name")
fi

echo "$dist/$name.tar.gz"
if [ -f "$dist/$name.zip" ]; then
  echo "$dist/$name.zip"
fi

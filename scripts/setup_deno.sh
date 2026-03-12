#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT_DIR/bin"
TARGET_PATH="$BIN_DIR/deno"
mkdir -p "$BIN_DIR"

ARCH="$(uname -m)"
OS="$(uname -s)"
if [[ "$OS" == "Linux" ]]; then
  case "$ARCH" in
    x86_64|amd64) DENO_ASSET="deno-x86_64-unknown-linux-gnu.zip" ;;
    aarch64|arm64) DENO_ASSET="deno-aarch64-unknown-linux-gnu.zip" ;;
    *)
      echo "Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac
elif [[ "$OS" == "Darwin" ]]; then
  case "$ARCH" in
    x86_64|amd64) DENO_ASSET="deno-x86_64-apple-darwin.zip" ;;
    aarch64|arm64) DENO_ASSET="deno-aarch64-apple-darwin.zip" ;;
    *)
      echo "Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac
else
  echo "Unsupported OS: $OS" >&2
  exit 1
fi

DOWNLOAD_URL="https://github.com/denoland/deno/releases/latest/download/${DENO_ASSET}"
echo "Downloading Deno from ${DOWNLOAD_URL}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
curl -fsSL "$DOWNLOAD_URL" -o "$TMP_DIR/deno.zip"
unzip -q "$TMP_DIR/deno.zip" -d "$TMP_DIR"
mv "$TMP_DIR/deno" "$TARGET_PATH"
chmod +x "$TARGET_PATH"
"$TARGET_PATH" --version
echo "Installed Deno to $TARGET_PATH"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT_DIR/bin"
TARGET_PATH="${AIRWAVE_YT_DLP_PATH:-$BIN_DIR/yt-dlp}"
mkdir -p "$(dirname "$TARGET_PATH")"

ARCH="$(uname -m)"
OS="$(uname -s)"
if [[ "$OS" == "Linux" ]]; then
  case "$ARCH" in
    x86_64|amd64) ASSET="yt-dlp_linux" ;;
    aarch64|arm64) ASSET="yt-dlp_linux_aarch64" ;;
    *)
      echo "Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac
elif [[ "$OS" == "Darwin" ]]; then
  # yt-dlp publishes a universal macOS executable named `yt-dlp_macos`.
  ASSET="yt-dlp_macos"
else
  echo "Unsupported OS: $OS" >&2
  exit 1
fi

DOWNLOAD_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/${ASSET}"
echo "Downloading yt-dlp from ${DOWNLOAD_URL}"
curl -fsSL -L --retry 3 --retry-delay 2 "$DOWNLOAD_URL" -o "$TARGET_PATH"
chmod +x "$TARGET_PATH"
"$TARGET_PATH" --version
echo "Installed yt-dlp to $TARGET_PATH"

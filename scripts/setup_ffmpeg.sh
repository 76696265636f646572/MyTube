#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT_DIR/bin"
TARGET_PATH="${AIRWAVE_FFMPEG_PATH:-$BIN_DIR/ffmpeg}"
mkdir -p "$(dirname "$TARGET_PATH")"

if command -v "$TARGET_PATH" >/dev/null 2>&1; then
  echo "ffmpeg already present at $TARGET_PATH"
  exit 0
fi

ARCH="$(uname -m)"
OS="$(uname -s)"
if [[ "$OS" == "Linux" ]]; then
  case "$ARCH" in
    x86_64|amd64) ASSET_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz" ;;
    aarch64|arm64) ASSET_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linuxarm64-gpl.tar.xz" ;;
    *)
      echo "Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac
elif [[ "$OS" == "Darwin" ]]; then
  case "$ARCH" in
    x86_64|amd64) ASSET_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-macos64-gpl.zip" ;;
    aarch64|arm64) ASSET_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-macosarm64-gpl.zip" ;;
    *)
      echo "Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac
else
  echo "Unsupported OS: $OS" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Downloading ffmpeg from $ASSET_URL"
if [[ "$ASSET_URL" == *.zip ]]; then
  curl -fsSL "$ASSET_URL" -o "$TMP_DIR/ffmpeg.zip"
  unzip -q "$TMP_DIR/ffmpeg.zip" -d "$TMP_DIR"
else
  curl -fsSL "$ASSET_URL" -o "$TMP_DIR/ffmpeg.tar.xz"
  tar -xJf "$TMP_DIR/ffmpeg.tar.xz" -C "$TMP_DIR"
fi
FFMPEG_BIN="$(find "$TMP_DIR" -type f -name ffmpeg | head -n 1)"
if [[ -z "${FFMPEG_BIN:-}" ]]; then
  echo "Could not find ffmpeg binary in downloaded archive" >&2
  exit 1
fi
cp "$FFMPEG_BIN" "$TARGET_PATH"
chmod +x "$TARGET_PATH"
"$TARGET_PATH" -version | head -n 1
echo "Installed ffmpeg to $TARGET_PATH"

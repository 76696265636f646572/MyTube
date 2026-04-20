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
  # `yt-dlp/FFmpeg-Builds` no longer publishes macOS artifacts.
  # On macOS we prefer an existing `ffmpeg` on PATH, otherwise Homebrew.
  if command -v ffmpeg >/dev/null 2>&1; then
    echo "Using ffmpeg from PATH: $(command -v ffmpeg)"
    cp "$(command -v ffmpeg)" "$TARGET_PATH"
    chmod +x "$TARGET_PATH"
    "$TARGET_PATH" -version | head -n 1
    echo "Installed ffmpeg to $TARGET_PATH"
    exit 0
  fi

  if command -v brew >/dev/null 2>&1; then
    echo "Installing ffmpeg via Homebrew..."
    # Homebrew can occasionally return non-zero while still installing the formula
    # (e.g. post-install warnings). If ffmpeg ends up on PATH, proceed.
    if ! brew install ffmpeg; then
      echo "Homebrew reported an error; checking whether ffmpeg is available anyway..." >&2
    fi
    if ! command -v ffmpeg >/dev/null 2>&1; then
      echo "ffmpeg is still not available on PATH after Homebrew install." >&2
      exit 1
    fi
    cp "$(command -v ffmpeg)" "$TARGET_PATH"
    chmod +x "$TARGET_PATH"
    "$TARGET_PATH" -version | head -n 1
    echo "Installed ffmpeg to $TARGET_PATH"
    exit 0
  fi

  echo "ffmpeg not found. Install it (e.g. via Homebrew) or set AIRWAVE_FFMPEG_PATH to an existing ffmpeg binary." >&2
  exit 1
else
  echo "Unsupported OS: $OS" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Downloading ffmpeg from $ASSET_URL"
curl -fsSL "$ASSET_URL" -o "$TMP_DIR/ffmpeg.tar.xz"
tar -xJf "$TMP_DIR/ffmpeg.tar.xz" -C "$TMP_DIR"
FFMPEG_BIN="$(find "$TMP_DIR" -type f -name ffmpeg | head -n 1)"
if [[ -z "${FFMPEG_BIN:-}" ]]; then
  echo "Could not find ffmpeg binary in downloaded archive" >&2
  exit 1
fi
cp "$FFMPEG_BIN" "$TARGET_PATH"
chmod +x "$TARGET_PATH"
"$TARGET_PATH" -version | head -n 1
echo "Installed ffmpeg to $TARGET_PATH"

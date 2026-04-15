# Multi-stage build for production-ready image
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    xz-utils \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency files
COPY pyproject.toml ./
COPY package.json package-lock.json* ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir ".[dev]"

# Install frontend dependencies
RUN npm ci

# Copy application source
COPY . .

# Build frontend
RUN npm run build

# Download and install yt-dlp
RUN mkdir -p /build/bin \
    && ARCH=$(uname -m) \
    && case "$ARCH" in \
        x86_64|amd64) ASSET="yt-dlp_linux" ;; \
        aarch64|arm64) ASSET="yt-dlp_linux_aarch64" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/${ASSET}" -o /build/bin/yt-dlp \
    && chmod +x /build/bin/yt-dlp

# Download and install Deno (JS runtime for yt-dlp EJS)
RUN ARCH=$(uname -m) \
    && case "$ARCH" in \
        x86_64|amd64) DENO_ASSET="deno-x86_64-unknown-linux-gnu.zip" ;; \
        aarch64|arm64) DENO_ASSET="deno-aarch64-unknown-linux-gnu.zip" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/denoland/deno/releases/latest/download/${DENO_ASSET}" -o /tmp/deno.zip \
    && unzip -q /tmp/deno.zip -d /tmp/deno-extract \
    && mv /tmp/deno-extract/deno /build/bin/deno \
    && chmod +x /build/bin/deno \
    && rm -rf /tmp/deno.zip /tmp/deno-extract

# Download and install ffmpeg (yt-dlp FFmpeg-Builds tarball)
RUN ARCH=$(uname -m) \
    && case "$ARCH" in \
        x86_64|amd64) ASSET_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz" ;; \
        aarch64|arm64) ASSET_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linuxarm64-gpl.tar.xz" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac \
    && TMP_DIR=$(mktemp -d) \
    && curl -fsSL "$ASSET_URL" -o "$TMP_DIR/ffmpeg.tar.xz" \
    && tar -xJf "$TMP_DIR/ffmpeg.tar.xz" -C "$TMP_DIR" \
    && FFMPEG_BIN=$(find "$TMP_DIR" -type f -name ffmpeg | head -n 1) \
    && cp "$FFMPEG_BIN" /build/bin/ffmpeg \
    && chmod +x /build/bin/ffmpeg \
    && rm -rf "$TMP_DIR"

# ffprobe from Martin Riedl FFmpeg build server (https://ffmpeg.martin-riedl.de/ — redirect "Scripting URLs", release build)
RUN ARCH=$(uname -m) \
    && case "$ARCH" in \
        x86_64|amd64) MR_ARCH=amd64 ;; \
        aarch64|arm64) MR_ARCH=arm64 ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac \
    && TMP_DIR=$(mktemp -d) \
    && curl -fsSL -L --retry 3 --retry-delay 2 \
        "https://ffmpeg.martin-riedl.de/redirect/latest/linux/${MR_ARCH}/release/ffprobe.zip" \
        -o "$TMP_DIR/ffprobe.zip" \
    && unzip -q "$TMP_DIR/ffprobe.zip" -d "$TMP_DIR/out" \
    && FFPROBE_BIN=$(find "$TMP_DIR/out" -type f -name ffprobe | head -n 1) \
    && cp "$FFPROBE_BIN" /build/bin/ffprobe \
    && chmod +x /build/bin/ffprobe \
    && rm -rf "$TMP_DIR"

# Production stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 airwave && \
    mkdir -p /app /app/bin /app/data && \
    chown -R airwave:airwave /app

WORKDIR /app

# Copy dependency file and app source (needed for package installation)
COPY --chown=airwave:airwave pyproject.toml ./
COPY --chown=airwave:airwave app/ ./app/

# Install Python packages (production only, no dev deps)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

# Copy built frontend assets from builder (overwrites app/static/dist)
COPY --chown=airwave:airwave --from=builder /build/app/static/dist ./app/static/dist

# Copy binaries from builder
COPY --chown=airwave:airwave --from=builder /build/bin/yt-dlp ./bin/yt-dlp
COPY --chown=airwave:airwave --from=builder /build/bin/deno ./bin/deno
COPY --chown=airwave:airwave --from=builder /build/bin/ffmpeg ./bin/ffmpeg
COPY --chown=airwave:airwave --from=builder /build/bin/ffprobe ./bin/ffprobe

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AIRWAVE_YT_DLP_PATH=/app/bin/yt-dlp \
    AIRWAVE_FFMPEG_PATH=/app/bin/ffmpeg \
    AIRWAVE_FFPROBE_PATH=/app/bin/ffprobe \
    AIRWAVE_DENO_PATH=/app/bin/deno \
    PATH="/app/bin:${PATH}"

# Switch to non-root user
USER airwave

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# 🚀 Airwave  
### Self-hosted shared radio — everyone listens in sync

![GitHub stars](https://img.shields.io/github/stars/76696265636f646572/Airwave?style=social)
![GitHub forks](https://img.shields.io/github/forks/76696265636f646572/Airwave?style=social)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688.svg)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org/)

> 🎧 **Turn any link into a shared listening experience**

Paste a YouTube, SoundCloud, Mixcloud, or Spotify playlist link →  
Airwave creates a **single live stream** →  
Everyone hears the **exact same audio**

No accounts. No premium APIs. No “press play at the same time.”

![Airwave Demo](./app.png)

---

## ⚡ Try it in 30 seconds

```bash
docker run -d -p 8000:8000 ghcr.io/76696265636f646572/airwave
````

Open → [http://localhost:8000](http://localhost:8000)

Paste a link → music starts → share the URL 🎉

---

## 🎧 The idea (why this exists)

Many music apps weren’t built for **shared listening**:

* Everyone plays their **own stream**
* Locked into one platform

**Airwave solves this:**

* One stream → multiple listeners
* Works across browsers and Sonos
* Import Spotify playlists → automatically matched to playable tracks
* Multi-source playback (YouTube, SoundCloud, Mixcloud, direct URLs, optional local files)

Simple idea. Huge difference.

---

## ✨ What makes Airwave different?

### 🔊 One shared live stream

* One `/stream/live.mp3`
* All listeners hear the same thing
* No per-user transcoding
* Perfect sync across devices

---

### 📋 Collaborative queue

* Anyone can add tracks
* Drag & reorder in real time
* Shared history

---

### ▶️ Multi-source playback

* YouTube (videos + playlists)
* SoundCloud (tracks + sets)
* Mixcloud (shows)
* Direct HTTP(S) URLs to audio when ffmpeg can read them
* Local files

👉 Paste almost any music link — it just works

---

### 💿 Local files & folders

* Point Airwave at one or more directories with **`AIRWAVE_LOCAL_MEDIA_ROOTS`**
* Browse and queue tracks from the UI (paths must stay inside those roots)
* Great for NAS mounts, a music library on disk, or bind-mounted folders in Docker

---

### 🎵 Spotify → playable music

* Import Spotify playlists into your **library**
* Auto-match tracks to YouTube, SoundCloud, or Mixcloud
* Review and pick the best version for your shared stream

---

### 🔈 Sonos integration

* Discover speakers on your LAN
* Group and control playback
* Same stream as browser clients

---

### 🎮 Player experience

* Play / pause / skip / repeat
* Seek (when supported)
* Fullscreen “Now Playing”
* Lock screen controls (Media Session)

---

### 📚 Library & playlists

* Create and manage playlists
* Import YouTube or Spotify playlists
* Merge playlists (with deduplication)
* Pin and reorder
* **Optional background sync** — per playlist, enable **Auto-sync** on the playlist page so Airwave periodically checks the upstream playlist (YouTube, SoundCloud, or Spotify) and **appends new tracks only** (no reordering). Spotify additions are **auto-searched** and the first playable match is applied. An optional second toggle can **remove tracks** that no longer appear upstream (off by default).

---

## 🧑‍🤝‍🧑 Perfect for

* 🎉 Parties (everyone queues music)
* 🏠 Shared household audio
* 🧑‍💻 Remote team listening
* 🔊 Sonos multi-room setups
* 🎧 Friends hanging out online

---

## 🧠 How it works

```
yt-dlp → ffmpeg → shared MP3 stream → all listeners
```

* One pipeline
* One stream
* Unlimited listeners

---

## 🐳 Docker (recommended)

For full functionality (especially Sonos):

```yaml
network_mode: host
```

Set your public URL:

```env
AIRWAVE_PUBLIC_BASE_URL=http://192.168.1.50:8000
```

For **local files**, mount host directories into the container and set `AIRWAVE_LOCAL_MEDIA_ROOTS` to those in-container paths (see **Configuration** below).

---

## ⚙️ Configuration

```env
AIRWAVE_HOST=0.0.0.0
AIRWAVE_PORT=8000
AIRWAVE_PUBLIC_BASE_URL=http://192.168.1.50:8000

AIRWAVE_FFMPEG_PATH=./bin/ffmpeg
AIRWAVE_FFPROBE_PATH=./bin/ffprobe
AIRWAVE_YT_DLP_PATH=./bin/yt-dlp
AIRWAVE_DENO_PATH=./bin/deno

# Optional: allow browsing and queuing audio from these directories (server-side paths).
# Comma-separated list, or a JSON array string, e.g. ["/music","/data/audio"].
# Leave unset to disable local media. In Docker, bind-mount the host folders and set paths inside the container.
AIRWAVE_LOCAL_MEDIA_ROOTS=/path/to/music,/other/library

AIRWAVE_MP3_BITRATE=128k
AIRWAVE_CHUNK_SIZE=256
AIRWAVE_STREAM_QUEUE_SIZE=16
AIRWAVE_LOG_LEVEL=info

# Optional: background playlist sync (only playlists with Auto-sync enabled in the UI).
# How often the sync loop runs, and how many playlists it may process concurrently.
AIRWAVE_PLAYLIST_SYNC_INTERVAL_SECONDS=3600
AIRWAVE_PLAYLIST_SYNC_MAX_CONCURRENT=2
```

`AIRWAVE_FFMPEG_PATH` and `AIRWAVE_FFPROBE_PATH` are configured independently. Point each one to the executable you want Airwave to use.

`AIRWAVE_CHUNK_SIZE` is how many bytes are read from ffmpeg’s stdout per pull into the shared stream (default `256`). Larger values mean fewer read syscalls; very small values increase overhead. `AIRWAVE_STREAM_QUEUE_SIZE` is the max depth of the in-memory buffer between ffmpeg and connected listeners (default `16`). Raise it if devices such as Sonos underrun the live stream.

---

## 🧱 Tech Stack

* FastAPI
* Vue 3
* yt-dlp
* ffmpeg
* SQLite

---

## 🏗 Architecture (simplified)

* StreamEngine — playback worker & prefetch
* FfmpegPipeline — transcoding & ffprobe probing
* MediaSourceResolver — local files & direct media URLs
* PlaylistService — queue/import orchestration
* SyncService — optional background sync for imported playlists (off per playlist until enabled)
* SharedMp3Hub — fan-out
* BinariesService — yt-dlp/ffmpeg/ffprobe/deno management
* Repository — persistence

---

## 💬 Why Airwave?

Because shared music should be:

* simple
* synced
* platform-independent

Not:

* fragmented
* locked-in
* out of sync

---

## 🤝 Contributing

Ideas, issues, and PRs welcome!

👉 See [CONTRIBUTING.md](./CONTRIBUTING.md)

---

## ⭐ Support

If you like Airwave:

* ⭐ Star the repo
* 🐛 Report bugs
* 💡 Suggest features
* 📢 Share it

---

## 🧭 Final thought

> Airwave isn’t a music player.
> It’s a **shared radio for the internet.**

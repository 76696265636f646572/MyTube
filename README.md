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
* Multi-source playback (YouTube, SoundCloud, Mixcloud)

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

👉 Paste almost any music link — it just works

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

---

## ⚙️ Configuration

```env
AIRWAVE_HOST=0.0.0.0
AIRWAVE_PORT=8000
AIRWAVE_PUBLIC_BASE_URL=http://192.168.1.50:8000

AIRWAVE_FFMPEG_PATH=./bin/ffmpeg
AIRWAVE_YT_DLP_PATH=./bin/yt-dlp
AIRWAVE_DENO_PATH=./bin/deno

AIRWAVE_MP3_BITRATE=128k
AIRWAVE_LOG_LEVEL=info
```

---

## 🧱 Tech Stack

* FastAPI
* Vue 3
* yt-dlp
* ffmpeg
* SQLite

---

## 🏗 Architecture (simplified)

* StreamEngine — playback worker
* FfmpegPipeline — transcoding
* YtDlpService — providers
* SharedMp3Hub — fan-out
* SpotifyImportService — playlist import & match
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

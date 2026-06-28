# VodLink

Browse and link IPTV VOD content from [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) into your [Emby](https://emby.media) library.

VodLink reads your Dispatcharr VOD directories, lets you search and browse movies and series, and creates the right file structures in your Emby-scanned directories so Emby can play them — including a stream proxy that handles Dispatcharr's redirect behavior for seeking, resume, and scanning to work correctly.

---

## Features

- Browse and search movies and series from Dispatcharr VOD sources
- One-click link/unlink to Emby library directories
- Stream proxy: converts Emby's `HEAD` requests to `GET`, caches Dispatcharr session URLs so seeking and resume work
- Scheduled sync to keep the VodLink database current with Dispatcharr
- Backup and restore for the VodLink database
- Dark/light/system theme
- Runs entirely in Docker

---

## Prerequisites

- [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) with VOD content
- [Emby](https://emby.media) (or Jellyfin) with library directories on the same host
- Docker + Docker Compose

---

## Quick Start

```bash
git clone https://github.com/jdfrey1/vodlink.git
cd vodlink
cp .env.example .env
# Edit .env with your paths and settings
docker compose up -d
```

Open `http://YOUR-NAS-IP:7842` in your browser.

---

## Configuration

Copy `.env.example` to `.env` and set the following:

| Variable | Description |
|---|---|
| `VODLINK_PORT` | Port the UI is served on (default: `7842`) |
| `MOVIES_SRC` | Host path to Dispatcharr's Movies VOD directory |
| `SERIES_SRC` | Host path to Dispatcharr's Series VOD directory |
| `MOVIES_DEST` | Host path to the directory Emby scans for movies |
| `SERIES_DEST` | Host path to the directory Emby scans for series |
| `DATA_DIR` | Where VodLink stores its database and backups |
| `PUID` / `PGID` | UID/GID to run the container as (run `id <your-user>`) |

> **Important:** `MOVIES_SRC` and `SERIES_SRC` must be the exact host paths — they are mounted at the same path inside the container so that symlinks VodLink creates resolve correctly when Emby follows them on the host.

---

## How It Works

### Linking

**Movies** — VodLink creates a real directory in the Emby destination with a `.strm` file pointing to VodLink's stream proxy, plus symlinked `.nfo` metadata files.

**Series** — VodLink creates a directory symlink pointing directly at the Dispatcharr source directory.

### Stream Proxy

Dispatcharr's VOD streams behave in ways that break Emby's default playback:

- Dispatcharr returns `405` for `HEAD` requests (Emby uses these to get file size for seeking and resume)
- Dispatcharr returns a `301` redirect to a unique per-request session URL

VodLink's `/stream/{type}/{tmdb_id}` endpoint handles both:

- **HEAD requests** — converted to `GET Range: bytes=0-0`, extracts total file size from `Content-Range`, returns a synthetic `200` response with the correct `Content-Length`
- **GET requests** — follows the initial Dispatcharr redirect once, caches the session URL, and reuses it for all subsequent seeks so Dispatcharr doesn't see concurrent session conflicts

---

## Using a Pre-built Image

Instead of building locally, you can pull the image from GitHub Container Registry:

```yaml
# In docker-compose.yml, replace the build block with:
image: ghcr.io/jdfrey1/vodlink:latest
```

---

## Building Locally

On low-memory hosts (e.g. Synology NAS), limit Docker's build memory to avoid OOM:

```bash
docker build --memory=3g --memory-swap=4g -t vodlink-vodlink .
docker compose up -d
```

---

## License

MIT

# VodLink

Browse and link IPTV VOD content from [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) into your [Emby](https://emby.media) library.

VodLink is the glue between the [VOD2MLIB](https://github.com/R3XCHRIS/VOD2MLIB) Dispatcharr plugin and Emby. VOD2MLIB generates `.strm` and `.nfo` files from your IPTV VOD catalog inside Dispatcharr. VodLink reads those files, lets you browse and selectively link movies and series into your Emby library, and runs a stream proxy so that Emby's seeking, resume, and scanning all work correctly with Dispatcharr's redirect-based streaming.

---

## How the Stack Fits Together

```
Dispatcharr + VOD2MLIB plugin
        │
        │  generates /VODS/Movies and /VODS/Series
        │  (.strm playback URLs + .nfo metadata)
        ▼
     VodLink
        │
        │  browses source, lets you link items
        │  proxies streams (handles HEAD→GET, session caching)
        ▼
       Emby
        │
        │  scans linked directories, plays via VodLink proxy
        ▼
     Playback
```

---

## Features

- Browse and search movies and series from VOD2MLIB source directories
- One-click link/unlink to Emby library directories
- Stream proxy: converts Emby's `HEAD` requests to `GET`, caches Dispatcharr session URLs so seeking and resume work
- Scheduled sync to keep the VodLink database current with source changes
- Backup and restore for the VodLink database
- Dark/light/system theme
- Runs entirely in Docker

---

## Prerequisites

- [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) v0.24.0+ with the [VOD2MLIB](https://github.com/R3XCHRIS/VOD2MLIB) plugin configured and generating `/VODS/Movies` and `/VODS/Series`
- The Dispatcharr `/VODS` directory accessible on the same host as VodLink (volume mount or bind mount)
- [Emby](https://emby.media) with library directories on the same host
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

### Source Files

VodLink reads the `.strm` and `.nfo` files that VOD2MLIB generates in the Dispatcharr `/VODS/Movies` and `/VODS/Series` directories. These must be mounted into the VodLink container at the same host path (see [Configuration](#configuration)).

### Linking

**Movies** — VodLink creates a real directory in the Emby destination with a `.strm` file pointing to VodLink's stream proxy endpoint, plus symlinked `.nfo` metadata files from the VOD2MLIB source.

**Series** — VodLink creates a directory symlink pointing directly at the VOD2MLIB source directory.

### Stream Proxy

Dispatcharr's streaming behavior breaks Emby's default playback in two ways:

- Dispatcharr returns `405` for `HEAD` requests (Emby uses `HEAD` to get file size for seeking and resume)
- Dispatcharr returns a `301` redirect to a unique per-request session URL (a new request to the same URL creates a new session, causing concurrency errors on seeks)

VodLink's `/stream/{type}/{tmdb_id}` proxy handles both:

- **HEAD requests** — converted to `GET Range: bytes=0-0`, extracts total file size from `Content-Range`, returns a synthetic `200` with the correct `Content-Length`
- **GET requests** — follows Dispatcharr's redirect once, caches the session URL, reuses it for all subsequent range requests so seeks don't create new competing sessions

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

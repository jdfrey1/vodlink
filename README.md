# VodLink

Browse and link IPTV VOD content from [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) into [Emby](https://emby.media).

VodLink bridges [VOD2MLIB](https://github.com/R3XCHRIS/VOD2MLIB) and Emby. VOD2MLIB generates `.strm` + `.nfo` files from IPTV VOD catalog inside Dispatcharr. VodLink reads those files, lets you browse and link movies/series into Emby library, and runs a stream proxy so seeking, resume, and scanning work correctly with Dispatcharr's redirect-based streaming.

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

- Browse and search movies/series from VOD2MLIB source directories
- One-click link/unlink to Emby library directories
- Stream proxy: converts `HEAD` to `GET`, caches Dispatcharr session URLs so seeking and resume work
- Scheduled sync keeps VodLink database current with source changes
- Backup and restore for VodLink database
- Dark/light/system theme
- Runs in Docker

---

## Prerequisites

- [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr) v0.24.0+ with [VOD2MLIB](https://github.com/R3XCHRIS/VOD2MLIB) plugin generating `/VODS/Movies` and `/VODS/Series`
- Dispatcharr `/VODS` directory accessible on same host as VodLink (volume or bind mount)
- [Emby](https://emby.media) with library directories on same host
- Docker + Docker Compose

---

## Quick Start

```bash
# Download the compose file and example config
curl -O https://raw.githubusercontent.com/jdfrey1/vodlink/main/docker-compose.example.yml
curl -O https://raw.githubusercontent.com/jdfrey1/vodlink/main/.env.example
mv .env.example .env

# Edit .env with your paths and settings, then start
docker compose -f docker-compose.example.yml up -d
```

Open `http://YOUR-NAS-IP:7842` in your browser.

---

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|---|---|
| `VODLINK_PORT` | Port UI is served on (default: `7842`) |
| `VOD_SRC` | Host path to VOD2MLIB output directory (must contain `Movies/` and `Series/`) |
| `VOD_DEST` | Host path to root Emby scans (must contain `Movies/` and `Series/`) |
| `DATA_DIR` | Where VodLink stores database and backups |
| `PUID` / `PGID` | UID/GID to run container as (run `id <your-user>`) |

---

## How It Works

### Source Files

VodLink reads `.strm` and `.nfo` files VOD2MLIB generates in `/VODS/Movies` and `/VODS/Series`. Mount these into the container via `VOD_SRC` (see [Configuration](#configuration)).

### Linking

**Movies** — VodLink creates a directory in Emby destination with a `.strm` pointing to VodLink's stream proxy and a copy of the `.nfo` from VOD2MLIB source.

**Series** — VodLink copies entire VOD2MLIB series directory tree (`.strm` + `.nfo` for every episode) into Emby destination.

Copied files refresh after each scan — VOD2MLIB metadata updates and new episodes propagate to Emby destination automatically.

### Stream Proxy

Dispatcharr's streaming breaks Emby playback two ways:

- Returns `405` for `HEAD` requests (Emby uses `HEAD` for file size, seeking, resume)
- Returns `301` redirect to unique per-request session URL (new request = new session = concurrency errors on seeks)

VodLink's `/stream/{type}/{tmdb_id}` proxy handles both:

- **HEAD** — converted to `GET Range: bytes=0-0`, extracts total size from `Content-Range`, returns synthetic `200` with correct `Content-Length`
- **GET** — follows Dispatcharr's redirect once, caches session URL, reuses for all range requests so seeks don't create competing sessions

---

## Using a Pre-built Image

Pull from GitHub Container Registry:

```yaml
# In docker-compose.yml, replace the build block with:
image: ghcr.io/jdfrey1/vodlink:latest
```

---

## Building Locally

On low-memory hosts (e.g. Synology NAS), limit build memory to avoid OOM:

```bash
docker build --memory=3g --memory-swap=4g -t vodlink-vodlink .
docker compose up -d
```

---

## License

MIT

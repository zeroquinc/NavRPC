import base64
import io
import json
import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from PIL import Image

from .config import NavidromeConfig, ImageConfig

# -------------------------
# Utilities
# -------------------------
def log(msg: str):
    """Simplified log function."""
    print(f"[NavRPC] {msg}")

_SESSION: Optional[requests.Session] = None

def get_session() -> requests.Session:
    """Create and return a cached requests.Session with retries."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        # Your existing retry logic
        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        _SESSION.mount("http://", adapter)
        _SESSION.mount("https://", adapter)
    return _SESSION

# -------------------------
# Data Model
# -------------------------
@dataclass(slots=True)
class TrackInfo:
    title: str
    artists: str
    album: str
    cover_id: str
    duration: Optional[int] = None
    position: Optional[float] = None
    minutes_ago: Optional[int] = None

    @classmethod
    def from_json(cls, np_json: Optional[dict]) -> Optional["TrackInfo"]:
        # Simplified the parsing, assuming standard Navidrome output structure
        if not np_json:
            return None
        
        entry = np_json.get("entry", {})
        if isinstance(entry, list) and entry:
             entry = entry[0]
        
        if not isinstance(entry, dict):
            return None

        # Existing robust parsing logic
        title = entry.get("title") or entry.get("name", "")
        raw_artists = entry.get("artist") or entry.get("artists", "")
        artists = ", ".join(a.strip() for a in raw_artists.replace(";", ",").split(",") if a.strip())
        duration = int(entry.get("duration", 0)) if entry.get("duration") else None
        position_raw = entry.get("position", entry.get("elapsed"))
        position_seconds = None
        if position_raw is not None:
            try:
                pos = int(position_raw)
                pos = pos / 1000.0 if pos > 100000 else float(pos)
                if pos >= 0: position_seconds = pos
            except Exception: position_seconds = None

        return cls(
            title=title,
            artists=artists or "Unknown",
            album=entry.get("album", ""),
            cover_id=entry.get("coverArt") or entry.get("coverId", ""),
            duration=duration if duration and duration > 0 else None,
            position=position_seconds,
            minutes_ago=entry.get("minutesAgo"),
        )

    def key(self) -> Tuple[str, str, str, str]:
        """Unique key for cache/comparison."""
        return (self.title, self.artists, self.album, self.cover_id)


# -------------------------
# Client Class
# -------------------------
class NavidromeClient:
    """Handles communication with Navidrome and Imgur."""
    
    def __init__(self, nav_config: NavidromeConfig, img_config: ImageConfig, imgur_client_id: str):
        self.nav_config = nav_config
        self.img_config = img_config
        self.imgur_client_id = imgur_client_id
        self.nav_params = {
            "u": nav_config.username,
            "p": nav_config.password,
            "v": "1.16.1",
            "c": "nav-rpc",
            "f": "json"
        }
        self.session = get_session()

    def _nav_request(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Handles Navidrome API calls with path suffix fallback."""
        url = f"{self.nav_config.base_url}/{endpoint}"
        try:
            r = self.session.get(url, params=self.nav_params, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception:
            try:
                # Subsonic APIs often use a .view suffix
                url_view = f"{self.nav_config.base_url}/{endpoint}.view"
                r = self.session.get(url_view, params=self.nav_params, timeout=5)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                log(f"Navidrome request failed for {endpoint}: {e}")
                return None

    def get_now_playing(self) -> Optional[TrackInfo]:
        """Polls Navidrome for the currently playing track."""
        data = self._nav_request("getNowPlaying")
        now_playing = data.get("subsonic-response", {}).get("nowPlaying") if data else None
        return TrackInfo.from_json(now_playing)

    def _download_cover_image(self, cover_id: str) -> Optional[bytes]:
        """Downloads cover image bytes."""
        if not cover_id: return None
        params = {"id": cover_id, **{k: self.nav_params[k] for k in ('u', 'p', 'v', 'c')}}
        
        for suffix in ("getCoverArt", "getCoverArt.view"):
            try:
                r = self.session.get(f"{self.nav_config.base_url}/{suffix}", params=params, timeout=8)
                r.raise_for_status()
                return r.content
            except Exception:
                continue
        return None

    def _optimize_image(self, image_bytes: bytes) -> Optional[bytes]:
        """Resizes and compresses an image using Pillow."""
        if not image_bytes: return None
        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != 'RGB': img = img.convert('RGB')
            
            max_size = (self.img_config.max_size, self.img_config.max_size)
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                log(f"Resized image to {img.width}x{img.height}")
            
            output_buffer = io.BytesIO()
            img.save(output_buffer, format="JPEG", quality=self.img_config.jpeg_quality, optimize=True)
            optimized_bytes = output_buffer.getvalue()
            
            if len(optimized_bytes) > self.img_config.max_file_bytes:
                log(f"Optimized image is still too large ({len(optimized_bytes)/(1024*1024):.2f}MB).")
                return None
            return optimized_bytes
        except Exception as e:
            log(f"Error optimizing image: {e}")
            return None

    def _upload_imgur(self, image_bytes: bytes) -> Optional[str]:
        """Uploads image bytes to Imgur."""
        if not image_bytes or not self.imgur_client_id: return None
        try:
            headers = {"Authorization": f"Client-ID {self.imgur_client_id}"}
            data = {"image": base64.b64encode(image_bytes).decode("ascii")}
            r = self.session.post("https://api.imgur.com/3/image", headers=headers, data=data, timeout=15)
            r.raise_for_status()
            payload = r.json()
            if payload.get("success"):
                return payload["data"]["link"]
        except Exception as e:
            log(f"Imgur upload failed: {e}")
        return None

    def get_or_upload_cover(self, track: TrackInfo, cache: Dict[str, str]) -> Optional[str]:
        """Checks cache, downloads, optimizes, uploads, and saves to cache."""
        if not track.album or not track.cover_id:
            return None
        
        # 1. Check Cache
        if track.album in cache:
            return cache[track.album]

        # 2. Download
        log("Downloading cover art...")
        img_bytes = self._download_cover_image(track.cover_id)
        if not img_bytes:
            log("Could not download cover art from Navidrome.")
            return None

        # 3. Optimize
        log(f"Original image size: {len(img_bytes) / (1024*1024):.2f}MB")
        optimized_img_bytes = self._optimize_image(img_bytes)
        if not optimized_img_bytes:
            log("Image optimization failed.")
            return None
        
        log(f"Optimized image size: {len(optimized_img_bytes) / (1024*1024):.2f}MB")

        # 4. Upload
        log("Attempting to upload cover art to Imgur...")
        imgur_url = self._upload_imgur(optimized_img_bytes)
        
        # 5. Cache and Return
        if imgur_url:
            cache[track.album] = imgur_url
            log(f"Uploaded and cached: {imgur_url}")
        else:
            log("Imgur upload failed.")
            
        return imgur_url
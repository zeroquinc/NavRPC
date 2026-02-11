import base64
import io
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image

from .config import NavidromeConfig, ImageConfig
from .logger import get_logger

logger = get_logger()

_SESSION: Optional[requests.Session] = None

def get_session() -> requests.Session:
    """Create and return a cached requests.Session with retries."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        # Retry strategy: exponential backoff for rate limits and server errors
        retry_strategy = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        _SESSION.mount("http://", adapter)
        _SESSION.mount("https://", adapter)
    return _SESSION

_REQUEST_COUNT = 0

def _increment_request_count():
    """Track requests for debugging."""
    global _REQUEST_COUNT
    _REQUEST_COUNT += 1

def get_request_count() -> int:
    """Get total requests made (for debugging)."""
    return _REQUEST_COUNT

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
    is_single: bool = False

    @classmethod
    def from_json(cls, np_json: Optional[dict], track_comment: bool = False, album_version: bool = False) -> Optional["TrackInfo"]:
        # Simplified the parsing, assuming standard Navidrome output structure
        if not np_json:
            return None
        
        entry = np_json.get("entry", {})
        if isinstance(entry, list) and entry:
             entry = entry[0]
        
        if not isinstance(entry, dict):
            return None

        # Get title with or without subtitle based on config
        raw_title = entry.get("title") or entry.get("name", "")
        
        if track_comment:
            # Keep full title including subtitle/comment
            title = raw_title
        else:
            # Strip subtitle: sortName contains the plain title without subtitle (but lowercase)
            sort_name = entry.get("sortName", "").strip()
            
            if sort_name:
                # Use sortName but preserve the original capitalization from title
                # by extracting the matching part from the full title
                title_lower = raw_title.lower()
                if title_lower.startswith(sort_name):
                    # Extract the properly capitalized version
                    title = raw_title[:len(sort_name)].strip()
                else:
                    # Fallback: capitalize each word in sortName
                    title = sort_name.title()
            else:
                title = raw_title
        
        # Use the artists array which contains the proper artist information
        artist_entries = entry.get("artists", [])
        if artist_entries:
            artists = ", ".join(a["name"] for a in artist_entries if isinstance(a, dict) and "name" in a)
        else:
            # Fallback to albumArtists if no artists are specified
            album_artists = entry.get("albumArtists", [])
            artists = ", ".join(a["name"] for a in album_artists if isinstance(a, dict) and "name" in a) if album_artists else "Unknown"
        duration = int(entry.get("duration", 0)) if entry.get("duration") else None
        position_raw = entry.get("position", entry.get("elapsed"))
        position_seconds = None
        if position_raw is not None:
            try:
                pos = int(position_raw)
                pos = pos / 1000.0 if pos > 100000 else float(pos)
                if pos >= 0: position_seconds = pos
            except Exception: position_seconds = None

        # Get album with or without version based on config
        raw_album = entry.get("album", "")
        album_comment = entry.get("_albumComment", "")
        
        if album_version and album_comment:
            # Append the album version/edition in parentheses
            album = f"{raw_album} ({album_comment})"
        else:
            album = raw_album

        return cls(
            title=title,
            artists=artists or "Unknown",
            album=album,
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
    
    def __init__(self, nav_config: NavidromeConfig, img_config: ImageConfig, imgur_client_id: str, track_comment: bool = False, album_version: bool = False, request_timeout: float = 5.0, album_cache_file: str = "album_cache.json"):
        self.nav_config = nav_config
        self.img_config = img_config
        self.imgur_client_id = imgur_client_id
        self.track_comment = track_comment
        self.album_version = album_version
        self.request_timeout = request_timeout
        self.album_cache_file = album_cache_file
        self.nav_params = {
            "u": nav_config.username,
            "p": nav_config.password,
            "v": "1.16.1",
            "c": "nav-rpc",
            "f": "json"
        }
        self.session = get_session()
        self._album_version_cache: Dict[str, str] = self._load_album_cache()  # Load persistent cache
        self._album_release_types_cache: Dict[str, Optional[Tuple[str, ...]]] = {}
        self._image_data_cache: Dict[str, bytes] = {}  # In-memory cache for image data

    def _load_album_cache(self) -> Dict[str, str]:
        """Load persistent album version cache from disk."""
        import os
        if not os.path.exists(self.album_cache_file):
            return {}
        try:
            import json
            with open(self.album_cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load album cache: {e}")
            return {}

    def _save_album_cache(self):
        """Save persistent album version cache to disk."""
        import json
        try:
            with open(self.album_cache_file, "w", encoding="utf-8") as f:
                json.dump(self._album_version_cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save album cache: {e}")

    def _nav_request(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Handles Navidrome API calls with path suffix fallback."""
        _increment_request_count()
        url = f"{self.nav_config.base_url}/{endpoint}"
        try:
            r = self.session.get(url, params=self.nav_params, timeout=self.request_timeout)
            r.raise_for_status()
            return r.json()
        except Exception:
            try:
                # Subsonic APIs often use a .view suffix
                url_view = f"{self.nav_config.base_url}/{endpoint}.view"
                r = self.session.get(url_view, params=self.nav_params, timeout=self.request_timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                logger.error(f"Navidrome request failed for {endpoint}: {e}")
                return None

    def get_now_playing(self) -> Optional[TrackInfo]:
        """Polls Navidrome for the currently playing track."""
        data = self._nav_request("getNowPlaying")
        now_playing = data.get("subsonic-response", {}).get("nowPlaying") if data else None
        entry = None

        if now_playing:
            entry = now_playing.get("entry", {})
            if isinstance(entry, list) and entry:
                entry = entry[0]
            if not isinstance(entry, dict):
                entry = None
        
        # If we want to include album version, fetch album details (with caching)
        if now_playing and self.album_version and entry:
                album_id = entry.get("albumId")
                if album_id:
                    # Check cache first
                    if album_id in self._album_version_cache:
                        album_subtitle = self._album_version_cache[album_id]
                        if album_subtitle:
                            entry["_albumComment"] = album_subtitle
                    else:
                        # Fetch and cache album info
                        album_info = self._get_album_info(album_id)
                        if album_info:
                            # Try to get album version/subtitle (could be in 'version' field)
                            album_subtitle = album_info.get("version", "") or album_info.get("comment", "")
                            self._album_version_cache[album_id] = album_subtitle  # Cache it
                            self._save_album_cache()  # Persist to disk
                            if album_subtitle:
                                entry["_albumComment"] = album_subtitle
        
        track = TrackInfo.from_json(now_playing, track_comment=self.track_comment, album_version=self.album_version)
        if track and entry:
            track.is_single = self._is_single_track(track, entry)
        return track

    def _is_single_track(self, track: TrackInfo, entry: Dict[str, Any]) -> bool:
        if not track.title or not track.album:
            return False

        if track.title.strip().casefold() != track.album.strip().casefold():
            return False

        album_id = entry.get("albumId")
        if not album_id:
            return False

        if album_id in self._album_release_types_cache:
            release_types = self._album_release_types_cache[album_id]
        else:
            album_info = self._get_album_info(album_id)
            release_types = None
            if album_info:
                raw_release_types = (
                    album_info.get("releaseTypes")
                    or album_info.get("releaseType")
                    or album_info.get("release_type")
                )
                if isinstance(raw_release_types, str):
                    release_types = (raw_release_types,)
                elif isinstance(raw_release_types, (list, tuple)):
                    release_types = tuple(str(item) for item in raw_release_types if item is not None)
            self._album_release_types_cache[album_id] = release_types

        if release_types:
            return any(rt.strip().casefold() == "single" for rt in release_types)

        album_info = self._get_album_info(album_id)
        if not album_info:
            return False

        raw_count = (
            album_info.get("songCount")
            or album_info.get("songcount")
            or album_info.get("song_count")
        )
        try:
            song_count = int(raw_count) if raw_count is not None else None
        except Exception:
            song_count = None

        return song_count == 1

    def _get_album_info(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Fetches album details by album ID."""
        _increment_request_count()
        url = f"{self.nav_config.base_url}/getAlbum"
        params = {**self.nav_params, "id": album_id}
        try:
            r = self.session.get(url, params=params, timeout=self.request_timeout)
            r.raise_for_status()
            data = r.json()
            album = data.get("subsonic-response", {}).get("album", {})
            return album
        except Exception as e:
            logger.error(f"Failed to fetch album info: {e}")
            return None

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
                logger.info(f"Resized image to {img.width}x{img.height}")
            
            output_buffer = io.BytesIO()
            img.save(output_buffer, format="JPEG", quality=self.img_config.jpeg_quality, optimize=True)
            optimized_bytes = output_buffer.getvalue()
            
            if len(optimized_bytes) > self.img_config.max_file_bytes:
                logger.warning(f"Optimized image is still too large ({len(optimized_bytes)/(1024*1024):.2f}MB).")
                return None
            return optimized_bytes
        except Exception as e:
            logger.error(f"Error optimizing image: {e}")
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
            logger.error(f"Imgur upload failed: {e}")
        return None

    def get_or_upload_cover(self, track: TrackInfo, cache: Dict[str, str]) -> Tuple[Optional[str], Optional[bytes]]:
        """
        Checks cache, downloads, optimizes, uploads, and saves to cache.
        Returns tuple of (imgur_url, optimized_image_bytes)
        """
        if not track.album or not track.cover_id:
            return None, None
        
        # 1. Check URL Cache
        imgur_url = cache.get(track.album)
        
        # 2. Check if we have cached image data
        if track.album in self._image_data_cache:
            logger.info(f"Using cached image data for: {track.album}")
            return imgur_url, self._image_data_cache[track.album]
        
        if imgur_url:
            # URL is cached but we don't have image data - try to get it
            logger.info(f"Album art URL cached: {imgur_url}")
            # Download the image from Navidrome to get the data
            img_bytes = self._download_cover_image(track.cover_id)
            if img_bytes:
                optimized_img_bytes = self._optimize_image(img_bytes)
                if optimized_img_bytes:
                    self._image_data_cache[track.album] = optimized_img_bytes
                    return imgur_url, optimized_img_bytes
            return imgur_url, None

        # 3. Download from Navidrome
        logger.info("Downloading cover art...")
        img_bytes = self._download_cover_image(track.cover_id)
        if not img_bytes:
            logger.warning("Could not download cover art from Navidrome.")
            return None, None

        # 4. Optimize
        logger.info(f"Original image size: {len(img_bytes) / (1024*1024):.2f}MB")
        optimized_img_bytes = self._optimize_image(img_bytes)
        if not optimized_img_bytes:
            logger.warning("Image optimization failed.")
            return None, None
        
        logger.info(f"Optimized image size: {len(optimized_img_bytes) / (1024*1024):.2f}MB")

        # 5. Cache image data
        self._image_data_cache[track.album] = optimized_img_bytes

        # 6. Upload to Imgur
        logger.info("Attempting to upload cover art to Imgur...")
        imgur_url = self._upload_imgur(optimized_img_bytes)
        
        # 7. Cache URL
        if imgur_url:
            cache[track.album] = imgur_url
            logger.info(f"Uploaded and cached: {imgur_url}")
        else:
            logger.warning("Imgur upload failed.")
            
        return imgur_url, optimized_img_bytes

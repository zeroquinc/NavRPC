import time
import json
import os
import threading
from typing import Dict, Any, Optional

from .config import Settings
from .client import NavidromeClient
from .discord import DiscordPresence
from .logger import get_logger

logger = get_logger()

# -------------------------
# Cache Management
# -------------------------
def load_cache(file_path: str) -> Dict[str, str]:
    """Loads cache with minimal error handling."""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading cache file: {e}. Starting fresh.")
        return {}

def save_cache(cache: Dict[str, str], file_path: str):
    """Saves cache file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving cache: {e}")

# -------------------------
# Main Execution
# -------------------------
def main_loop(settings: Settings, tray_icon=None):
    """Initializes clients and runs the main polling loop with adaptive intervals."""
    
    # 1. Initialization
    nav_client = NavidromeClient(
        nav_config=settings.navidrome,
        img_config=settings.image,
        imgur_client_id=settings.integration.imgur_client_id,
        track_comment=settings.track_comment,
        album_version=settings.album_version,
        request_timeout=settings.request_timeout,
        album_cache_file=settings.album_cache_file
    )
    
    discord_id = settings.integration.discord_client_id
    cache = load_cache(settings.cache_file)
    last_track_key = None
    poll_interval_playing = settings.poll_interval_playing
    poll_interval_idle = settings.poll_interval_idle
    consecutive_failures = 0
    max_backoff_interval = max(poll_interval_playing, poll_interval_idle) * 3

    if not discord_id:
        logger.error("❌ Please set discord_client_id in config.yaml.")
        return

    logger.info(f"Starting NavRPC polling: {poll_interval_playing}s when playing, {poll_interval_idle}s when idle")

    # 2. Main Loop
    try:
        with DiscordPresence(discord_id) as rpc:
            while True:
                track = nav_client.get_now_playing()

                if not track:
                    if last_track_key is not None:
                        rpc.clear()
                        logger.info("No track playing. Clearing RPC.")
                        if tray_icon:
                            tray_icon.clear_track()
                        consecutive_failures = 0
                    last_track_key = None
                    current_interval = poll_interval_idle
                else:
                    consecutive_failures = 0
                    track_key = track.key()
                    if track_key != last_track_key:
                        logger.info(f"Now playing new track: {track.artists} — {track.title}")
                        
                        # Get/Upload Image (returns both URL and image bytes)
                        imgur_url, image_data = nav_client.get_or_upload_cover(track, cache)
                        save_cache(cache, settings.cache_file)
                        
                        # Update tray with detailed info and image data
                        if tray_icon:
                            tray_icon.update_track(
                                track_info=f"{track.artists} — {track.title}",
                                title=track.title,
                                artist=track.artists,
                                album=track.album,
                                album_art_url=imgur_url,
                                album_art_data=image_data
                            )

                        # Update RPC
                        image_asset = imgur_url or settings.integration.discord_asset_name
                        rpc.update(track, image_asset)

                        last_track_key = track_key
                    
                    current_interval = poll_interval_playing

                # Exponential backoff on consecutive failures
                if track is None and consecutive_failures > 0:
                    backoff_interval = min(2 ** (consecutive_failures - 1) * poll_interval_idle, max_backoff_interval)
                    logger.warning(f"Request failed. Backing off for {backoff_interval}s (attempt {consecutive_failures})")
                    time.sleep(backoff_interval)
                    consecutive_failures += 1
                else:
                    time.sleep(current_interval)
                
    except ConnectionError:
        logger.critical("Fatal error connecting to Discord RPC. Exiting.")
    except KeyboardInterrupt:
        logger.info("Exiting gracefully...")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
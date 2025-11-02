import time
import json
import os
from typing import Dict, Any

from .config import Settings
from .client import NavidromeClient, log
from .discord import DiscordPresence

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
    except Exception:
        log("Error loading cache file. Starting fresh.")
        return {}

def save_cache(cache: Dict[str, str], file_path: str):
    """Saves cache file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        log(f"Error saving cache: {e}")

# -------------------------
# Main Execution
# -------------------------
def main_loop(settings: Settings):
    """Initializes clients and runs the main polling loop."""
    
    # 1. Initialization
    nav_client = NavidromeClient(
        nav_config=settings.navidrome,
        img_config=settings.image,
        imgur_client_id=settings.integration.imgur_client_id,
        strip_title_subtitle=settings.strip_title_subtitle
    )
    
    discord_id = settings.integration.discord_client_id
    cache = load_cache(settings.cache_file)
    last_track_key = None
    poll_interval = settings.poll_interval

    if not discord_id:
        log("❌ Please set discord_client_id in config.yaml.")
        return

    # 2. Main Loop
    try:
        with DiscordPresence(discord_id) as rpc:
            while True:
                track = nav_client.get_now_playing()

                if not track:
                    if last_track_key is not None:
                        rpc.clear()
                        log("No track playing. Clearing RPC.")
                    last_track_key = None
                    time.sleep(poll_interval)
                    continue
                
                track_key = track.key()
                if track_key != last_track_key:
                    log(f"Now playing new track: {track.artists} — {track.title}")
                    
                    # Get/Upload Image
                    imgur_url = nav_client.get_or_upload_cover(track, cache)
                    save_cache(cache, settings.cache_file)

                    # Update RPC
                    image_asset = imgur_url or settings.integration.discord_asset_name
                    rpc.update(track, image_asset)

                    last_track_key = track_key

                time.sleep(poll_interval)
                
    except ConnectionError:
        log("Fatal error connecting to Discord RPC. Exiting.")
    except KeyboardInterrupt:
        log("Exiting gracefully...")
    except Exception as e:
        log(f"An unexpected error occurred: {e}")
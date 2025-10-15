import time
from typing import Optional, Tuple

from pypresence.presence import Presence
from pypresence.types import ActivityType, StatusDisplayType

from .client import TrackInfo, log

# -------------------------
# Discord RPC
# -------------------------
class DiscordPresence:
    """Context manager and updater for Discord RPC."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.rpc = Presence(client_id, pipe=0)
        self.is_connected = False
        self.last_rpc_details: Optional[Tuple] = None

    def __enter__(self):
        try:
            self.rpc.connect()
            self.is_connected = True
            log("Connected to Discord RPC.")
        except Exception as e:
            log(f"Failed to connect to Discord RPC: {e}")
            raise ConnectionError("Discord RPC connection failed.") from e
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.is_connected:
            try:
                self.rpc.clear()
            except Exception:
                pass
            try:
                self.rpc.close()
            except Exception:
                pass

    # Helper: Ensure Discord RPC text fields are valid, we can't have less than 2 characters.
    def _safe_text(self, text: Optional[str], fallback: str = "Navidrome") -> str:
        """Ensures text is at least 2 visible characters long (Discord RPC requirement)."""
        text = text or fallback
        return text if len(text.strip()) >= 2 else text + "\u200B"

    def update(self, track: TrackInfo, image_url: Optional[str]):
        """Calculates timestamps and updates the Rich Presence."""
        if not self.is_connected:
            log("RPC not connected, skipping update.")
            return

        now = time.time()
        start_ts = end_ts = None

        # Calculate Timestamps
        if track.duration:
            if track.minutes_ago is not None:
                estimated_offset = track.minutes_ago * 60
                start_ts = int(now - estimated_offset)
            elif track.position is not None:
                start_ts = int(now - track.position)
            else:
                start_ts = int(now - 3)  # Simple fallback if no position data

            # Basic sanity check
            if start_ts > now:
                start_ts = int(now - track.duration)
            end_ts = int(start_ts + track.duration)

        final_image = image_url or "navidrome_logo"  # Fallback image if needed

        # Apply safe text for all Discord fields
        title = self._safe_text(track.title, "Unknown Title")
        artists = self._safe_text(track.artists, "Unknown Artist")
        album = self._safe_text(track.album, "Navidrome")

        current_rpc_details = (title, artists, album, final_image, start_ts, end_ts)

        if current_rpc_details == self.last_rpc_details:
            return  # Skip redundant updates

        self.rpc.update(
            activity_type=ActivityType.LISTENING,
            status_display_type=StatusDisplayType.STATE,
            details=title,
            state=artists,
            large_text=album,
            large_image=final_image,
            start=start_ts,
            end=end_ts,
        )
        log(f"🎵 RPC Updated: {artists} — {title}")
        self.last_rpc_details = current_rpc_details

    def clear(self):
        """Clears the RPC status."""
        if self.is_connected:
            try:
                self.rpc.clear()
            except Exception:
                pass
            self.last_rpc_details = None

"""MoOde Audio Player client.

Implementation of the MediaPlayer interface for MoOde Audio,
a Raspberry Pi-based music player OS (https://moodeaudio.org).

MoOde exposes playback state via HTTP API endpoint `/engine-mpd.php`.
This implementation uses polling to fetch playback state at regular intervals,
maintaining the same MediaPlayer interface as other clients (Volumio, piCorePlayer).

Supports both MPD playback and AirPlay streaming via shairport-sync.
"""

import os
import time
import json
import logging
import requests
import subprocess
from urllib.parse import urlparse
from media_player import MediaPlayer

logger = logging.getLogger(__name__)

# Default MoOde HTTP API endpoint
MOODE_DEFAULT_URL = "http://localhost/engine-mpd.php"

# Minimum interval (seconds) between HTTP polls to avoid excessive API load.
# Main loop may call receive_message() frequently (~10 times/second with 0.1s timeout),
# but we throttle actual HTTP requests to this interval.
MIN_POLL_INTERVAL = 1.0

# Shairport-sync metadata file location (AirPlay)
SHAIRPORT_METADATA_FILE = "/tmp/shairport-sync-metadata"


class MoodeClient(MediaPlayer):
    """MediaPlayer implementation for MoOde Audio using HTTP polling.

    MoOde doesn't provide real-time WebSocket updates like Volumio, so this
    client polls the `/engine-mpd.php` endpoint periodically. The connection
    interface remains compatible with other MediaPlayer implementations.

    The polling is passive and on-demand: state is fetched when receive_message()
    is called, avoiding constant network requests while maintaining interface
    consistency.
    """

    def __init__(self, url: str = MOODE_DEFAULT_URL) -> None:
        """Initialize MoOde client.

        Args:
            url: HTTP endpoint for MoOde API (default: http://localhost/engine-mpd.php)
        """
        self.url = url
        self._connected = False
        self._last_state: dict | None = None
        self._last_poll_time: float = 0.0  # Track time of last HTTP poll
        self._base_url = self._extract_base_url(url)

    def _extract_base_url(self, url: str) -> str:
        """Extract base URL from full API endpoint.

        Args:
            url: Full endpoint URL (e.g., http://localhost/engine-mpd.php)

        Returns:
            Base URL for relative paths (e.g., http://localhost)
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _is_airplay_active(self) -> bool:
        """Check if shairport-sync (AirPlay) is currently streaming audio.

        Detects active AirPlay playback by checking ALSA playback status
        on the USB audio device.

        Returns:
            True if audio is actively playing via AirPlay, False otherwise.
        """
        try:
            # Check if shairport-sync process is running
            result = subprocess.run(
                ["pgrep", "-f", "shairport-sync"],
                capture_output=True,
                timeout=1
            )
            if result.returncode != 0:
                return False  # shairport-sync not running

            # Check ALSA stream status for USB audio device
            # Look for "Status: Running" in card0/stream0
            try:
                with open("/proc/asound/card0/stream0", "r") as f:
                    content = f.read()
                    if "Status: Running" in content:
                        return True
            except (FileNotFoundError, IOError):
                pass

            return False
        except Exception as e:
            logger.debug(f"Error checking AirPlay status: {e}")
            return False

    def _get_airplay_metadata(self) -> dict | None:
        """Read metadata from shairport-sync for currently playing AirPlay stream.

        Shairport-sync writes metadata to /tmp/shairport-sync-metadata in a
        special format. Parse it to extract artist, title, album, etc.

        Returns:
            Dictionary with parsed metadata (title, artist, album) or None
            if metadata file is not available or empty.
        """
        try:
            if not os.path.exists(SHAIRPORT_METADATA_FILE):
                return None

            with open(SHAIRPORT_METADATA_FILE, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()

            if not content:
                return None

            # Parse shairport-sync metadata format: key=value pairs
            metadata = {}
            for line in content.split("\n"):
                line = line.strip()
                if not line or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip().lower()
                value = value.strip()

                # Map shairport keys to our standard schema
                if key == "artist":
                    metadata["artist"] = value
                elif key == "title":
                    metadata["title"] = value
                elif key == "album":
                    metadata["album"] = value
                elif key == "songalbumartist":
                    metadata["albumartist"] = value

            return metadata if metadata else None
        except Exception as e:
            logger.debug(f"Error reading AirPlay metadata: {e}")
            return None

    def connect(self) -> bool:
        """Test connection to MoOde HTTP API.

        Performs a single request to verify the endpoint is reachable.

        Returns:
            True if connection was successful, False otherwise.
        """
        try:
            response = requests.get(self.url, timeout=3)
            response.raise_for_status()
            # Verify response is valid JSON
            response.json()
            self._connected = True
            self._last_poll_time = 0.0  # Reset to allow immediate first poll
            logger.info(f"Connected to MoOde at {self.url}")
            return True
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Error connecting to MoOde at {self.url}: {e}")
            self._connected = False
            return False

    def receive_message(self, timeout: float = 1.0) -> dict | None:
        """Poll MoOde for current playback state.

        Fetches the current state from the MoOde API and returns it only if
        it differs from the last polled state (change detection). Automatically
        rate-limits HTTP requests to avoid excessive API load even when called
        frequently by the main loop.

        Args:
            timeout: Timeout in seconds for the HTTP request.

        Returns:
            A state dictionary when playback state has changed, or None if
            unchanged or unreachable. Returns None if not connected or if
            minimum poll interval has not elapsed to rate-limit API requests.
        """
        if not self._connected:
            return None

        # Rate-limit: only poll HTTP API if minimum interval has elapsed
        # Main loop may call this ~10 times/second, but we throttle actual
        # network requests to avoid unnecessary load on MoOde API.
        now = time.time()
        if now - self._last_poll_time < MIN_POLL_INTERVAL:
            return None
        
        self._last_poll_time = now

        try:
            response = requests.get(self.url, timeout=timeout)
            response.raise_for_status()
            state = response.json()
            
            # Convert MoOde fields to standard MediaPlayer state format
            normalized_state = self._normalize_state(state)
            
            # Only return state if it changed
            if normalized_state != self._last_state:
                self._last_state = normalized_state
                return normalized_state
            
            return None
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.debug(f"Error polling MoOde: {e}")
            return None

    def _normalize_state(self, raw_state: dict) -> dict:
        """Convert MoOde API response to standard playback state format.

        Maps MoOde-specific fields to the common state schema used by all
        MediaPlayer implementations.

        Args:
            raw_state: Raw JSON response from MoOde API.

        Returns:
            Normalized state dictionary ready for display/rendering.
        """
        # Extract and convert numeric fields
        elapsed = raw_state.get("elapsed")
        seek = None
        if elapsed is not None:
            try:
                # MoOde reports elapsed time in seconds; normalize to milliseconds
                # to match Volumio/app schema used by renderer and seek interpolation
                elapsed_seconds = float(elapsed)
                seek = int(elapsed_seconds * 1000)
            except (ValueError, TypeError):
                pass

        time = raw_state.get("time")
        duration = None
        if time is not None:
            try:
                # MoOde reports duration in seconds; normalize to milliseconds
                # to match Volumio/app schema
                duration_seconds = float(time)
                duration = int(duration_seconds * 1000)
            except (ValueError, TypeError):
                pass

        # Convert MoOde status to standard format
        status = raw_state.get("state", "stop")
        if status not in ["play", "pause", "stop"]:
            status = "stop"

        # Override status if AirPlay is actively streaming
        # (MPD reports "stop" when playing via AirPlay, not its queue)
        airplay_metadata = None
        if status == "stop" and self._is_airplay_active():
            logger.debug("AirPlay streaming detected, overriding MPD 'stop' status to 'play'")
            status = "play"
            # Try to get actual metadata from AirPlay stream
            airplay_metadata = self._get_airplay_metadata()
            if airplay_metadata:
                logger.debug(f"Using AirPlay metadata: {airplay_metadata}")

        # Build album artwork URL (relative path needs base URL)
        coverurl = raw_state.get("coverurl")
        albumart = None
        if coverurl and coverurl != "/images/default-album-cover.png":
            albumart = f"{self._base_url}{coverurl}" if coverurl.startswith("/") else coverurl

        # Extract quality info from bitrate and encoded fields
        bitrate = raw_state.get("bitrate", "")
        encoded = raw_state.get("encoded", "")
        quality = None
        if encoded:
            quality = encoded
        elif bitrate and bitrate != "0 bps":
            quality = bitrate

        # Use AirPlay metadata if available, otherwise fall back to MPD metadata
        if airplay_metadata:
            return {
                "title": airplay_metadata.get("title", ""),
                "artist": airplay_metadata.get("artist", ""),
                "album": airplay_metadata.get("album", ""),
                "albumart": albumart,
                "status": status,
                "seek": seek,
                "duration": duration,
                "quality": quality,
                "volume": int(raw_state.get("volume", 100)),
            }
        else:
            return {
                "title": raw_state.get("title", ""),
                "artist": raw_state.get("artist", ""),
                "album": raw_state.get("album", ""),
                "albumart": albumart,
                "status": status,
                "seek": seek,
                "duration": duration,
                "quality": quality,
                "volume": int(raw_state.get("volume", 100)),
            }

    def is_connected(self) -> bool:
        """Check if currently connected to MoOde.

        Returns:
            True if the connection test passed, False otherwise.
        """
        return self._connected

    def close(self) -> None:
        """Close the connection to MoOde (cleanup).

        No persistent connection to close, but resets internal state.
        """
        self._connected = False
        self._last_state = None
        self._last_poll_time = 0.0

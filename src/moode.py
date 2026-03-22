"""MoOde Audio Player client.

Implementation of the MediaPlayer interface for MoOde Audio,
a Raspberry Pi-based music player OS (https://moodeaudio.org).

MoOde exposes playback state via HTTP API endpoint `/engine-mpd.php`.
This implementation uses polling to fetch playback state at regular intervals,
maintaining the same MediaPlayer interface as other clients (Volumio, piCorePlayer).

Supports both MPD playback and AirPlay streaming via shairport-sync, Bluetooth, UPnP, etc.
Uses multi-layered detection strategy for streaming renderer detection.
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

# Metadata file cache: track last modification time to detect updates
_METADATA_CACHE = {"mtime": 0, "data": None}


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

    def _check_shairport_running(self) -> bool:
        """Check if shairport-sync process is running.
        
        Returns:
            True if process is found, False otherwise.
        """
        try:
            result = subprocess.run(
                ["pgrep", "-f", "shairport-sync"],
                capture_output=True,
                timeout=1
            )
            is_running = result.returncode == 0
            logger.debug(f"Shairport-sync process check: {'running' if is_running else 'not found'}")
            return is_running
        except Exception as e:
            logger.debug(f"Error checking shairport-sync process: {e}")
            return False

    def _check_alsa_audio_active(self) -> bool:
        """Check if ALSA is actively playing audio.
        
        Looks for "Status: Running" in ALSA stream information, which indicates
        active audio playback at the hardware level (device-independent).
        
        Returns:
            True if audio is actively playing, False otherwise.
        """
        try:
            # Try multiple ALSA card/stream combinations to handle different devices
            for card in range(5):  # Check cards 0-4
                for stream in range(2):  # Playback (0) and Capture (1)
                    path = f"/proc/asound/card{card}/stream{stream}"
                    if not os.path.exists(path):
                        continue
                    
                    try:
                        with open(path, "r") as f:
                            content = f.read()
                            if "Status: Running" in content:
                                logger.debug(f"ALSA audio active on card{card}/stream{stream}")
                                return True
                    except (IOError, OSError):
                        continue
            
            logger.debug("ALSA: no active audio streams detected")
            return False
        except Exception as e:
            logger.debug(f"Error checking ALSA status: {e}")
            return False

    def _check_metadata_file_active(self) -> bool:
        """Check if shairport-sync metadata FIFO exists and is accessible.
        
        Note: Shairport-sync writes metadata to a FIFO (named pipe), not a regular file.
        We can only verify the FIFO exists; mtime checks don't work reliably on FIFOs
        since they report the creation time, not the last-write time.
        
        Returns:
            True if metadata FIFO exists and is readable.
        """
        try:
            if not os.path.exists(SHAIRPORT_METADATA_FILE):
                logger.debug(f"Metadata FIFO not found: {SHAIRPORT_METADATA_FILE}")
                return False
            
            # FIFO exists; consider it potentially active if it's a FIFO/pipe
            mode = os.stat(SHAIRPORT_METADATA_FILE).st_mode
            is_fifo = os.path.isfifo(SHAIRPORT_METADATA_FILE)
            logger.debug(f"Metadata FIFO exists (is_fifo={is_fifo})")
            return is_fifo
        except Exception as e:
            logger.debug(f"Error checking metadata FIFO: {e}")
            return False

    def _is_streaming_renderer_active(self) -> bool:
        """Detect if audio is streaming from shairport-sync (AirPlay).
        
        Uses dual-layer detection specifically for AirPlay via shairport-sync:
        1. Shairport-sync process is running (necessary condition for AirPlay)
        2. ALSA shows active audio playback (hardware-level confirmation)
        
        Both indicators must be true for confident detection. This avoids false
        positives from shairport running idle and false negatives from ALSA glitches.
        
        Note: Metadata file (FIFO) can't be reliably checked for freshness since
        mtime reports creation time, not last-write time. We rely on the other two.
        
        Note: This detects AirPlay/shairport-sync streaming. Bluetooth and UPnP
        streams use different mechanisms (BlueZ, UPnP renderers) not covered here.
        For MoOde, AirPlay is the primary streaming renderer of interest.
        
        Returns:
            True if AirPlay streaming via shairport-sync is detected, False otherwise.
        """
        logger.info("=== Streaming Renderer Detection ===")
        shairport_running = self._check_shairport_running()
        alsa_active = self._check_alsa_audio_active()
        
        # Both must be true: shairport running AND ALSA showing audio
        # (Avoids false positives from idle shairport, false negatives from ALSA glitch)
        is_active = shairport_running and alsa_active
        
        logger.info(f"Indicators: shairport={shairport_running}, alsa={alsa_active} => {is_active}")
        
        return is_active

    def _get_airplay_metadata(self) -> dict | None:
        """Read metadata from shairport-sync for currently playing stream.

        Shairport-sync writes metadata to /tmp/shairport-sync-metadata in a
        key=value format. This method parses it and caches the result to avoid
        re-parsing on every call.

        Supported metadata keys from shairport-sync:
        - artist, title, album, songalbumartist, artwork

        Returns:
            Dictionary with parsed metadata (title, artist, album) or None
            if metadata file is not available or empty.
        """
        try:
            if not os.path.exists(SHAIRPORT_METADATA_FILE):
                logger.debug(f"Metadata file does not exist: {SHAIRPORT_METADATA_FILE}")
                _METADATA_CACHE["data"] = None
                return None

            # Check if file was modified since last read
            try:
                mtime = os.path.getmtime(SHAIRPORT_METADATA_FILE)
                if mtime == _METADATA_CACHE["mtime"] and _METADATA_CACHE["data"] is not None:
                    # File hasn't changed, return cached data
                    return _METADATA_CACHE["data"]
            except OSError:
                pass

            with open(SHAIRPORT_METADATA_FILE, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()

            if not content:
                logger.debug("Metadata file is empty")
                _METADATA_CACHE["data"] = None
                return None

            # Parse shairport-sync metadata format: key=value pairs
            metadata = {}
            lines_parsed = 0
            for line in content.split("\n"):
                line = line.strip()
                if not line or "=" not in line:
                    continue

                try:
                    key, value = line.split("=", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    # Map shairport keys to our standard schema
                    if key == "artist" and value:
                        metadata["artist"] = value
                    elif key == "title" and value:
                        metadata["title"] = value
                    elif key == "album" and value:
                        metadata["album"] = value
                    elif key == "songalbumartist" and value:
                        metadata["albumartist"] = value
                    
                    lines_parsed += 1
                except (ValueError, AttributeError) as e:
                    logger.debug(f"Error parsing metadata line '{line}': {e}")
                    continue

            if metadata:
                logger.debug(f"Parsed metadata from file ({lines_parsed} lines): {metadata}")
                # Update cache
                try:
                    _METADATA_CACHE["mtime"] = os.path.getmtime(SHAIRPORT_METADATA_FILE)
                except OSError:
                    _METADATA_CACHE["mtime"] = 0
                _METADATA_CACHE["data"] = metadata
                return metadata
            else:
                logger.debug(f"Metadata file has no valid entries ({lines_parsed} lines parsed)")
                _METADATA_CACHE["data"] = None
                return None
                
        except Exception as e:
            logger.debug(f"Error reading metadata file: {e}")
            _METADATA_CACHE["data"] = None
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
        MediaPlayer implementations. Includes sophisticated handling for
        streaming renderers (AirPlay, Bluetooth, UPnP) where MPD reports
        "stop" because it's not managing the current playback.

        Args:
            raw_state: Raw JSON response from MoOde API.

        Returns:
            Normalized state dictionary ready for display/rendering.
        """
        logger.debug(f"_normalize_state: Processing state - status={raw_state.get('state')}, "
                    f"title={raw_state.get('title')}, current_song_path={raw_state.get('file')}")
        
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

        # Detect if a streaming renderer (AirPlay, Bluetooth, UPnP) is active
        # When streaming via renderer, MPD reports "state":"stop" because it's not
        # managing the playback. We need to detect this and override the status.
        streaming_active = False
        airplay_metadata = None
        
        if status == "stop":
            logger.info("MPD status is 'stop', checking for active streaming renderer...")
            
            # Use multi-layered detection
            streaming_active = self._is_streaming_renderer_active()
            
            if streaming_active:
                logger.info("✓ Streaming renderer detected, overriding status: stop -> play")
                status = "play"
                
                # Try to get metadata from the streaming source
                airplay_metadata = self._get_airplay_metadata()
                if airplay_metadata:
                    logger.info(f"✓ Using streaming metadata: {airplay_metadata}")
                else:
                    logger.info("⚠ Streaming detected but no metadata available yet")
            else:
                logger.info("✗ No streaming renderer detected, keeping status as stop")

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

        # Use streaming metadata if available, otherwise fall back to MPD metadata
        final_state = {
            "title": (airplay_metadata.get("title") if airplay_metadata else None) or raw_state.get("title", ""),
            "artist": (airplay_metadata.get("artist") if airplay_metadata else None) or raw_state.get("artist", ""),
            "album": (airplay_metadata.get("album") if airplay_metadata else None) or raw_state.get("album", ""),
            "albumart": albumart,
            "status": status,
            "seek": seek,
            "duration": duration,
            "quality": quality,
            "volume": int(raw_state.get("volume", 100)),
        }
        
        logger.debug(f"_normalize_state result: status={final_state['status']}, "
                    f"title={final_state['title']}, artist={final_state['artist']}")
        
        return final_state

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

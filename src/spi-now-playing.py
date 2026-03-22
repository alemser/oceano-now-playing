#!/usr/bin/env python3
import time
import signal
import sys
import logging
import threading
from urllib.parse import urlparse
from renderer import Renderer
from media_player import MediaPlayer
from volumio import VolumioClient
from config import Config

# --- LOGGING CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global State
last_state = None
last_rendered_state = None
last_rendered_mode = None # Tracks if last render was cover or text
last_active_time = time.time()
last_cycle_time = time.time()
last_sync_time = 0
last_render_time = 0
last_volumio_timestamp = 0 # Local timestamp when pushState was received
last_volumio_seek = 0      # Seek value from Volumio at that timestamp
is_sleeping = False
is_showing_idle = False    # Tracks if idle screen is currently displayed

# Global objects
config = None
renderer = None
volumio = None


def _connect_with_timeout(client: MediaPlayer, timeout: float = 3.0) -> bool:
    """Connect to a media player with enforced timeout.

    Uses threading to enforce a hard timeout on the connect() call, preventing
    long blocking waits if a service is not responding (e.g., 10s WebSocket
    timeout on Volumio when the service is down).

    Args:
        client: The MediaPlayer instance to connect.
        timeout: Maximum seconds to wait for connection. Defaults to 3 seconds.

    Returns:
        True if connection succeeded within the timeout, False otherwise.
    """
    result = {"connected": False}

    def connect_thread():
        try:
            result["connected"] = client.connect()
        except Exception as e:
            logger.debug(f"Connect thread exception: {e}")
            result["connected"] = False

    thread = threading.Thread(target=connect_thread, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    # If thread is still alive, the connect() call exceeded the timeout
    if thread.is_alive():
        logger.debug(f"Connect timed out after {timeout}s")
        return False

    return result["connected"]


def auto_detect_media_player(cfg: Config) -> MediaPlayer:
    """Auto-detect and instantiate the correct media player client.

    Attempts to connect to each supported media player in sequence with a
    timeout. Returns the first player that responds successfully.

    Currently only Volumio is auto-detected via WebSocket probing. MoOde and
    piCorePlayer stubs are not included in auto-detection until their connect()
    methods are implemented.

    Probing order:
        1. Volumio (ws://localhost:3000)

    Args:
        cfg: Configuration object with media player URLs.

    Returns:
        A concrete :class:`MediaPlayer` instance with probe connection closed,
        ready to be connected again in main(), or VolumioClient as fallback
        if detection fails.

    Note:
        Each probe has a 3-second timeout. Future implementations of MoOde and
        piCorePlayer clients can be added to the candidates list once their
        connect() methods are functional.
    """
    logger.info("Auto-detecting media player...")
    
    # Only Volumio is currently implemented for auto-detection.
    # MoOde and piCorePlayer clients are stubs (connect() returns False),
    # so they are omitted from the candidates list to avoid wasting time
    # probing services that can never be detected until their implementations
    # are completed.
    candidates = [
        ('volumio', cfg.volumio_url, VolumioClient),
        # TODO: Add MoOde once MoodeClient.connect() is implemented
        # TODO: Add piCorePlayer once PiCorePlayerClient.connect() is implemented
    ]
    
    for name, url, client_factory in candidates:
        try:
            logger.info(f"Probing {name} at {url}...")
            client = client_factory(url)
            
            # Try to connect with 3-second timeout
            if _connect_with_timeout(client, timeout=3.0):
                logger.info(f"✓ Auto-detected: {name.upper()} is running")
                
                # Close the probe connection so the caller can establish
                # a single long-lived connection later without leaking sockets.
                try:
                    disconnect_fn = getattr(client, "disconnect", None)
                    if callable(disconnect_fn):
                        disconnect_fn()
                    else:
                        # Fallback: close underlying WebSocket if exposed
                        ws = getattr(client, "ws", None)
                        if ws is not None:
                            try:
                                ws.close()
                            finally:
                                setattr(client, "ws", None)
                except Exception as disconnect_error:
                    logger.debug(
                        f"Failed to close probe connection for {name}: "
                        f"{disconnect_error}"
                    )
                
                return client
            else:
                logger.info(f"✗ {name} returned False (not running)")
        except Exception as e:
            logger.debug(f"✗ {name} probe failed: {e}")
    
    # Fallback: use Volumio as default
    logger.warning("No media player detected. Falling back to Volumio.")
    return VolumioClient(cfg.volumio_url)


def detect_media_player(cfg: Config) -> MediaPlayer:
    """Detect and instantiate the correct media player client.

    If MEDIA_PLAYER is set to 'auto', attempts auto-detection by probing
    Volumio. Otherwise uses the explicitly configured player.

    Args:
        cfg: Configuration object specifying which media player to use.

    Supported values for MEDIA_PLAYER:
        - ``auto``     — Auto-detect (probe Volumio only; MoOde/piCore need implementation)
        - ``volumio``  — Volumio (default if not set)
        - ``moode``    — MoOde Audio
        - ``picore``   — piCorePlayer / LMS

    Returns:
        A concrete :class:`MediaPlayer` instance ready to be connected.
        On auto-detection, updates cfg.media_player_type with the detected value.
    """
    player_type = cfg.media_player_type
    logger.info(f"Media player type: '{player_type}'")

    if player_type == 'auto':
        client = auto_detect_media_player(cfg)
        # Infer the detected player type from the concrete client instance
        # so downstream logic that branches on cfg.media_player_type sees
        # a concrete value instead of 'auto'.
        try:
            from moode import MoodeClient
        except ImportError:
            MoodeClient = None  # type: ignore[assignment]
        try:
            from picore_player import PiCorePlayerClient
        except ImportError:
            PiCorePlayerClient = None  # type: ignore[assignment]
        
        detected_type: str | None = None
        if isinstance(client, VolumioClient):
            detected_type = 'volumio'
        elif MoodeClient is not None and isinstance(client, MoodeClient):
            detected_type = 'moode'
        elif PiCorePlayerClient is not None and isinstance(client, PiCorePlayerClient):
            detected_type = 'picore'
        
        if detected_type is not None:
            cfg.media_player_type = detected_type
            logger.info(f"Auto-detected media player type: {detected_type}")
        else:
            logger.warning(
                "Auto-detected media player client of unknown type; "
                "leaving cfg.media_player_type as 'auto'."
            )
        return client

    if player_type == 'moode':
        from moode import MoodeClient
        logger.info(f"Using MoOde client at {cfg.moode_url}")
        return MoodeClient(cfg.moode_url)

    if player_type == 'picore':
        from picore_player import PiCorePlayerClient
        logger.info(f"Using piCorePlayer client at {cfg.lms_url}")
        return PiCorePlayerClient(cfg.lms_url)

    # Default: Volumio
    logger.info(f"Using Volumio client at {cfg.volumio_url}")
    return VolumioClient(cfg.volumio_url)

def states_are_equal(s1, s2):
    """Compares two states to see if visible fields have changed."""
    if s1 is None or s2 is None:
        return s1 == s2
    
    keys = ['title', 'artist', 'album', 'status', 'samplerate', 'bitdepth', 'albumart']
    for k in keys:
        if s1.get(k) != s2.get(k):
            return False
    return True

def disable_cursor():
    """Disables the blinking cursor on the framebuffer console using ANSI escape codes."""
    for tty in ['tty0', 'tty1', 'tty2', 'console']:
        try:
            with open(f'/dev/{tty}', 'w') as f:
                f.write('\033[?25l')  # ANSI escape code to hide cursor
                f.flush()
        except:
            pass

def enable_cursor():
    """Re-enables the cursor on exit using ANSI escape codes."""
    for tty in ['tty0', 'tty1', 'tty2', 'console']:
        try:
            with open(f'/dev/{tty}', 'w') as f:
                f.write('\033[?25h')  # ANSI escape code to show cursor
                f.flush()
        except:
            pass

def signal_handler(sig, frame):
    logger.info("Exiting application...")
    # Re-enable the cursor on exit
    enable_cursor()
    if renderer:
        # During shutdown, do not use fsync to avoid long blocks
        renderer.clear(use_fsync=False)
        renderer.close()
    if volumio:
        volumio.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    global last_state, last_rendered_state, last_rendered_mode, last_active_time, last_cycle_time, last_sync_time, last_render_time, last_volumio_timestamp, last_volumio_seek, is_sleeping, is_showing_idle, config, renderer, volumio
    
    # Initialize configuration (moved here to avoid side effects at import time)
    config = Config()
    config.validate()
    config.log_config()
    
    logger.info("SPI Now Playing - Starting...")
    
    # Wait for Volumio to fully boot and avoid framebuffer conflicts
    logger.info("Waiting for system to stabilize...")
    time.sleep(3)
    
    # Initialize modules
    # Extract Volumio host for renderer to fetch album art.
    # Note: Album art caching via Volumio API only works with Volumio, not MoOde or piCorePlayer.
    volumio_host = "localhost"
    if config.media_player_type == "volumio":
        try:
            parsed = urlparse(config.volumio_url)
            if parsed.hostname:
                volumio_host = parsed.hostname
                logger.info(f"Extracted Volumio hostname: {volumio_host}")
        except Exception as e:
            logger.warning(f"Failed to parse Volumio URL: {e}. Using localhost.")

    renderer = Renderer(
        config.display_width, config.display_height,
        config.framebuffer_device, config.color_format,
        volumio_host=volumio_host
    )
    volumio = detect_media_player(config)
    
    # Disable the blinking cursor on the framebuffer console
    disable_cursor()
    
    # Initialize inactivity timer
    last_active_time = time.time()
    
    # Show the idle screen logo instead of just clearing
    renderer.render_idle_screen()
    is_showing_idle = True
    logger.info("Startup screen displayed.")

    show_capa_mode = False

    while True:
        try:
            logger.info(f"Connecting to media player ({config.media_player_type})...")
            if not volumio.connect():
                time.sleep(5)
                continue
            
            # Immediately request state to force a render
            volumio.get_state()
            last_sync_time = time.time()
            
            while True:
                now = time.time()
                
                # Periodic synchronization every 30 seconds
                if now - last_sync_time > 30:
                    volumio.get_state()
                    last_sync_time = now
                
                # Receive messages
                new_data = volumio.receive_message(timeout=0.1)
                
                if new_data:
                    # Detect song change to reset text mode and clear art cache
                    is_new_song = False
                    if not last_state:
                        is_new_song = True
                    elif new_data.get('title') != last_state.get('title') or new_data.get('artist') != last_state.get('artist'):
                        is_new_song = True
                    
                    if is_new_song:
                        show_capa_mode = False
                        last_cycle_time = now
                        if renderer:
                            renderer.clear_art_cache()
                        logger.info(f"New song detected: {new_data.get('title')} - {new_data.get('artist')}. Starting in text mode.")
                    
                    # Store data for local seek interpolation
                    last_volumio_seek = new_data.get('seek', 0)
                    if last_volumio_seek is None:
                        last_volumio_seek = 0
                    last_volumio_timestamp = now
                    
                    # Reset standby timer on ANY state change message
                    last_active_time = now
                    
                    # Wake up if we were sleeping or showing idle
                    if is_sleeping or is_showing_idle:
                        logger.info("Activity detected, waking up display...")
                        is_sleeping = False
                        is_showing_idle = False
                    
                    last_state = new_data
                
                if not last_state:
                    continue

                # --- HANDLE IDLE/STANDBY STATES ---
                
                # If stopped or paused, show idle screen after a short timeout
                # or clear screen after a long timeout (config.standby_timeout)
                
                if last_state.get('status') != 'play':
                    # If stopped or paused for more than standby_timeout, clear screen (standby)
                    if now - last_active_time > config.standby_timeout:
                        if not is_sleeping:
                            logger.info(f"Inactive for {config.standby_timeout}s. Entering standby.")
                            renderer.clear()
                            is_sleeping = True
                            is_showing_idle = False
                        continue
                    
                    # If stopped or paused, show idle screen
                    if not is_showing_idle and not is_sleeping:
                        logger.info(f"Player {last_state.get('status')}. Showing idle screen.")
                        renderer.render_idle_screen()
                        is_showing_idle = True
                    continue # Skip music rendering
                
                # If we get here, we are playing
                if is_sleeping or is_showing_idle:
                    logger.info("Playback resumed, waking up display...")
                    # Clear the screen to ensure a fresh start
                    renderer.clear()
                    is_sleeping = False
                    is_showing_idle = False
                    # Reset mode to text and restart cycle timer on resumption
                    show_capa_mode = False
                    last_cycle_time = now
                    # Force re-render after waking up
                    last_rendered_state = None
                    last_rendered_mode = None
                
                last_active_time = now
                
                # --- HANDLE MUSIC RENDERING ---
                
                # Automatic mode switching while playing
                if last_state.get('status') == 'play':
                    if now - last_cycle_time > config.mode_cycle_time:
                        show_capa_mode = not show_capa_mode
                        last_cycle_time = now
                        logger.info(f"Switching to {'cover' if show_capa_mode else 'text'} mode...")

                # Determine if we need to re-render
                state_changed = not states_are_equal(last_state, last_rendered_state)
                mode_changed = show_capa_mode != last_rendered_mode
                time_to_update_progress = (last_state.get('status') == 'play' and now - last_render_time >= 1.0)

                if state_changed or mode_changed or time_to_update_progress:
                    # Interpolate seek time
                    current_seek = last_volumio_seek
                    if last_state.get('status') == 'play':
                        current_seek += int((now - last_volumio_timestamp) * 1000)
                    
                    render_data = last_state.copy()
                    render_data['seek'] = current_seek
                    
                    renderer.render(render_data, show_capa_mode)
                    
                    last_rendered_state = last_state.copy()
                    last_rendered_mode = show_capa_mode
                    last_render_time = now
                    is_showing_idle = False
                    is_sleeping = False

        except Exception as e:
            logger.error(f"Error in connection/main loop: {e}")
            if volumio:
                volumio.close()
            time.sleep(5)

if __name__ == "__main__":
    main()

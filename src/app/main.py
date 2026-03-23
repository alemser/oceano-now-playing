#!/usr/bin/env python3
import time
import signal
import sys
import logging
import threading

from config import Config
from media_players.base import MediaPlayer
from media_players.moode import MoodeClient
from media_players.picore import PiCorePlayerClient
from media_players.volumio import VolumioClient
from renderer import Renderer

# --- LOGGING CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global State
last_state = None
last_rendered_state = None
last_rendered_mode = None
last_active_time = time.time()
last_cycle_time = time.time()
last_sync_time = 0
last_render_time = 0
last_seek_timestamp = 0
last_known_seek = 0
is_sleeping = False
is_showing_idle = False

# Global objects
config = None
renderer = None
player = None


def _connect_with_timeout(client: MediaPlayer, timeout: float = 3.0) -> bool:
    """Connect to a media player with enforced timeout."""
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

    if thread.is_alive():
        logger.debug(f"Connect timed out after {timeout}s")
        return False

    return result["connected"]


def auto_detect_media_player(cfg: Config) -> MediaPlayer:
    """Auto-detect and instantiate the correct media player client."""
    logger.info("Auto-detecting media player...")

    candidates = [
        (
            'volumio',
            cfg.volumio_url,
            lambda url: VolumioClient(
                url,
                external_artwork_enabled=cfg.external_artwork_enabled,
            ),
        ),
        ('moode', cfg.moode_url, MoodeClient),
    ]

    for name, url, client_factory in candidates:
        try:
            logger.info(f"Probing {name} at {url}...")
            client = client_factory(url)

            if _connect_with_timeout(client, timeout=3.0):
                logger.info(f"✓ Auto-detected: {name.upper()} is running")

                try:
                    disconnect_fn = getattr(client, "disconnect", None)
                    if callable(disconnect_fn):
                        disconnect_fn()
                    else:
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

    logger.warning("No media player detected. Falling back to Volumio.")
    return VolumioClient(
        cfg.volumio_url,
        external_artwork_enabled=cfg.external_artwork_enabled,
    )


def detect_media_player(cfg: Config) -> MediaPlayer:
    """Detect and instantiate the correct media player client."""
    player_type = cfg.media_player_type
    logger.info(f"Media player type: '{player_type}'")

    if player_type == 'auto':
        client = auto_detect_media_player(cfg)

        detected_type = None
        if isinstance(client, VolumioClient):
            detected_type = 'volumio'
        elif isinstance(client, MoodeClient):
            detected_type = 'moode'
        elif isinstance(client, PiCorePlayerClient):
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
        logger.info(f"Using MoOde client at {cfg.moode_url}")
        return MoodeClient(cfg.moode_url)

    if player_type == 'picore':
        logger.info(f"Using piCorePlayer client at {cfg.lms_url}")
        return PiCorePlayerClient(cfg.lms_url)

    logger.info(f"Using Volumio client at {cfg.volumio_url}")
    return VolumioClient(cfg.volumio_url)


def states_are_equal(s1, s2):
    """Compares two states to see if visible fields have changed."""
    if s1 is None or s2 is None:
        return s1 == s2

    keys = ['title', 'artist', 'album', 'status', 'samplerate', 'bitdepth', 'albumart']
    for key in keys:
        if s1.get(key) != s2.get(key):
            return False
    return True


def disable_cursor():
    """Disable the blinking cursor on the framebuffer console."""
    for tty in ['tty0', 'tty1', 'tty2', 'console']:
        try:
            with open(f'/dev/{tty}', 'w') as f:
                f.write('\033[?25l')
                f.flush()
        except Exception:
            pass


def enable_cursor():
    """Re-enable the cursor on exit."""
    for tty in ['tty0', 'tty1', 'tty2', 'console']:
        try:
            with open(f'/dev/{tty}', 'w') as f:
                f.write('\033[?25h')
                f.flush()
        except Exception:
            pass


def signal_handler(sig, frame):
    logger.info("Exiting application...")
    enable_cursor()
    if renderer:
        renderer.clear(use_fsync=False)
        renderer.close()
    if player:
        player.close()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    global last_state, last_rendered_state, last_rendered_mode
    global last_active_time, last_cycle_time, last_sync_time, last_render_time
    global last_seek_timestamp, last_known_seek, is_sleeping, is_showing_idle
    global config, renderer, player

    config = Config()
    config.validate()
    config.log_config()

    logger.info("SPI Now Playing - Starting...")
    logger.info("Waiting for system to stabilize...")
    time.sleep(3)

    renderer = Renderer(
        config.display_width,
        config.display_height,
        config.framebuffer_device,
        config.color_format,
    )
    player = detect_media_player(config)

    disable_cursor()
    last_active_time = time.time()

    renderer.render_idle_screen()
    is_showing_idle = True
    logger.info("Startup screen displayed.")

    show_capa_mode = False

    while True:
        try:
            logger.info(f"Connecting to media player ({config.media_player_type})...")
            if not player.connect():
                time.sleep(5)
                continue

            player.get_state()
            last_sync_time = time.time()

            while True:
                now = time.time()

                if now - last_sync_time > 30:
                    player.get_state()
                    last_sync_time = now

                new_data = player.receive_message(timeout=0.1)

                if new_data:
                    is_new_song = False
                    artwork_changed = False
                    if not last_state:
                        is_new_song = True
                    elif new_data.get('title') != last_state.get('title') or new_data.get('artist') != last_state.get('artist'):
                        is_new_song = True
                    if last_state and new_data.get('albumart') != last_state.get('albumart'):
                        artwork_changed = True

                    previous_resolved_artwork = last_state.get('_resolved_artwork') if last_state else None

                    if is_new_song or artwork_changed or last_state is None:
                        new_data['_resolved_artwork'] = player.resolve_artwork(new_data)
                    else:
                        new_data['_resolved_artwork'] = previous_resolved_artwork

                    if is_new_song:
                        show_capa_mode = False
                        last_cycle_time = now
                        if renderer:
                            renderer.clear_art_cache()
                        logger.info(f"New song detected: {new_data.get('title')} - {new_data.get('artist')}. Starting in text mode.")

                    last_known_seek = new_data.get('seek', 0)
                    if last_known_seek is None:
                        last_known_seek = 0
                    last_seek_timestamp = now
                    last_active_time = now

                    if is_sleeping or is_showing_idle:
                        logger.info("Activity detected, waking up display...")
                        is_sleeping = False
                        is_showing_idle = False

                    last_state = new_data

                if not last_state:
                    continue

                if last_state.get('status') != 'play':
                    if now - last_active_time > config.standby_timeout:
                        if not is_sleeping:
                            logger.info(f"Inactive for {config.standby_timeout}s. Entering standby.")
                            renderer.clear()
                            is_sleeping = True
                            is_showing_idle = False
                        continue

                    if not is_showing_idle and not is_sleeping:
                        logger.info(f"Player {last_state.get('status')}. Showing idle screen.")
                        renderer.render_idle_screen()
                        is_showing_idle = True
                    continue

                if is_sleeping or is_showing_idle:
                    logger.info("Playback resumed, waking up display...")
                    renderer.clear()
                    is_sleeping = False
                    is_showing_idle = False
                    show_capa_mode = False
                    last_cycle_time = now
                    last_rendered_state = None
                    last_rendered_mode = None

                last_active_time = now

                if last_state.get('status') == 'play' and now - last_cycle_time > config.mode_cycle_time:
                    show_capa_mode = not show_capa_mode
                    last_cycle_time = now
                    logger.info(f"Switching to {'cover' if show_capa_mode else 'text'} mode...")

                state_changed = not states_are_equal(last_state, last_rendered_state)
                mode_changed = show_capa_mode != last_rendered_mode
                time_to_update_progress = (
                    last_state.get('status') == 'play' and now - last_render_time >= 1.0
                )

                if state_changed or mode_changed or time_to_update_progress:
                    current_seek = last_known_seek
                    if last_state.get('status') == 'play':
                        current_seek += int((now - last_seek_timestamp) * 1000)

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
            if player:
                player.close()
            time.sleep(5)


if __name__ == "__main__":
    main()

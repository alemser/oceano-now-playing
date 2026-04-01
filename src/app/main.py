#!/usr/bin/env python3
import time
import signal
import sys
import logging

from config import Config
from media_players.state_file import StateFileClient
from renderer import Renderer
from vu_client import VUClient

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
vu_client = None


def should_reconnect_player(client) -> bool:
    """Return True when the state file has disappeared and needs reconnection."""
    try:
        return not client.is_connected()
    except Exception as e:
        logger.debug(f"Error checking player connection state: {e}")
        return True


def states_are_equal(s1, s2):
    """Compares two states to see if visible fields have changed."""
    if s1 is None or s2 is None:
        return s1 == s2

    keys = [
        'title',
        'artist',
        'album',
        'status',
        'samplerate',
        'bitdepth',
        'albumart',
        'playback_source',
        'media_side',
        'media_track_number',
        'media_position',
    ]
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
    if vu_client:
        vu_client.stop()
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
    global config, renderer, player, vu_client

    config = Config()
    config.validate()
    config.log_config()

    logger.info("Oceano Now Playing - Starting...")
    time.sleep(3)

    renderer = Renderer(
        config.display_width,
        config.display_height,
        config.framebuffer_device,
        config.color_format,
        layout_profile=config.layout_profile,
    )
    player = StateFileClient(config.oceano_state_file)

    if config.display_mode == "vu":
        vu_client = VUClient(config.vu_socket)
        vu_client.start()

    disable_cursor()
    last_active_time = time.time()

    renderer.render_idle_screen()
    is_showing_idle = True
    logger.info("Startup screen displayed.")

    show_artwork_mode = config.display_mode == 'artwork'

    while True:
        try:
            logger.info("Connecting to state file...")
            if not player.connect():
                time.sleep(5)
                continue
            logger.info("Connected to state file.")

            player.get_state()
            last_sync_time = time.time()

            while True:
                now = time.time()

                if now - last_sync_time > 30:
                    player.get_state()
                    last_sync_time = now

                new_data = player.receive_message(timeout=0.1)
                if should_reconnect_player(player):
                    logger.info("State file unavailable. Reconnecting...")
                    player.close()
                    time.sleep(0.5)
                    break

                if new_data is not None:
                    is_new_song = False
                    has_meaningful_track_metadata = bool(
                        new_data.get('title') and new_data.get('artist')
                    )

                    if has_meaningful_track_metadata:
                        if not last_state:
                            is_new_song = True
                        elif (
                            new_data.get('title') != last_state.get('title')
                            or new_data.get('artist') != last_state.get('artist')
                        ):
                            is_new_song = True

                    incoming_seek = new_data.get('seek') if new_data else 0
                    if incoming_seek is None:
                        incoming_seek = 0

                    if last_seek_timestamp == 0 or incoming_seek != last_known_seek:
                        last_known_seek = incoming_seek
                        last_seek_timestamp = now
                    status = new_data.get('status') if new_data else None
                    if status == 'play':
                        last_active_time = now

                    if status == 'play' and (is_sleeping or is_showing_idle):
                        logger.info("Activity detected, waking up display...")
                        is_sleeping = False
                        is_showing_idle = False

                    if is_new_song:
                        if config.display_mode == 'artwork':
                            show_artwork_mode = True
                        else:
                            show_artwork_mode = False
                        if config.display_mode == 'rotate':
                            last_cycle_time = now
                        if renderer:
                            renderer.clear_art_cache()
                        if config.display_mode == 'hybrid':
                            mode_label = 'hybrid'
                        else:
                            mode_label = 'cover' if show_artwork_mode else 'text'
                        logger.info(
                            f"New song detected: {new_data.get('title')} - {new_data.get('artist')}. "
                            f"Starting in {mode_label} mode."
                        )

                    last_state = new_data

                if not last_state:
                    continue

                status = last_state.get('status') if last_state else None
                if status != 'play':
                    if now - last_active_time > config.standby_timeout:
                        if not is_sleeping:
                            logger.debug(f"Inactive for {config.standby_timeout}s. Entering standby.")
                            renderer.clear()
                            is_sleeping = True
                            is_showing_idle = False
                        continue

                    if not is_showing_idle and not is_sleeping:
                        logger.debug(f"Player {status}. Showing idle screen.")
                        renderer.render_idle_screen()
                        is_showing_idle = True
                    continue

                if is_sleeping or is_showing_idle:
                    logger.info("Playback resumed, waking up display...")
                    renderer.clear()
                    is_sleeping = False
                    is_showing_idle = False
                    if config.display_mode == 'artwork':
                        show_artwork_mode = True
                    else:
                        show_artwork_mode = False
                    if config.display_mode == 'rotate':
                        last_cycle_time = now
                    last_rendered_state = None
                    last_rendered_mode = None

                last_active_time = now

                if config.display_mode == 'vu':
                    # VU mode: render at ~15 fps regardless of metadata changes.
                    if now - last_render_time >= 0.067:
                        vu_l, vu_r, peak_l, peak_r = vu_client.get_levels()
                        current_seek = last_known_seek
                        if status == 'play':
                            current_seek += int((now - last_seek_timestamp) * 1000)
                        render_data = last_state.copy()
                        render_data['seek'] = current_seek
                        renderer.render_vu(vu_l, vu_r, peak_l, peak_r, render_data)
                        last_render_time = now
                        is_showing_idle = False
                        is_sleeping = False
                else:
                    if config.display_mode == 'rotate':
                        if status == 'play' and now - last_cycle_time > config.mode_cycle_time:
                            show_artwork_mode = not show_artwork_mode
                            last_cycle_time = now
                            logger.debug(f"Switching to {'cover' if show_artwork_mode else 'text'} mode...")
                    elif config.display_mode == 'artwork':
                        show_artwork_mode = True
                    else:
                        show_artwork_mode = False

                    state_changed = not states_are_equal(last_state, last_rendered_state)
                    if config.display_mode == 'hybrid':
                        current_render_mode = 'hybrid'
                    else:
                        current_render_mode = 'artwork' if show_artwork_mode else 'text'
                    mode_changed = current_render_mode != last_rendered_mode
                    time_to_update_progress = (
                        status == 'play' and now - last_render_time >= 1.0
                    )

                    if state_changed or mode_changed or time_to_update_progress:
                        current_seek = last_known_seek
                        if status == 'play':
                            current_seek += int((now - last_seek_timestamp) * 1000)

                        render_data = last_state.copy()
                        render_data['seek'] = current_seek

                        renderer.render(
                            render_data,
                            show_artwork_mode=show_artwork_mode,
                            show_hybrid_mode=(config.display_mode == 'hybrid'),
                        )

                        last_rendered_state = last_state.copy()
                        last_rendered_mode = current_render_mode
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

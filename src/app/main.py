#!/usr/bin/env python3
import time
import signal
import sys
import logging

from config import Config
from media_players.base import MediaPlayer
from media_players.oceano import OceanoClient
from media_players.oceano_analog import OceanoAnalogClient
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
ARTWORK_RETRY_INTERVAL_SECONDS = 15.0
ARTWORK_RESOLVE_TIMEOUT_SECONDS = 2.5


# Global objects
config = None
renderer = None
player_digital = None
player_analog = None


def detect_media_player(cfg: Config) -> OceanoClient:
    """Instantiate the Oceano metadata client used by this fork."""
    if cfg.media_player_type == 'oceano':
        logger.info(f"Using Oceano client at {cfg.oceano_metadata_pipe}")
        return OceanoClient(
            cfg.oceano_metadata_pipe,
            external_artwork_enabled=cfg.external_artwork_enabled,
        )
    elif cfg.media_player_type == 'oceano_analog':
        logger.info("Using Oceano Analog client (analog source detection)")
        return OceanoAnalogClient()
    else:
        raise ValueError(f"Unsupported MEDIA_PLAYER: {cfg.media_player_type}")


def should_resolve_artwork(
    is_new_song: bool,
    artwork_changed: bool,
    previous_resolved_artwork: dict | None,
    previous_artwork_resolve_time: float | None,
    now: float,
    metadata_became_meaningful: bool = False,
) -> bool:
    """Decide whether to resolve artwork again for the current state update.

    Notes:
        artwork_changed is intentionally ignored in provider-only mode because
        the raw albumart field can fluctuate while track metadata stays steady,
        which would otherwise cause redundant fallback lookups.
    """
    if is_new_song:
        return True

    if metadata_became_meaningful:
        # Refresh once when artist/album transitions from placeholders to
        # meaningful metadata, even if we currently hold fallback artwork.
        return True

    if previous_resolved_artwork is None:
        if previous_artwork_resolve_time is None:
            return True
        return (now - previous_artwork_resolve_time) >= ARTWORK_RETRY_INTERVAL_SECONDS

    if previous_resolved_artwork.get('source') == 'fallback':
        return False

    return False


def artwork_identity_changed(current_state: dict | None, previous_state: dict | None) -> bool:
    """Return True when artist/album pair changed and artwork should refresh."""
    if current_state is None:
        return False
    if previous_state is None:
        return True

    return (
        (current_state.get('artist') or "") != (previous_state.get('artist') or "")
        or (current_state.get('album') or "") != (previous_state.get('album') or "")
    )


def _is_meaningful_metadata_value(value: str | None) -> bool:
    """Return True when metadata value is not empty or placeholder text."""
    normalized = (value or "").strip().lower()
    return normalized not in {"", "unknown", "[unknown]", "none", "n/a"}


def metadata_became_meaningful(current_state: dict | None, previous_state: dict | None) -> bool:
    """Return True when artist/album improves from placeholder to meaningful."""
    if current_state is None:
        return False

    current_artist = _is_meaningful_metadata_value(current_state.get('artist'))
    current_album = _is_meaningful_metadata_value(current_state.get('album'))
    current_is_meaningful = current_artist and current_album
    if not current_is_meaningful:
        return False

    if previous_state is None:
        return True

    previous_artist = _is_meaningful_metadata_value(previous_state.get('artist'))
    previous_album = _is_meaningful_metadata_value(previous_state.get('album'))
    previous_is_meaningful = previous_artist and previous_album
    return not previous_is_meaningful


def has_backend_artwork(state: dict | None) -> bool:
    """Return True when state already carries non-fallback resolved artwork."""
    if not state:
        return False
    resolved = state.get('_resolved_artwork')
    if not isinstance(resolved, dict):
        return False
    return resolved.get('source') != 'fallback'


def should_reconnect_player(client: MediaPlayer) -> bool:
    """Return True when the active player transport has dropped.

    This allows the main loop to re-enter the outer connect path after a
    backend disconnects mid-run, which is required for FIFO-based backends
    like Oceano after the writer closes the metadata pipe.
    """
    try:
        return not client.is_connected()
    except Exception as e:
        logger.debug(f"Error checking player connection state: {e}")
        return True


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
    # Fechar ambos os players se existirem
    global player_digital, player_analog
    if player_digital:
        player_digital.close()
    if player_analog:
        player_analog.close()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)



def main():
    DIGITAL_TIMEOUT_SECONDS = 5.0
    last_digital_update = 0.0
    global last_state, last_rendered_state, last_rendered_mode
    global last_active_time, last_cycle_time, last_sync_time, last_render_time
    global last_seek_timestamp, last_known_seek, is_sleeping, is_showing_idle
    global config, renderer, player_digital, player_analog

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
    # Sempre instanciar ambos os players
    player_digital = OceanoClient(
        config.oceano_metadata_pipe,
        external_artwork_enabled=config.external_artwork_enabled,
    )
    player_analog = OceanoAnalogClient()

    disable_cursor()
    last_active_time = time.time()

    renderer.render_idle_screen()
    is_showing_idle = True
    logger.info("Startup screen displayed.")

    show_artwork_mode = config.display_mode == 'artwork'

    while True:
        try:
            logger.info("Connecting to digital and analog media players...")
            if not player_digital.connect():
                logger.warning("Digital player failed to connect. Retrying...")
                time.sleep(5)
                continue
            if not player_analog.connect():
                logger.warning("Analog player failed to connect. Retrying...")
                time.sleep(5)
                continue
            logger.info("Connected to both players.")

            player_digital.get_state()
            last_sync_time = time.time()

            while True:
                now = time.time()

                if now - last_sync_time > 30:
                    player_digital.get_state()
                    last_sync_time = now

                # Consulta ambos os players

                data_digital = player_digital.receive_message(timeout=0.1)
                data_analog = player_analog.receive_message(timeout=0.1)

                now = time.time()
                # Timeout: se não receber digital por X segundos, ignora digital
                digital_active = False
                if data_digital:
                    last_digital_update = now
                    if data_digital.get("status") == "play":
                        digital_active = True
                elif (now - last_digital_update) < DIGITAL_TIMEOUT_SECONDS and last_state and last_state.get("status") == "play":
                    # Considera digital ativo se tocou recentemente
                    digital_active = True

                # Prioridade: digital tocando > analog tocando > idle
                chosen = None
                if digital_active and data_digital:
                    chosen = data_digital
                elif data_analog and data_analog.get("status") == "play":
                    chosen = data_analog
                elif data_digital:
                    chosen = data_digital
                elif data_analog:
                    chosen = data_analog

                if should_reconnect_player(player_digital):
                    logger.info("Digital player disconnected. Reconnecting...")
                    player_digital.close()
                    time.sleep(0.5)
                    break
                if should_reconnect_player(player_analog):
                    logger.info("Analog player disconnected. Reconnecting...")
                    player_analog.close()
                    time.sleep(0.5)
                    break

                if chosen:
                    is_new_song = False
                    artwork_identity_is_new = artwork_identity_changed(chosen, last_state)
                    metadata_upgraded = metadata_became_meaningful(chosen, last_state)
                    has_meaningful_track_metadata = (
                        _is_meaningful_metadata_value(chosen.get('title'))
                        and _is_meaningful_metadata_value(chosen.get('artist'))
                    )
                    has_meaningful_artwork_metadata = (
                        _is_meaningful_metadata_value(chosen.get('artist'))
                        and _is_meaningful_metadata_value(chosen.get('album'))
                    )

                    # Avoid treating placeholder play states as new songs.
                    if has_meaningful_track_metadata:
                        if not last_state:
                            is_new_song = True
                        elif (
                            chosen.get('title') != last_state.get('title')
                            or chosen.get('artist') != last_state.get('artist')
                        ):
                            is_new_song = True

                    previous_resolved_artwork = last_state.get('_resolved_artwork') if last_state else None
                    previous_artwork_resolve_time = (
                        last_state.get('_artwork_resolve_time') if last_state else None
                    )

                    if should_resolve_artwork(
                        is_new_song=artwork_identity_is_new,
                        artwork_changed=False,
                        previous_resolved_artwork=previous_resolved_artwork,
                        previous_artwork_resolve_time=previous_artwork_resolve_time,
                        now=now,
                        metadata_became_meaningful=metadata_upgraded,
                    ):
                        if not has_backend_artwork(chosen) and has_meaningful_artwork_metadata and chosen is data_digital:
                            chosen['_resolved_artwork'] = player_digital.resolve_artwork(
                                chosen,
                                timeout=ARTWORK_RESOLVE_TIMEOUT_SECONDS,
                            )
                        chosen['_artwork_resolve_time'] = now
                    else:
                        if has_backend_artwork(chosen):
                            chosen['_artwork_resolve_time'] = now
                        else:
                            chosen['_resolved_artwork'] = previous_resolved_artwork
                            if previous_artwork_resolve_time is not None:
                                chosen['_artwork_resolve_time'] = previous_artwork_resolve_time

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
                            f"New song detected: {chosen.get('title')} - {chosen.get('artist')}. "
                            f"Starting in {mode_label} mode."
                        )

                    incoming_seek = chosen.get('seek')
                    if incoming_seek is None:
                        incoming_seek = 0

                    # Some backends emit frequent metadata-only updates. Only
                    # reset interpolation anchor when seek actually changes.
                    if last_seek_timestamp == 0 or incoming_seek != last_known_seek:
                        last_known_seek = incoming_seek
                        last_seek_timestamp = now
                    status = chosen.get('status')
                    if status == 'play':
                        last_active_time = now

                    if status == 'play' and (is_sleeping or is_showing_idle):
                        logger.info("Activity detected, waking up display...")
                        is_sleeping = False
                        is_showing_idle = False

                    last_state = chosen

                if not last_state:
                    continue

                if last_state.get('status') != 'play':
                    if now - last_active_time > config.standby_timeout:
                        if not is_sleeping:
                            logger.debug(f"Inactive for {config.standby_timeout}s. Entering standby.")
                            renderer.clear()
                            is_sleeping = True
                            is_showing_idle = False
                        continue

                    if not is_showing_idle and not is_sleeping:
                        logger.debug(f"Player {last_state.get('status')}. Showing idle screen.")
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

                if config.display_mode == 'rotate':
                    if last_state.get('status') == 'play' and now - last_cycle_time > config.mode_cycle_time:
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
                    last_state.get('status') == 'play' and now - last_render_time >= 1.0
                )

                if state_changed or mode_changed or time_to_update_progress:
                    current_seek = last_known_seek
                    if last_state.get('status') == 'play':
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
            if player_digital:
                player_digital.close()
            if player_analog:
                player_analog.close()
            time.sleep(5)


if __name__ == "__main__":
    main()

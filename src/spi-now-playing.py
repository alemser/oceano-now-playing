#!/usr/bin/env python3
import time
import os
import signal
import sys
import logging
from renderer import Renderer
from volumio import VolumioClient

# --- LOGGING CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- SETTINGS ---
WIDTH, HEIGHT = 480, 320
FB_DEVICE = os.getenv("FB_DEVICE", "/dev/fb0")
VOLUMIO_URL = os.getenv("VOLUMIO_URL", "ws://localhost:3000/socket.io/?EIO=3&transport=websocket")
COLOR_FORMAT = os.getenv("COLOR_FORMAT", "RGB565")

CYCLE_TIME = 30
# Standby time in seconds (default: 600 = 10 minutes)
STANDBY_TIMEOUT = int(os.getenv("STANDBY_TIMEOUT", 600))

# Global State
last_state = None
last_rendered_state = None
last_active_time = time.time()
last_cycle_time = time.time()
last_sync_time = 0
show_capa_mode = False
is_sleeping = False

# Global objects
renderer = None
volumio = None

def states_are_equal(s1, s2):
    """Compares two states to see if visible fields have changed."""
    if s1 is None or s2 is None:
        return s1 == s2
    
    keys = ['title', 'artist', 'album', 'status', 'samplerate', 'bitdepth', 'albumart']
    for k in keys:
        if s1.get(k) != s2.get(k):
            return False
    return True

def signal_handler(sig, frame):
    logger.info("Exiting application...")
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
    global last_state, last_rendered_state, last_active_time, last_cycle_time, last_sync_time, show_capa_mode, is_sleeping, renderer, volumio
    
    logger.info("SPI Now Playing - Starting...")
    
    # Initialize modules
    renderer = Renderer(WIDTH, HEIGHT, FB_DEVICE, COLOR_FORMAT)
    volumio = VolumioClient(VOLUMIO_URL)
    
    # Initialize inactivity timer
    last_active_time = time.time()
    
    renderer.clear()

    while True:
        try:
            logger.info(f"Connecting to Volumio at {VOLUMIO_URL}...")
            if not volumio.connect():
                time.sleep(5)
                continue
                
            last_sync_time = time.time()
            
            while True:
                now = time.time()
                
                # Periodic synchronization every 30 seconds
                if now - last_sync_time > 30:
                    volumio.get_state()
                    last_sync_time = now
                
                # Receive messages
                new_data = volumio.receive_message(timeout=1.0)
                
                if new_data:
                    # Detect song change to reset text mode
                    if last_state and new_data.get('title') != last_state.get('title'):
                        show_capa_mode = False
                        last_cycle_time = now
                        logger.info(f"New song detected: {new_data.get('title')} - {new_data.get('artist')}")
                    
                    # Reset standby timer on ANY state change message
                    last_active_time = now
                    
                    # Wake up if we were sleeping
                    if is_sleeping:
                        logger.info("Activity detected, exiting standby mode...")
                        is_sleeping = False
                    
                    # Render only if state changed or we exited standby mode
                    if not states_are_equal(new_data, last_rendered_state) or is_sleeping:
                        renderer.render(new_data, show_capa_mode)
                        last_rendered_state = new_data.copy()
                    
                    last_state = new_data
                
                # Time and state checks
                if not last_state:
                    continue
                
                # Standby (Turn off screen if inactive for too long)
                if last_state.get('status') == 'play':
                    last_active_time = now
                    is_sleeping = False
                
                if last_state.get('status') != 'play' and (now - last_active_time > STANDBY_TIMEOUT):
                    if not is_sleeping:
                        logger.info(f"Inactive for {STANDBY_TIMEOUT}s. Entering standby...")
                        renderer.clear()
                        is_sleeping = True
                    continue
                
                # Automatic mode switching: alternating between Text and Cover every CYCLE_TIME
                if last_state and last_state.get('status') == 'play':
                    if now - last_cycle_time > CYCLE_TIME:
                        show_capa_mode = not show_capa_mode
                        last_cycle_time = now
                        logger.info(f"Switching to {'cover' if show_capa_mode else 'text'} mode...")
                        renderer.render(last_state, show_capa_mode)
                        last_rendered_state = last_state.copy()

        except Exception as e:
            logger.error(f"Error in connection/main loop: {e}")
            if volumio:
                volumio.close()
            time.sleep(5)

if __name__ == "__main__":
    main()

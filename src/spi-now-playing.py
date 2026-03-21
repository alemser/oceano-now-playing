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

# --- CONFIGURAÇÕES ---
WIDTH, HEIGHT = 480, 320
FB_DEVICE = os.getenv("FB_DEVICE", "/dev/fb0")
VOLUMIO_URL = os.getenv("VOLUMIO_URL", "ws://localhost:3000/socket.io/?EIO=3&transport=websocket")
COLOR_FORMAT = os.getenv("COLOR_FORMAT", "RGB565")

CYCLE_TIME = 30
# Standby time in seconds (default: 600 = 10 minutes)
STANDBY_TIMEOUT = int(os.getenv("STANDBY_TIMEOUT", 600))

# Estado Global
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
    """Compara dois estados para ver se os campos visíveis mudaram."""
    if s1 is None or s2 is None:
        return s1 == s2
    
    keys = ['title', 'artist', 'album', 'status', 'samplerate', 'bitdepth', 'albumart']
    for k in keys:
        if s1.get(k) != s2.get(k):
            return False
    return True

def signal_handler(sig, frame):
    logger.info("Encerrando aplicação...")
    if renderer:
        # Durante o encerramento, não usamos fsync para evitar bloqueios longos
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
    
    # Inicializa os módulos
    renderer = Renderer(WIDTH, HEIGHT, FB_DEVICE, COLOR_FORMAT)
    volumio = VolumioClient(VOLUMIO_URL)
    
    # Inicializa o temporizador de inatividade
    last_active_time = time.time()
    
    renderer.clear()

    while True:
        try:
            logger.info(f"Conectando ao Volumio em {VOLUMIO_URL}...")
            if not volumio.connect():
                time.sleep(5)
                continue
                
            last_sync_time = time.time()
            
            while True:
                now = time.time()
                
                # Sincronização periódica a cada 30 segundos
                if now - last_sync_time > 30:
                    volumio.get_state()
                    last_sync_time = now
                
                # Recebe mensagens
                new_data = volumio.receive_message(timeout=1.0)
                
                if new_data:
                    # Detecta mudança de música para resetar modo texto
                    if last_state and new_data.get('title') != last_state.get('title'):
                        show_capa_mode = False
                        last_cycle_time = now
                        logger.info(f"Nova música detectada: {new_data.get('title')} - {new_data.get('artist')}")
                    
                    # Reset standby timer on ANY state change message
                    last_active_time = now
                    
                    # Wake up if we were sleeping
                    if is_sleeping:
                        logger.info("Atividade detectada, saindo do modo standby...")
                        is_sleeping = False
                    
                    # Renderiza apenas se o estado mudou ou se saímos do modo standby
                    if not states_are_equal(new_data, last_rendered_state) or is_sleeping:
                        renderer.render(new_data, show_capa_mode)
                        last_rendered_state = new_data.copy()
                    
                    last_state = new_data
                
                # Verificações de tempo e estado
                if not last_state:
                    continue
                
                # Standby (Desliga a tela se inativo por muito tempo)
                if last_state.get('status') == 'play':
                    last_active_time = now
                    is_sleeping = False
                
                if last_state.get('status') != 'play' and (now - last_active_time > STANDBY_TIMEOUT):
                    if not is_sleeping:
                        logger.info(f"Inativo por {STANDBY_TIMEOUT}s. Entrando em standby...")
                        renderer.clear()
                        is_sleeping = True
                    continue
                
                # Alternância automática Texto (30s) -> Capa
                if not show_capa_mode and (now - last_cycle_time > CYCLE_TIME) and last_state.get('status') == 'play':
                    logger.info("Alternando para modo capa...")
                    show_capa_mode = True
                    renderer.render(last_state, show_capa_mode)
                    last_rendered_state = last_state.copy()

        except Exception as e:
            logger.error(f"Erro na conexão/loop principal: {e}")
            if volumio:
                volumio.close()
            time.sleep(5)

if __name__ == "__main__":
    main()

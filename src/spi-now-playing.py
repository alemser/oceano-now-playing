#!/usr/bin/env python3
import time
import json
import os
import signal
import sys
import requests
import textwrap
import logging
from io import BytesIO
import numpy as np
from websocket import create_connection
from PIL import Image, ImageDraw, ImageFont

# --- LOGGING CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÕES ---
WIDTH, HEIGHT = 480, 320
FB_DEVICE = os.getenv("FB_DEVICE", "/dev/fb0")
VOLUMIO_URL = os.getenv("VOLUMIO_URL", "ws://localhost:3000/socket.io/?EIO=3&transport=websocket")

ART_SIZE = 320
ART_X, ART_Y = 10, 0
CYCLE_TIME = 30
# Standby time in seconds (default: 600 = 10 minutes)
STANDBY_TIMEOUT = int(os.getenv("STANDBY_TIMEOUT", 600))

# Estado Global
last_state = None
last_active_time = time.time()
last_cycle_time = time.time()
show_capa_mode = False
is_sleeping = False

def rgb888_to_bgr565(img):
    """
    Converte uma imagem RGB888 do Pillow para o formato BGR565 (16 bits)
    comumente usado por framebuffers Linux em displays SPI.
    """
    img_array = np.array(img).astype(np.uint16)
    # R (5 bits), G (6 bits), B (5 bits)
    r, g, b = (img_array[:,:,0] >> 3), (img_array[:,:,1] >> 2), (img_array[:,:,2] >> 3)
    # Formato BGR565: B (bits 11-15), G (bits 5-10), R (bits 0-4)
    return (b << 11 | g << 5 | r).tobytes()

def clear_fb():
    """Limpa o framebuffer preenchendo-o com preto."""
    try:
        blank = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
        with open(FB_DEVICE, "wb") as f:
            f.write(rgb888_to_bgr565(blank))
    except Exception as e:
        logger.error(f"Erro ao limpar framebuffer: {e}")

def get_font(size, bold=False):
    """Tenta carregar uma fonte específica ou retorna a padrão."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def render_ui(data):
    if not data:
        return

    img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    f_large = get_font(36, bold=True)
    f_med = get_font(26)
    f_tech = get_font(22, bold=True)

    title = data.get('title', 'Unknown')
    artist = data.get('artist', 'Unknown')
    album = data.get('album', 'Unknown')
    samplerate = data.get('samplerate', '')
    bitdepth = data.get('bitdepth', '')
    albumart = data.get('albumart', '')

    if not show_capa_mode:
        # --- MODO 1: TEXTO (ALINHADO À ESQUERDA COM QUEBRA DE LINHA) ---
        margin_left = 20
        y_cursor = 30
        
        # Quebra o título se for muito longo (aprox 20-22 caracteres por linha)
        lines = textwrap.wrap(title, width=22)
        for line in lines[:3]: # No máximo 3 linhas de título
            draw.text((margin_left, y_cursor), line, fill=(255, 255, 255), font=f_large)
            y_cursor += 45
        
        y_cursor += 10
        draw.text((margin_left, y_cursor), artist[:35], fill=(200, 200, 200), font=f_med)
        y_cursor += 35
        draw.text((margin_left, y_cursor), album[:40], fill=(120, 120, 120), font=f_med)
        
        # Linha verde e qualidade técnica
        y_cursor += 50
        draw.line((margin_left, y_cursor, 200, y_cursor), fill=(60, 180, 60), width=3)
        y_cursor += 15
        quality_str = f"{samplerate} | {bitdepth}" if samplerate and bitdepth else samplerate or bitdepth
        draw.text((margin_left, y_cursor), quality_str, fill=(150, 150, 150), font=f_tech)

    else:
        # --- MODO 2: CAPA + INFO TÉCNICA À DIREITA ---
        if albumart:
            try:
                # Volumio host can be localhost or the actual IP
                url = f"http://localhost:3000{albumart}" if albumart.startswith('/') else albumart
                res = requests.get(url, timeout=3)
                art = Image.open(BytesIO(res.content)).convert("RGB").resize((ART_SIZE, ART_SIZE), Image.Resampling.LANCZOS)
                img.paste(art, (ART_X, ART_Y))
            except Exception as e:
                logger.warning(f"Erro ao carregar album art: {e}")

        # Info Técnica empilhada à direita (kHz e Bits)
        x_pos = 345
        if samplerate:
            draw.text((x_pos, 25), f"{samplerate}", fill=(60, 180, 60), font=f_tech)
        if bitdepth:
            draw.text((x_pos, 65), f"{bitdepth}", fill=(60, 180, 60), font=f_tech)

    # Envio ao Hardware
    try:
        raw = rgb888_to_bgr565(img)
        with open(FB_DEVICE, "wb") as f:
            f.write(raw)
    except Exception as e:
        logger.error(f"Erro ao escrever no framebuffer: {e}")

def signal_handler(sig, frame):
    logger.info("Encerrando aplicação...")
    clear_fb()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    global last_state, last_active_time, last_cycle_time, show_capa_mode, is_sleeping
    
    logger.info("SPI Now Playing - Starting...")
    
    # Tenta garantir permissões no framebuffer
    if os.path.exists(FB_DEVICE):
        try:
            os.system(f"sudo chmod 666 {FB_DEVICE}")
        except:
            logger.warning(f"Não foi possível mudar as permissões de {FB_DEVICE}. Tente rodar como sudo.")
    else:
        logger.error(f"Dispositivo de framebuffer {FB_DEVICE} não encontrado.")
        # No Pi 5, verifique se o overlay do display está habilitado no config.txt
    
    clear_fb()

    while True:
        try:
            logger.info(f"Conectando ao Volumio em {VOLUMIO_URL}...")
            ws = create_connection(VOLUMIO_URL, timeout=10)
            ws.send('42["getState"]')
            
            while True:
                ws.settimeout(1.0)
                try:
                    result = ws.recv()
                    if result.startswith('42["pushState"'):
                        # Extrai o JSON da mensagem do socket.io
                        json_str = result[result.find('{'):result.rfind('}')+1]
                        new_data = json.loads(json_str)
                        
                        # Reset para modo texto em nova música
                        if last_state and new_data.get('title') != last_state.get('title'):
                            show_capa_mode = False
                            last_cycle_time = time.time()
                            logger.info(f"Nova música: {new_data.get('title')} - {new_data.get('artist')}")
                        
                        last_state = new_data
                        if last_state.get('status') == 'play':
                            last_active_time = time.time()
                        
                        render_ui(last_state)
                    elif result == '2': # Heartbeat do socket.io
                        ws.send('3')
                except (TimeoutError, Exception) as e:
                    # Timeouts são normais se não houver mudança de estado
                    pass

                if not last_state:
                    continue
                
                now = time.time()
                
                # Standby (Desliga a tela se inativo por muito tempo)
                if last_state.get('status') != 'play' and (now - last_active_time > STANDBY_TIMEOUT):
                    if not is_sleeping:
                        logger.info("Entrando em modo standby...")
                        clear_fb()
                        is_sleeping = True
                    continue
                
                if is_sleeping and last_state.get('status') == 'play':
                    logger.info("Saindo do modo standby...")
                    is_sleeping = False

                # Alternância automática Texto (30s) -> Capa
                if not show_capa_mode and (now - last_cycle_time > CYCLE_TIME) and last_state.get('status') == 'play':
                    logger.info("Alternando para modo capa...")
                    show_capa_mode = True
                    render_ui(last_state)

        except Exception as e:
            logger.error(f"Erro na conexão/loop principal: {e}")
            time.sleep(5) # Tenta reconectar após 5 segundos

if __name__ == "__main__":
    main()

import os
import textwrap
import logging
from io import BytesIO
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class Renderer:
    def __init__(self, width=480, height=320, fb_device="/dev/fb0"):
        self.width = width
        self.height = height
        self.fb_device = fb_device
        self.fb_handle = None
        self.art_cache = {}  # Cache para imagens redimensionadas
        self.art_size = 320
        self.art_x, self.art_y = 10, 0
        
        # Tenta abrir o framebuffer uma única vez
        self._open_fb()

    def _open_fb(self):
        """Abre o framebuffer de forma persistente e detecta seu tamanho real e stride."""
        if os.path.exists(self.fb_device):
            try:
                # Tenta garantir permissões
                os.system(f"sudo chmod 666 {self.fb_device}")
                self.fb_handle = open(self.fb_device, "r+b") # Abre para leitura e escrita
                
                # Detecta o tamanho real do framebuffer
                self.fb_handle.seek(0, os.SEEK_END)
                self.real_fb_size = self.fb_handle.tell()
                self.fb_handle.seek(0)
                
                # Detecta o stride (bytes por linha)
                # Se o tamanho total for divisível pela altura, esse é o stride
                self.stride = self.real_fb_size // self.height
                
                logger.info(f"Framebuffer {self.fb_device} aberto. Tamanho: {self.real_fb_size} bytes. Stride: {self.stride} bytes.")
            except Exception as e:
                logger.error(f"Não foi possível abrir o framebuffer {self.fb_device}: {e}")
        else:
            logger.error(f"Dispositivo de framebuffer {self.fb_device} não encontrado.")

    def close(self):
        """Fecha o handle do framebuffer."""
        if self.fb_handle:
            self.fb_handle.close()
            self.fb_handle = None

    def _rgb888_to_bgr565(self, img):
        """Converte RGB888 para BGR565."""
        img_array = np.array(img).astype(np.uint16)
        r, g, b = (img_array[:,:,0] >> 3), (img_array[:,:,1] >> 2), (img_array[:,:,2] >> 3)
        return (b << 11 | g << 5 | r).tobytes()

    def clear(self):
        """Limpa o framebuffer preenchendo todo o dispositivo com zeros."""
        try:
            if not self.fb_handle:
                self._open_fb()
            
            if self.fb_handle:
                self.fb_handle.seek(0)
                # Cria um buffer de zeros do tamanho REAL do dispositivo para garantir limpeza total
                black_buffer = b'\x00' * self.real_fb_size
                self.fb_handle.write(black_buffer)
                self.fb_handle.flush()
                os.fsync(self.fb_handle.fileno())
        except Exception as e:
            logger.error(f"Erro ao limpar framebuffer: {e}")
            self.fb_handle = None

    def _write_to_fb(self, img):
        """Escreve a imagem no framebuffer considerando o stride."""
        if not self.fb_handle:
            self._open_fb()
        
        if self.fb_handle:
            try:
                raw = self._rgb888_to_bgr565(img)
                self.fb_handle.seek(0)
                
                # Se o stride for diferente de width * 2, escrevemos linha por linha
                expected_line_bytes = self.width * 2
                if self.stride != expected_line_bytes:
                    for y in range(self.height):
                        start = y * expected_line_bytes
                        end = start + expected_line_bytes
                        self.fb_handle.seek(y * self.stride)
                        self.fb_handle.write(raw[start:end])
                else:
                    # Caso contrário, escrevemos tudo de uma vez
                    self.fb_handle.write(raw)
                
                self.fb_handle.flush()
                os.fsync(self.fb_handle.fileno())
            except Exception as e:
                logger.error(f"Erro ao escrever no framebuffer: {e}")
                self.fb_handle = None

    def get_font(self, size, bold=False):
        """Tenta carregar fontes comuns ou retorna a padrão."""
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        for path in font_paths:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    def render(self, data, show_capa_mode=False):
        """Renderiza a interface completa."""
        if not data:
            return

        img = Image.new('RGB', (self.width, self.height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)

        f_large = self.get_font(36, bold=True)
        f_med = self.get_font(26)
        f_tech = self.get_font(22, bold=True)

        title = data.get('title', 'Unknown')
        artist = data.get('artist', 'Unknown')
        album = data.get('album', 'Unknown')
        samplerate = data.get('samplerate', '')
        bitdepth = data.get('bitdepth', '')
        albumart = data.get('albumart', '')

        if not show_capa_mode:
            # --- MODO 1: TEXTO ---
            margin_left = 20
            y_cursor = 30
            lines = textwrap.wrap(title, width=22)
            for line in lines[:3]:
                draw.text((margin_left, y_cursor), line, fill=(255, 255, 255), font=f_large)
                y_cursor += 45
            
            y_cursor += 10
            draw.text((margin_left, y_cursor), artist[:35], fill=(200, 200, 200), font=f_med)
            y_cursor += 35
            draw.text((margin_left, y_cursor), album[:40], fill=(120, 120, 120), font=f_med)
            
            y_cursor += 50
            draw.line((margin_left, y_cursor, 200, y_cursor), fill=(60, 180, 60), width=3)
            y_cursor += 15
            quality_str = f"{samplerate} | {bitdepth}" if samplerate and bitdepth else samplerate or bitdepth
            draw.text((margin_left, y_cursor), quality_str, fill=(150, 150, 150), font=f_tech)
        else:
            # --- MODO 2: CAPA ---
            if albumart:
                art = self._get_cached_art(albumart)
                if art:
                    img.paste(art, (self.art_x, self.art_y))

            x_pos = 345
            if samplerate:
                draw.text((x_pos, 25), f"{samplerate}", fill=(60, 180, 60), font=f_tech)
            if bitdepth:
                draw.text((x_pos, 65), f"{bitdepth}", fill=(60, 180, 60), font=f_tech)

        self._write_to_fb(img)

    def _get_cached_art(self, art_url):
        """Busca e redimensiona a capa, com cache."""
        if art_url in self.art_cache:
            return self.art_cache[art_url]

        try:
            # Limpa o cache se ficar muito grande (mais de 10 capas)
            if len(self.art_cache) > 10:
                self.art_cache.clear()

            url = f"http://localhost:3000{art_url}" if art_url.startswith('/') else art_url
            res = requests.get(url, timeout=3)
            art = Image.open(BytesIO(res.content)).convert("RGB")
            art = art.resize((self.art_size, self.art_size), Image.Resampling.LANCZOS)
            self.art_cache[art_url] = art
            return art
        except Exception as e:
            logger.warning(f"Erro ao carregar album art: {e}")
            return None

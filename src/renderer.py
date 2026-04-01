import math
import os
import re
import textwrap
import logging
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayoutProfile:
    """Visual profile for text and artwork layouts."""

    name: str
    bg_color: tuple[int, int, int]
    title_color: tuple[int, int, int]
    artist_color: tuple[int, int, int]
    album_color: tuple[int, int, int]
    quality_text_color: tuple[int, int, int]
    quality_box_color: tuple[int, int, int]
    progress_track_color: tuple[int, int, int]
    progress_height: int
    status_icon_size: int
    title_font_size: int
    artist_font_size: int
    album_font_size: int
    quality_font_size: int


LAYOUT_PROFILES = {
    "classic": LayoutProfile(
        name="classic",
        bg_color=(0, 0, 0),
        title_color=(255, 255, 255),
        artist_color=(200, 200, 200),
        album_color=(120, 120, 120),
        quality_text_color=(255, 255, 255),
        quality_box_color=(255, 255, 255),
        progress_track_color=(40, 40, 40),
        progress_height=6,
        status_icon_size=18,
        title_font_size=42,
        artist_font_size=32,
        album_font_size=24,
        quality_font_size=20,
    ),
    "high_contrast": LayoutProfile(
        name="high_contrast",
        bg_color=(6, 6, 6),
        title_color=(255, 255, 255),
        artist_color=(195, 215, 230),
        album_color=(170, 170, 170),
        quality_text_color=(255, 255, 255),
        quality_box_color=(255, 255, 255),
        progress_track_color=(30, 30, 30),
        progress_height=10,
        status_icon_size=24,
        title_font_size=54,
        artist_font_size=30,
        album_font_size=22,
        quality_font_size=24,
    ),
}

class Renderer:
    def __init__(
        self,
        width=480,
        height=320,
        fb_device="/dev/fb0",
        color_format="RGB565",
        layout_profile="high_contrast",
    ):
        self.width = width
        self.height = height
        self.fb_device = fb_device
        self.color_format = color_format.upper()
        self.layout_profile_name = layout_profile.lower()
        self.layout_profile = LAYOUT_PROFILES.get(
            self.layout_profile_name,
            LAYOUT_PROFILES["high_contrast"],
        )
        self.fb_handle = None
        self.art_cache = {}  # Cache for resized images and their dominant colors
        self.art_cache_meta = {}  # Cache metadata keyed by artwork URL
        self.art_size = 320
        self.art_x, self.art_y = 10, 0
        
        # Default accent color
        self.default_accent = (60, 180, 60)
        
        # Try to open the framebuffer once
        self._open_fb()

    def _open_fb(self):
        """Opens the framebuffer persistently and detects its real size."""
        if os.path.exists(self.fb_device):
            try:
                # Try to ensure permissions
                os.system(f"sudo chmod 666 {self.fb_device}")
                self.fb_handle = open(self.fb_device, "r+b") # Open for read and write
                
                # Detect the real size of the framebuffer
                self.fb_handle.seek(0, os.SEEK_END)
                self.real_fb_size = self.fb_handle.tell()
                self.fb_handle.seek(0)
                
                logger.info(f"Framebuffer {self.fb_device} opened. Detected size: {self.real_fb_size} bytes. Format: {self.color_format}")
            except Exception as e:
                logger.error(f"Could not open framebuffer {self.fb_device}: {e}")
        else:
            logger.error(f"Framebuffer device {self.fb_device} not found.")

    def close(self):
        """Closes the framebuffer handle."""
        if self.fb_handle:
            self.fb_handle.close()
            self.fb_handle = None

    def _rgb888_to_565(self, img):
        """Converts RGB888 to 565 according to format (RGB or BGR)."""
        img_array = np.array(img).astype(np.uint16)
        r, g, b = (img_array[:,:,0] >> 3), (img_array[:,:,1] >> 2), (img_array[:,:,2] >> 3)
        
        if self.color_format == "BGR565":
            # B (bits 11-15), G (bits 5-10), R (bits 0-4)
            return (b << 11 | g << 5 | r).tobytes()
        else:
            # Default: RGB565 - R (bits 11-15), G (bits 5-10), B (bits 0-4)
            return (r << 11 | g << 5 | b).tobytes()

    def clear(self, use_fsync=True):
        """Clears the framebuffer by filling the entire device with zeros."""
        try:
            if not self.fb_handle:
                self._open_fb()
            
            if self.fb_handle:
                self.fb_handle.seek(0)
                # Create a zero buffer of the REAL size of the device to ensure full clearing
                black_buffer = b'\x00' * self.real_fb_size
                self.fb_handle.write(black_buffer)
                self.fb_handle.flush()
                if use_fsync:
                    try:
                        os.fsync(self.fb_handle.fileno())
                    except OSError:
                        pass # Some devices do not support fsync
        except Exception as e:
            logger.error(f"Error clearing framebuffer: {e}")
            self.fb_handle = None

    def _write_to_fb(self, img):
        """Writes the image to the framebuffer as directly as possible."""
        if not self.fb_handle:
            self._open_fb()
        
        if self.fb_handle:
            try:
                raw = self._rgb888_to_565(img)
                self.fb_handle.seek(0)
                
                # Write exactly the number of bytes for the image (WIDTH * HEIGHT * 2)
                # without trying to fill the entire device to avoid misalignment
                img_bytes = self.width * self.height * 2
                self.fb_handle.write(raw[:img_bytes])
                
                self.fb_handle.flush()
                # Optional: fsync can cause slowness on some SPI drivers
                # but helps avoid 'tearing'
                try:
                    os.fsync(self.fb_handle.fileno())
                except:
                    pass
            except Exception as e:
                logger.error(f"Error writing to framebuffer: {e}")
                self.fb_handle = None

    def get_font(self, size, bold=False):
        """Tries to load common fonts or returns the default."""
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        for path in font_paths:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    def _get_dominant_color(self, img):
        """Extracts the dominant color from an image."""
        small_img = img.resize((1, 1), Image.Resampling.BILINEAR)
        res = small_img.getpixel((0, 0))
        # Ensure it's not too dark to be visible
        if sum(res) < 60:
            return self.default_accent
        return res

    def _format_time(self, seconds):
        """Formats seconds into MM:SS."""
        if seconds is None: return "00:00"
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    def _draw_centered_text(self, draw, text, y, font, fill, max_width=440):
        """Draws text centered on the screen, scaling font down if it overflows."""
        # Try to fit the text by reducing font size if necessary
        current_font = font
        font_size = getattr(font, 'size', 24)
        
        while font_size > 12:
            bbox = draw.textbbox((0, 0), text, font=current_font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                break
            font_size -= 2
            current_font = self.get_font(font_size, bold=True if font_size > 20 else False)
            
        bbox = draw.textbbox((0, 0), text, font=current_font)
        w = bbox[2] - bbox[0]
        draw.text(((self.width - w) // 2, y), text, fill=fill, font=current_font)
        return y + (bbox[3] - bbox[1]) + 10

    def _normalize_source_label(self, playback_source):
        """Normalize source text for compact UI chips."""
        source = str(playback_source or "").strip()
        if not source:
            return ""

        source_lower = source.lower()
        if source_lower == "physical":
            return "VINYL"
        return source.upper()

    def _is_vinyl_source(self, playback_source):
        """Heuristic to identify vinyl/phono sources from free-form input."""
        source = str(playback_source or "").strip().lower()
        if not source:
            return False
        return any(token in source for token in ("vinyl", "phono", "record", "lp", "physical"))

    def _is_cd_source(self, playback_source):
        """Heuristic to identify CD sources from free-form input."""
        source = str(playback_source or "").strip().lower()
        if not source:
            return False
        return any(token in source for token in ("cd", "compact disc", "compactdisc"))

    def _coerce_track_number(self, value):
        """Return a positive integer track number from loose input, or None."""
        if value is None:
            return None

        if isinstance(value, int):
            return value if value > 0 else None

        value_str = str(value).strip()
        if not value_str:
            return None

        match = re.search(r"(\d{1,3})", value_str)
        if not match:
            return None

        track_number = int(match.group(1))
        return track_number if track_number > 0 else None

    def _parse_media_position(self, data):
        """Parse side/track from structured or manual fields and return a UI label."""
        if not data:
            return ""

        side_candidates = (
            data.get("media_side"),
            data.get("side"),
            data.get("vinyl_side"),
        )
        track_candidates = (
            data.get("media_track_number"),
            data.get("track_number"),
            data.get("track_no"),
            data.get("vinyl_track"),
        )
        raw_candidates = (
            data.get("media_position"),
            data.get("media_position_label"),
            data.get("vinyl_position"),
            data.get("vinyl_position_raw"),
            data.get("position"),
        )

        side = ""
        for candidate in side_candidates:
            candidate_str = str(candidate or "").strip().upper()
            if candidate_str and re.match(r"^[A-Z]$", candidate_str):
                side = candidate_str
                break

        track_number = None
        for candidate in track_candidates:
            track_number = self._coerce_track_number(candidate)
            if track_number is not None:
                break

        if side and track_number is not None:
            return f"Side {side} | Track {track_number}"
        if side:
            return f"Side {side}"
        if track_number is not None:
            return f"Track {track_number}"

        for raw in raw_candidates:
            raw_str = str(raw or "").strip()
            if not raw_str:
                continue

            cleaned = re.sub(r"[^A-Za-z0-9]+", "", raw_str).upper()

            # 1A, 12B
            m_num_letter = re.match(r"^(\d{1,3})([A-Z])$", cleaned)
            if m_num_letter:
                return f"Side {m_num_letter.group(2)} | Track {int(m_num_letter.group(1))}"

            # A1, B12
            m_letter_num = re.match(r"^([A-Z])(\d{1,3})$", cleaned)
            if m_letter_num:
                return f"Side {m_letter_num.group(1)} | Track {int(m_letter_num.group(2))}"

            m_side = re.search(r"(?:SIDE|LADO)\s*([A-Z])", raw_str, flags=re.IGNORECASE)
            m_track = re.search(r"(?:TRACK|FAIXA)\s*(\d{1,3})", raw_str, flags=re.IGNORECASE)
            if m_side and m_track:
                return f"Side {m_side.group(1).upper()} | Track {int(m_track.group(1))}"
            if m_track:
                return f"Track {int(m_track.group(1))}"
            if m_side:
                return f"Side {m_side.group(1).upper()}"

            # Final fallback: short sanitized manual input.
            fallback = re.sub(r"\s+", " ", raw_str).strip()
            if fallback:
                return textwrap.shorten(fallback, width=20, placeholder="...")

        return ""

    def _build_info_chips(self, data):
        """Build source/detail chips shown above the progress bar."""
        samplerate = str(data.get("samplerate") or "").strip()
        bitdepth = str(data.get("bitdepth") or "").strip()
        playback_source = data.get("playback_source")

        source_chip = self._normalize_source_label(playback_source)
        position_chip = self._parse_media_position(data)
        quality_chip = " | ".join([part for part in (samplerate, bitdepth) if part])

        is_vinyl = self._is_vinyl_source(playback_source)
        is_cd = self._is_cd_source(playback_source)

        details_chip = ""
        if is_vinyl or is_cd:
            details_chip = position_chip or quality_chip
        else:
            details_chip = quality_chip or position_chip

        if is_vinyl and not details_chip:
            details_chip = "Track ?"

        chips = []
        if source_chip:
            chips.append(source_chip)
        if details_chip:
            chips.append(details_chip)
        return chips

    def _draw_centered_chips(self, draw, chips, box_y, font, outline_color, text_color, profile_name):
        """Draw one or two centered info chips with fixed spacing."""
        if not chips:
            return

        box_height = 36 if profile_name == "high_contrast" else 30
        pad_x = 14 if profile_name == "high_contrast" else 10
        gap = 10

        chip_widths = []
        for chip in chips:
            cw, _ = draw.textbbox((0, 0), chip, font=font)[2:]
            chip_widths.append(cw + 2 * pad_x)

        total_width = sum(chip_widths) + (gap * (len(chip_widths) - 1))
        x = (self.width - total_width) // 2

        for idx, chip in enumerate(chips):
            chip_w = chip_widths[idx]
            draw.rectangle(
                (x, box_y, x + chip_w, box_y + box_height),
                fill=(0, 0, 0) if profile_name == "high_contrast" else None,
                outline=outline_color,
                width=3 if profile_name == "high_contrast" else 2,
            )
            tw, th = draw.textbbox((0, 0), chip, font=font)[2:]
            text_x = x + (chip_w - tw) // 2
            text_y = box_y + (box_height - th) // 2 - (1 if profile_name == "high_contrast" else 0)
            draw.text((text_x, text_y), chip, fill=text_color, font=font)
            x += chip_w + gap

    def render_idle_screen(self):
        """Renders a stylized grayscale logo for the idle/startup state."""
        img = Image.new('RGB', (self.width, self.height), color=(10, 10, 10))
        draw = ImageDraw.Draw(img)
        
        center_x = self.width // 2
        center_y = self.height // 2
        
        # Draw a stylized icon (sound waves/bars)
        bar_width = 12
        gap = 8
        colors = [(40, 40, 40), (70, 70, 70), (100, 100, 100), (70, 70, 70), (40, 40, 40)]
        heights = [40, 70, 100, 70, 40]
        
        start_x = center_x - (len(heights) * (bar_width + gap) - gap) // 2
        for i, h in enumerate(heights):
            x = start_x + i * (bar_width + gap)
            draw.rounded_rectangle(
                (x, center_y - h // 2 - 30, x + bar_width, center_y + h // 2 - 30),
                radius=4,
                fill=colors[i]
            )
            
        # Draw text
        f_logo = self.get_font(28, bold=True)
        f_sub = self.get_font(16)
        
        text1 = "Oceano Player"
        text2 = "Waiting for media..."
        
        bbox1 = draw.textbbox((0, 0), text1, font=f_logo)
        w1 = bbox1[2] - bbox1[0]
        draw.text(((self.width - w1) // 2, center_y + 40), text1, fill=(140, 140, 140), font=f_logo)
        
        bbox2 = draw.textbbox((0, 0), text2, font=f_sub)
        w2 = bbox2[2] - bbox2[0]
        draw.text(((self.width - w2) // 2, center_y + 80), text2, fill=(80, 80, 80), font=f_sub)
        
        self._write_to_fb(img)
        return img

    def _render_missing_artwork_card(self, title, artist, album):
        """Render a built-in placeholder card when artwork is unavailable."""
        card = Image.new('RGB', (self.art_size, self.art_size), color=(18, 18, 18))
        draw = ImageDraw.Draw(card)

        accent = self.default_accent
        muted = (90, 90, 90)
        panel = (28, 28, 28)
        highlight = (210, 210, 210)

        draw.rounded_rectangle((0, 0, self.art_size - 1, self.art_size - 1), radius=28, fill=panel)
        draw.rounded_rectangle((12, 12, self.art_size - 13, self.art_size - 13), radius=22, outline=accent, width=3)

        for stripe_y in (36, 58, 80):
            draw.rounded_rectangle((28, stripe_y, self.art_size - 28, stripe_y + 6), radius=3, fill=(40, 40, 40))

        center_x = self.art_size // 2
        center_y = 150
        draw.ellipse((center_x - 62, center_y - 62, center_x + 62, center_y + 62), outline=highlight, width=4)
        draw.ellipse((center_x - 18, center_y - 18, center_x + 18, center_y + 18), fill=accent)
        draw.arc((center_x - 82, center_y - 82, center_x + 82, center_y + 82), start=210, end=332, fill=accent, width=5)

        label_font = self.get_font(18, bold=True)
        title_font = self.get_font(24, bold=True)
        meta_font = self.get_font(16)

        label = "NO COVER"
        label_box = draw.textbbox((0, 0), label, font=label_font)
        label_width = label_box[2] - label_box[0]
        draw.text(((self.art_size - label_width) // 2, 230), label, fill=highlight, font=label_font)

        title_text = (title or album or "Unknown Album")[:22]
        artist_text = (artist or album or "Unknown Artist")[:28]
        album_text = album[:28] if album else "Artwork unavailable"

        title_box = draw.textbbox((0, 0), title_text, font=title_font)
        title_width = title_box[2] - title_box[0]
        draw.text(((self.art_size - title_width) // 2, 256), title_text, fill=(255, 255, 255), font=title_font)

        artist_box = draw.textbbox((0, 0), artist_text, font=meta_font)
        artist_width = artist_box[2] - artist_box[0]
        draw.text(((self.art_size - artist_width) // 2, 286), artist_text, fill=(175, 175, 175), font=meta_font)

        album_box = draw.textbbox((0, 0), album_text, font=meta_font)
        album_width = album_box[2] - album_box[0]
        draw.text(((self.art_size - album_width) // 2, 306), album_text, fill=muted, font=meta_font)

        return card

    def render(self, data, show_artwork_mode=False, show_hybrid_mode=False):
        """Renders the complete V2 interface."""
        if not data:
            return

        # Ensure framebuffer is open
        if not self.fb_handle:
            logger.info("Framebuffer handle was closed, re-opening.")
            self._open_fb()

        profile = self.layout_profile
        img = Image.new('RGB', (self.width, self.height), color=profile.bg_color)
        draw = ImageDraw.Draw(img)

        # Fonts
        f_xl = self.get_font(profile.title_font_size, bold=True)
        f_large = self.get_font(profile.artist_font_size, bold=True)
        f_med = self.get_font(profile.album_font_size, bold=True if profile.name == "high_contrast" else False)
        f_small = self.get_font(profile.status_icon_size)
        f_tech = self.get_font(profile.quality_font_size, bold=True)

        # Data
        title = data.get('title', 'Unknown')
        artist = data.get('artist', 'Unknown')
        album = data.get('album', 'Unknown')
        samplerate = data.get('samplerate', '')
        bitdepth = data.get('bitdepth', '')
        playback_source = data.get('playback_source', '')
        albumart = data.get('albumart', '')
        status = data.get('status', 'stop')
        
        # Progress Calculation
        seek = data.get('seek', 0) or 0
        if seek is None:
            seek = 0
        
        duration = data.get('duration', 0) or 0
        if duration is None:
            duration = 0
        
        progress = 0
        if duration > 0:
            # Keep both values in milliseconds to avoid unit mismatch.
            progress = min(seek / duration, 1.0)

        # Get Art and Accent Color
        accent_color = self.default_accent
        art = None
        resolved_artwork = data.get('_resolved_artwork')
        if resolved_artwork:
            art_data = self._get_cached_art(
                resolved_artwork.get('cache_key'),
                resolved_artwork.get('image'),
                source=resolved_artwork.get('source', 'unknown')
            )
            if art_data:
                art, accent_color = art_data
            else:
                logger.warning(f"[RENDER] Failed to load artwork, using default accent")
        elif albumart:
            logger.debug("[RENDER] Media player did not provide resolved artwork")
        else:
            logger.debug(f"[RENDER] No albumart provided by media player")

        # --- DRAW PROGRESS BAR (Common for both modes) ---
        pb_height = profile.progress_height
        pb_y = self.height - pb_height
        progress_color = accent_color
        draw.rectangle((0, pb_y, self.width, self.height), fill=profile.progress_track_color) # Background
        draw.rectangle((0, pb_y, int(self.width * progress), self.height), fill=progress_color) # Progress

        # --- DRAW STATUS ICON ---
        icon = "▶" if status == 'play' else "II"
        _, th = draw.textbbox((0, 0), icon, font=f_small)[2:]
        draw.text((10, pb_y - th - 10), icon, fill=progress_color, font=f_small)

        if show_hybrid_mode:
            # --- MODE 3: HYBRID (ART + TEXT ON THE SAME SCREEN) ---
            hybrid_art_size = 184 if profile.name == "high_contrast" else 170
            art_x = 16
            art_y = 14

            if art:
                hybrid_art = art.resize((hybrid_art_size, hybrid_art_size), Image.Resampling.LANCZOS)
            else:
                placeholder_art = self._render_missing_artwork_card(title, artist, album)
                hybrid_art = placeholder_art.resize((hybrid_art_size, hybrid_art_size), Image.Resampling.LANCZOS)
            img.paste(hybrid_art, (art_x, art_y))

            text_x = art_x + hybrid_art_size + 16
            text_w = self.width - text_x - 12
            y_cursor = 16

            title_wrap_width = 14 if profile.name == "high_contrast" else 16
            title_lines = textwrap.wrap(title, width=title_wrap_width)[:2]
            for line in title_lines:
                draw.text((text_x, y_cursor), line, fill=profile.title_color, font=f_large)
                line_h = draw.textbbox((0, 0), line, font=f_large)[3]
                y_cursor += line_h + 4

            artist_text = textwrap.shorten(artist, width=30, placeholder="...")
            draw.text((text_x, y_cursor + 4), artist_text, fill=profile.artist_color, font=f_med)
            y_cursor += draw.textbbox((0, 0), artist_text, font=f_med)[3] + 8

            album_text = textwrap.shorten(album, width=32, placeholder="...")
            draw.text((text_x, y_cursor), album_text, fill=profile.album_color, font=f_med)

            info_chips = self._build_info_chips(data)
            if info_chips:
                combined = " | ".join(info_chips[:2])
                quality_text = textwrap.shorten(combined, width=28, placeholder="...")
                qw, qh = draw.textbbox((0, 0), quality_text, font=f_tech)[2:]
                box_y = pb_y - (qh + 20)
                box_x1 = text_x
                box_x2 = min(text_x + text_w, text_x + qw + 16)
                draw.rectangle(
                    (box_x1, box_y, box_x2, box_y + qh + 12),
                    fill=(0, 0, 0),
                    outline=accent_color,
                    width=2,
                )
                draw.text((text_x + 8, box_y + 6), quality_text, fill=profile.quality_text_color, font=f_tech)

        elif not show_artwork_mode:
            # --- MODE 1: CENTERED TEXT ---
            y_cursor = 18 if profile.name == "high_contrast" else 35
            
            # Title (wrapped if needed, then centered)
            title_wrap_width = 20 if profile.name == "high_contrast" else 25
            title_lines = textwrap.wrap(title, width=title_wrap_width)
            for line in title_lines[:2]:
                y_cursor = self._draw_centered_text(draw, line, y_cursor, f_xl, profile.title_color)
            
            y_cursor += 14 if profile.name == "high_contrast" else 5
            # Artist
            artist_max_chars = 34 if profile.name == "high_contrast" else 40
            y_cursor = self._draw_centered_text(draw, artist[:artist_max_chars], y_cursor, f_large, profile.artist_color)
            
            # Album
            album_max_chars = 40 if profile.name == "high_contrast" else 45
            y_cursor = self._draw_centered_text(draw, album[:album_max_chars], y_cursor, f_med, profile.album_color)
            
            # Source and media-position chips at bottom center.
            info_chips = self._build_info_chips(data)
            if info_chips:
                box_y = pb_y - 56 if profile.name == "high_contrast" else pb_y - 50
                outline = profile.quality_box_color if profile.name == "high_contrast" else accent_color
                text_color = profile.quality_text_color if profile.name == "high_contrast" else accent_color
                self._draw_centered_chips(
                    draw,
                    info_chips[:2],
                    box_y,
                    f_tech,
                    outline,
                    text_color,
                    profile.name,
                )

        else:
            # --- MODE 2: COVER (CENTERED) ---
            art_x = (self.width - self.art_size) // 2
            art_y = (self.height - self.art_size) // 2 - 10  # Slight upward offset for progress bar
            if art:
                img.paste(art, (art_x, art_y))
            else:
                placeholder_art = self._render_missing_artwork_card(title, artist, album)
                img.paste(placeholder_art, (art_x, art_y))

        self._write_to_fb(img)

    def clear_art_cache(self):
        """Clears the album art cache."""
        self.art_cache.clear()
        self.art_cache_meta.clear()

    def _prepare_artwork_on_cache_miss(self, artwork_image):
        """Resize resolved artwork and compute its dominant color."""
        accent = self._get_dominant_color(artwork_image)

        art_resized = artwork_image.resize((self.art_size, self.art_size), Image.Resampling.LANCZOS)
        return art_resized, accent

    # ------------------------------------------------------------------ #
    # VU meter rendering                                                   #
    # ------------------------------------------------------------------ #

    # Gauge geometry — PIL angles: 0=east, clockwise.
    # Arc spans from lower-left (215°) through top (270°) to lower-right (325°).
    # dB range matches a classic VU meter: -20 VU to +3 VU.
    _VU_ARC_START  = 215    # PIL °  →  -20 dB
    _VU_ARC_END    = 325    # PIL °  →  +3 dB
    _VU_DB_MIN     = -20.0
    _VU_DB_MAX     =   3.0
    _VU_ZONE_YEL   =  -7.0  # green → yellow boundary
    _VU_ZONE_RED   =   0.0  # yellow → red boundary

    @staticmethod
    def _db_to_vu_angle(db: float) -> float:
        """Map a dBFS value to a PIL gauge angle."""
        t = (db - Renderer._VU_DB_MIN) / (Renderer._VU_DB_MAX - Renderer._VU_DB_MIN)
        t = max(0.0, min(t, 1.0))
        return Renderer._VU_ARC_START + t * (Renderer._VU_ARC_END - Renderer._VU_ARC_START)

    @staticmethod
    def _rms_to_db(rms: float) -> float:
        """Convert linear RMS [0, 1] to dBFS, clamped to [DB_MIN, DB_MAX]."""
        if rms < 1e-7:
            return Renderer._VU_DB_MIN
        return max(Renderer._VU_DB_MIN, min(20.0 * math.log10(rms), Renderer._VU_DB_MAX))

    def render_vu(
        self,
        vu_left: float,
        vu_right: float,
        peak_left: float,
        peak_right: float,
        state: dict | None,
    ) -> None:
        """Render two analog needle VU meters inspired by the Magnat MR 780.

        Layout (480×320):
          - Two gauge cards (dark panel, amber outline) side by side, 254 px tall
          - Footer strip (58 px): title + artist centred, source badge right
          - Progress bar (8 px) at the very bottom in amber
        """
        if not self.fb_handle:
            self._open_fb()

        FOOTER_H = 58
        PB_H = 8
        GAUGE_H = self.height - FOOTER_H - PB_H   # 254 px
        CARD_PAD = 8
        CARD_W = (self.width - 3 * CARD_PAD) // 2  # 228 px
        RADIUS = 108
        PIVOT_Y = GAUGE_H - 18                      # 236

        # Card x-boundaries
        L_X1, L_X2 = CARD_PAD, CARD_PAD + CARD_W                          # 8 … 236
        R_X1, R_X2 = self.width - CARD_PAD - CARD_W, self.width - CARD_PAD  # 244 … 472
        LEFT_CX  = (L_X1 + L_X2) // 2   # 122
        RIGHT_CX = (R_X1 + R_X2) // 2   # 358

        img = Image.new("RGB", (self.width, self.height), (4, 4, 8))
        draw = ImageDraw.Draw(img)

        # Gauge card backgrounds
        for x1, x2 in ((L_X1, L_X2), (R_X1, R_X2)):
            draw.rounded_rectangle(
                (x1, CARD_PAD, x2, GAUGE_H - CARD_PAD),
                radius=14,
                fill=(10, 10, 16),
                outline=(58, 40, 8),
                width=2,
            )

        # Gauges
        for rms, peak, cx, ch in (
            (vu_left,  peak_left,  LEFT_CX,  "L"),
            (vu_right, peak_right, RIGHT_CX, "R"),
        ):
            self._draw_vu_gauge(draw, cx, PIVOT_Y, RADIUS, rms, peak, ch)

        # Footer — title + artist
        footer_y = GAUGE_H + 8
        f_title  = self.get_font(20, bold=True)
        f_artist = self.get_font(16)
        f_source = self.get_font(13)

        if state:
            title  = state.get("title")  or ""
            artist = state.get("artist") or ""
            source = state.get("playback_source") or ""

            if title and title != "Unknown":
                t = textwrap.shorten(title, width=40, placeholder="…")
                bx = draw.textbbox((0, 0), t, font=f_title)
                tw = bx[2] - bx[0]
                draw.text(((self.width - tw) // 2, footer_y),
                          t, fill=(240, 240, 240), font=f_title)

            if artist and artist != "Unknown":
                a = textwrap.shorten(artist, width=48, placeholder="…")
                bx = draw.textbbox((0, 0), a, font=f_artist)
                aw = bx[2] - bx[0]
                draw.text(((self.width - aw) // 2, footer_y + 26),
                          a, fill=(145, 165, 185), font=f_artist)

            if source:
                bx = draw.textbbox((0, 0), source, font=f_source)
                sw, sh = bx[2] - bx[0], bx[3] - bx[1]
                sx, sy = self.width - sw - 16, footer_y + 8
                draw.rectangle((sx - 5, sy - 3, sx + sw + 5, sy + sh + 3),
                                outline=(80, 52, 10), width=1)
                draw.text((sx, sy), source, fill=(155, 95, 25), font=f_source)

        # Progress bar
        seek     = (state or {}).get("seek", 0) or 0
        duration = (state or {}).get("duration", 0) or 0
        progress = min(seek / duration, 1.0) if duration > 0 else 0.0
        pb_y = self.height - PB_H
        draw.rectangle((0, pb_y, self.width, self.height), fill=(18, 10, 3))
        if progress > 0:
            draw.rectangle(
                (0, pb_y, int(self.width * progress), self.height),
                fill=(200, 100, 15),
            )

        self._write_to_fb(img)

    def _draw_vu_gauge(
        self,
        draw: ImageDraw.ImageDraw,
        cx: int,
        cy: int,   # pivot Y
        r: int,
        rms: float,
        peak: float,
        label: str,
    ) -> None:
        """Draw one VU needle gauge.

        The arc spans _VU_ARC_START → _VU_ARC_END (PIL clockwise degrees),
        passing through the top (270°). The pivot is at (cx, cy).
        """
        bbox = [cx - r, cy - r, cx + r, cy + r]

        # 1. Dim background arc (shows full scale even at silence)
        draw.arc(bbox, self._VU_ARC_START, self._VU_ARC_END, fill=(28, 20, 6), width=12)

        # 2. Coloured zone arcs
        angle_yel = self._db_to_vu_angle(self._VU_ZONE_YEL)
        angle_red = self._db_to_vu_angle(self._VU_ZONE_RED)
        draw.arc(bbox, self._VU_ARC_START, angle_yel, fill=(0, 130, 45),  width=10)
        draw.arc(bbox, angle_yel,          angle_red,  fill=(185, 135, 0), width=10)
        draw.arc(bbox, angle_red,          self._VU_ARC_END, fill=(200, 30, 15), width=10)

        # 3. Tick marks (drawn inward from the arc outer edge)
        TICKS = {-20: True, -15: False, -10: True, -7: False,
                 -5: False, -3: False, 0: True, 3: True}
        LABELS = {-20, -10, 0, 3}
        f_tick = self.get_font(11)

        for db, major in TICKS.items():
            ang = math.radians(self._db_to_vu_angle(db))
            outer = r + 1
            inner = r - (16 if major else 8)
            ox, oy = cx + outer * math.cos(ang), cy + outer * math.sin(ang)
            ix, iy = cx + inner * math.cos(ang), cy + inner * math.sin(ang)
            draw.line([(ix, iy), (ox, oy)],
                      fill=(210, 155, 45) if major else (95, 68, 18),
                      width=2 if major else 1)

            if db in LABELS:
                lr = r - 30
                lx = cx + lr * math.cos(ang)
                ly = cy + lr * math.sin(ang)
                txt = f"+{db}" if db > 0 else str(db)
                draw.text((lx, ly), txt,
                          fill=(165, 110, 28), font=f_tick, anchor="mm")

        # 4. Peak-hold marker — bright line segment on the arc
        if peak > 1e-6:
            db_pk = self._rms_to_db(peak)
            ang   = math.radians(self._db_to_vu_angle(db_pk))
            o_x = cx + (r + 2)  * math.cos(ang)
            o_y = cy + (r + 2)  * math.sin(ang)
            i_x = cx + (r - 11) * math.cos(ang)
            i_y = cy + (r - 11) * math.sin(ang)
            draw.line([(i_x, i_y), (o_x, o_y)], fill=(255, 252, 200), width=3)

        # 5. Needle
        db_rms     = self._rms_to_db(rms)
        needle_ang = math.radians(self._db_to_vu_angle(db_rms))
        nlen       = r - 14
        nx = cx + nlen * math.cos(needle_ang)
        ny = cy + nlen * math.sin(needle_ang)

        draw.line([(cx, cy), (nx + 1, ny + 1)], fill=(45, 25, 5), width=5)  # shadow
        draw.line([(cx, cy), (nx, ny)],          fill=(255, 148, 8), width=3)  # needle

        # 6. Pivot cap
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(48, 32, 6))
        draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(210, 130, 25))
        draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(255, 215, 90))

        # 7. Channel label (L / R) — top-centre of the card area above the arc
        f_lbl = self.get_font(18, bold=True)
        arc_top_y = cy - r
        lbl_y     = max(12, arc_top_y - 40)
        bx        = draw.textbbox((0, 0), label, font=f_lbl)
        draw.text((cx - (bx[2] - bx[0]) // 2, lbl_y),
                  label, fill=(185, 105, 22), font=f_lbl)

        # 8. Peak dB value — below channel label
        if peak > 1e-6:
            db_pk  = self._rms_to_db(peak)
            db_txt = f"{db_pk:+.0f} dB" if db_pk >= 0 else f"{db_pk:.0f} dB"
            f_db   = self.get_font(12)
            bx     = draw.textbbox((0, 0), db_txt, font=f_db)
            pk_col = (205, 45, 20) if db_pk >= 0 else (170, 120, 15) if db_pk >= -7 else (70, 135, 55)
            draw.text((cx - (bx[2] - bx[0]) // 2, lbl_y + 24),
                      db_txt, fill=pk_col, font=f_db)

    def _get_cached_art(self, cache_key, artwork_image, source="unknown"):
        """Cache resized artwork and accent color using a media-player-provided key."""
        if not cache_key or artwork_image is None:
            return None

        if cache_key in self.art_cache:
            return self.art_cache[cache_key]

        try:
            if len(self.art_cache) > 10:
                self.art_cache.clear()
                self.art_cache_meta.clear()
            art_resized, accent = self._prepare_artwork_on_cache_miss(artwork_image)
            
            self.art_cache[cache_key] = (art_resized, accent)
            self.art_cache_meta[cache_key] = {"source": source}
            return art_resized, accent
        except Exception as e:
            logger.warning(f"[ART ERROR] Failed to prepare artwork {cache_key}: {type(e).__name__}: {e}")
            return None

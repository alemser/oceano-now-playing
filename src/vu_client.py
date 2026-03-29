"""VUClient — reads real-time stereo RMS levels from the oceano-source-detector
Unix socket and applies analog VU meter ballistics (fast attack, slow decay,
peak hold).

Socket protocol: 8-byte frames, little-endian float32 left + float32 right RMS,
published by oceano-source-detector at ~5 frames/sec (one per 8192-sample
audio buffer at 44.1 kHz ≈ 186 ms).
"""

import math
import socket
import struct
import threading
import time
import logging

logger = logging.getLogger(__name__)

# Ballistics constants
_ATTACK_TAU = 0.050   # 50 ms — fast attack to catch transients
_DECAY_TAU = 0.300    # 300 ms — slow decay for classic VU feel
_PEAK_HOLD = 1.5      # seconds to hold peak before dropping


class VUClient:
    """Background thread that reads VU frames and exposes smoothed levels.

    Usage:
        client = VUClient("/tmp/oceano-vu.sock")
        client.start()
        left, right, peak_l, peak_r = client.get_levels()
        client.stop()
    """

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path

        self._lock = threading.Lock()
        self._left: float = 0.0
        self._right: float = 0.0
        self._peak_left: float = 0.0
        self._peak_right: float = 0.0
        self._peak_left_at: float = 0.0
        self._peak_right_at: float = 0.0

        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="vu-client")
        self._thread.start()
        logger.info("VUClient started (socket=%s)", self.socket_path)

    def stop(self) -> None:
        self._running = False

    def get_levels(self) -> tuple[float, float, float, float]:
        """Return (left, right, peak_left, peak_right) RMS in [0.0, 1.0]."""
        with self._lock:
            return self._left, self._right, self._peak_left, self._peak_right

    # ------------------------------------------------------------------ #
    # Background thread                                                    #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        while self._running:
            try:
                self._connect_and_read()
            except Exception as e:
                logger.debug("VU socket error: %s — retrying in 2s", e)
                self._reset_to_zero()
                time.sleep(2)

    def _connect_and_read(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(self.socket_path)
        sock.settimeout(1.0)
        logger.debug("VU socket connected")

        buf = b""
        last_t = time.monotonic()

        try:
            while self._running:
                try:
                    chunk = sock.recv(256)
                except TimeoutError:
                    # No frames for a second — decay toward silence.
                    now = time.monotonic()
                    self._apply_decay(now - last_t)
                    last_t = now
                    continue

                if not chunk:
                    break

                buf += chunk
                while len(buf) >= 8:
                    left_raw, right_raw = struct.unpack_from("<ff", buf)
                    buf = buf[8:]
                    now = time.monotonic()
                    self._apply_ballistics(left_raw, right_raw, now - last_t, now)
                    last_t = now
        finally:
            sock.close()

    # ------------------------------------------------------------------ #
    # Ballistics                                                           #
    # ------------------------------------------------------------------ #

    def _apply_ballistics(self, l: float, r: float, dt: float, now: float) -> None:
        with self._lock:
            self._left = _smooth(self._left, l, dt)
            self._right = _smooth(self._right, r, dt)
            self._peak_left, self._peak_left_at = _update_peak(
                self._left, self._peak_left, self._peak_left_at, now
            )
            self._peak_right, self._peak_right_at = _update_peak(
                self._right, self._peak_right, self._peak_right_at, now
            )

    def _apply_decay(self, dt: float) -> None:
        with self._lock:
            self._left = _smooth(self._left, 0.0, dt)
            self._right = _smooth(self._right, 0.0, dt)

    def _reset_to_zero(self) -> None:
        with self._lock:
            self._left = 0.0
            self._right = 0.0


# ------------------------------------------------------------------ #
# Module-level helpers (pure functions, easy to unit-test)            #
# ------------------------------------------------------------------ #

def _smooth(current: float, target: float, dt: float) -> float:
    """First-order low-pass filter with separate attack/decay time constants."""
    tau = _ATTACK_TAU if target >= current else _DECAY_TAU
    alpha = 1.0 - math.exp(-dt / tau)
    return current + alpha * (target - current)


def _update_peak(
    value: float, peak: float, peak_at: float, now: float
) -> tuple[float, float]:
    """Return updated (peak, peak_at) with hold-then-drop behaviour."""
    if value >= peak:
        return value, now
    if now - peak_at > _PEAK_HOLD:
        return value, now
    return peak, peak_at

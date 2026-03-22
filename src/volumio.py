import json
import logging
import time
from websocket import create_connection
from media_player import MediaPlayer

logger = logging.getLogger(__name__)

class VolumioClient(MediaPlayer):
    def __init__(self, url: str) -> None:
        self.url = url
        self.ws = None

    def connect(self) -> bool:
        """Connects to Volumio's WebSocket.

        Returns:
            True if connection was successful, False otherwise.
        """
        try:
            self.ws = create_connection(self.url, timeout=10)
            self.ws.send('42["getState"]')
            return True
        except Exception as e:
            logger.error(f"Error connecting to Volumio at {self.url}: {e}")
            return False

    def get_state(self) -> None:
        """Requests the current state explicitly."""
        if self.ws:
            try:
                self.ws.send('42["getState"]')
            except Exception as e:
                logger.error(f"Error requesting state from Volumio: {e}")
                self.ws = None

    def receive_message(self, timeout: float = 1.0) -> dict | None:
        """Receives and processes WebSocket messages.

        Args:
            timeout: Maximum seconds to wait for a message.

        Returns:
            A state dictionary when a new playback state is available,
            or None if no message arrived within the timeout.
        """
        if not self.ws:
            return None

        try:
            self.ws.settimeout(timeout)
            result = self.ws.recv()
            
            # Socket.io heartbeat
            if result == '2':
                self.ws.send('3')
                return None
                
            # Check if it's a state message (pushState or getState response)
            if '"pushState"' in result:
                start = result.find('{')
                end = result.rfind('}')
                if start != -1 and end != -1:
                    json_str = result[start:end+1]
                    return json.loads(json_str)
        except (TimeoutError, Exception):
            # Timeouts are expected if Volumio doesn't send anything
            pass
        return None

    def is_connected(self) -> bool:
        """Checks if the connection is active.

        Returns:
            True if the connection is active, False otherwise.
        """
        return self.ws is not None

    def close(self) -> None:
        """Closes the connection."""
        if self.ws:
            self.ws.close()
            self.ws = None

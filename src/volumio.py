import json
import logging
import time
import socket
from typing import Optional, Dict, Any
from websocket import create_connection, WebSocketException

logger = logging.getLogger(__name__)

class VolumioClient:
    def __init__(self, url: str) -> None:
        self.url = url
        self.ws = None

    def connect(self) -> bool:
        """Connects to Volumio's WebSocket."""
        try:
            self.ws = create_connection(self.url, timeout=10)
            self.ws.send('42["getState"]')
            return True
        except (socket.timeout, socket.error) as e:
            logger.error(f"Network error connecting to Volumio at {self.url}: {e}")
            return False
        except WebSocketException as e:
            logger.error(f"WebSocket error connecting to Volumio: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to Volumio at {self.url}: {e}")
            return False

    def get_state(self) -> None:
        """Requests the current state explicitly."""
        if self.ws:
            try:
                self.ws.send('42["getState"]')
            except (socket.error, WebSocketException) as e:
                logger.warning(f"Error requesting state from Volumio: {e}")
                self.ws = None
            except Exception as e:
                logger.error(f"Unexpected error in get_state: {e}")
                self.ws = None

    def receive_message(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Receives and processes WebSocket messages."""
        if not self.ws:
            return None

        try:
            self.ws.settimeout(timeout)
            result = self.ws.recv()
            
            # Socket.io heartbeat
            if result == '2':
                try:
                    self.ws.send('3')
                except (socket.error, WebSocketException):
                    logger.warning("Failed to send heartbeat response")
                    self.ws = None
                return None
                
            # Check if it's a state message (pushState or getState response)
            if '"pushState"' in result:
                start = result.find('{')
                end = result.rfind('}')
                if start != -1 and end != -1:
                    json_str = result[start:end+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse state JSON: {e}")
                        return None
        except socket.timeout:
            # Timeouts are expected if Volumio doesn't send anything
            pass
        except (socket.error, WebSocketException) as e:
            logger.warning(f"WebSocket connection error: {e}")
            self.ws = None
        except Exception as e:
            logger.error(f"Unexpected error in receive_message: {e}")
            self.ws = None
        return None

    def is_connected(self) -> bool:
        """Checks if the connection is active."""
        return self.ws is not None

    def close(self) -> None:
        """Closes the connection."""
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
            finally:
                self.ws = None

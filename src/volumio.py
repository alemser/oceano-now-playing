import json
import logging
import time
from websocket import create_connection

logger = logging.getLogger(__name__)

class VolumioClient:
    def __init__(self, url):
        self.url = url
        self.ws = None

    def connect(self):
        """Conecta ao WebSocket do Volumio."""
        try:
            self.ws = create_connection(self.url, timeout=10)
            self.ws.send('42["getState"]')
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar ao Volumio em {self.url}: {e}")
            return False

    def get_state(self):
        """Solicita o estado atual explicitamente."""
        if self.ws:
            try:
                self.ws.send('42["getState"]')
            except Exception as e:
                logger.error(f"Erro ao solicitar estado do Volumio: {e}")
                self.ws = None

    def receive_message(self, timeout=1.0):
        """Recebe e processa mensagens do WebSocket."""
        if not self.ws:
            return None

        try:
            self.ws.settimeout(timeout)
            result = self.ws.recv()
            
            # Heartbeat do socket.io
            if result == '2':
                self.ws.send('3')
                return None
                
            # Verifica se é uma mensagem de estado (pushState ou resposta de getState)
            if '"pushState"' in result:
                start = result.find('{')
                end = result.rfind('}')
                if start != -1 and end != -1:
                    json_str = result[start:end+1]
                    return json.loads(json_str)
        except (TimeoutError, Exception):
            # Timeouts são esperados se Volumio não enviar nada
            pass
        return None

    def is_connected(self):
        """Verifica se a conexão está ativa."""
        return self.ws is not None

    def close(self):
        """Fecha a conexão."""
        if self.ws:
            self.ws.close()
            self.ws = None

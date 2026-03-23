# ADR 0001: WebSocket Mocking Strategy for Tests

## Status
✅ **Accepted** (Implemented, 12 tests passing)

## Context
We need to test the Volumio WebSocket client (`media_players/volumio.py`) without requiring:
1. A running Volumio server (localhost:3000)
2. Network access
3. Complex test setup

However, `media_players/volumio.py` imports `websocket` at module load time:
```python
from websocket import create_connection  # This happens immediately!
```

This means we can't use simple pytest mocking—we need to inject the mock **before** the module imports.

## Decision
Use `monkeypatch.setitem(sys.modules, 'websocket', MockWebSocket)` to inject a mock WebSocket module at the pytest fixture level, then delete and reimport `media_players/volumio.py` per test for isolation.

## Implementation

### MockWebSocket Class (conftest.py)
```python
class MockWebSocket:
    """Simulates websocket.WebSocket for testing."""
    
    def __init__(self):
        self.sent_messages = []
        self._message_queue = []
        self._should_timeout = False
    
    def send(self, message):
        """Capture sent messages."""
        self.sent_messages.append(message)
    
    def recv(self):
        """Return queued messages."""
        if self._should_timeout:
            raise TimeoutError("Socket timeout")
        if self._message_queue:
            return self._message_queue.pop(0)
        raise TimeoutError("No messages")
    
    def settimeout(self, timeout):
        """Store timeout value (required by websocket API)."""
        self.timeout_value = timeout
    
    def close(self):
        """Mock close."""
        pass
    
    # Test helpers
    def queue_message(self, message):
        self._message_queue.append(message)
    
    def trigger_timeout(self):
        self._should_timeout = True
```

### Fixture (conftest.py)
```python
@pytest.fixture
def mock_volumio_client(mock_websocket, monkeypatch):
    """Provide a VolumioClient with mocked WebSocket."""
    import importlib
    
    # Create mock websocket module
    mock_ws_module = MagicMock()
    mock_ws_module.create_connection = MagicMock(return_value=mock_websocket)
    mock_ws_module.WebSocketException = Exception
    
    # Inject BEFORE any import
    monkeypatch.setitem(sys.modules, 'websocket', mock_ws_module)
    
    # Remove volumio from cache to force reimport with mocked websocket
    if 'volumio' in sys.modules:
        del sys.modules['volumio']
    
    # Now import VolumioClient—it will use our mock
    from media_players.volumio import VolumioClient
    
    client = VolumioClient('ws://localhost:3000/socket.io/?EIO=3&transport=websocket')
    client.connect()
    return client, mock_websocket
```

### Test Example
```python
def test_volumio_receive_playing_state(mock_volumio_client, volumio_websocket_message_playing):
    """Test receiving and parsing a playing state message."""
    client, mock_ws = mock_volumio_client
    
    # Queue a message
    mock_ws.queue_message(volumio_websocket_message_playing)
    
    # Receive it
    state = client.receive_message(timeout=0.1)
    
    # Verify parsing
    assert state is not None
    assert state['title'] == 'Test Song'
    assert state['status'] == 'play'
```

## Alternatives Considered

### 1. Simple pytest-mock (Mock after import)
```python
from unittest.mock import patch

@patch('websocket.create_connection')
def test_volumio(mock_create):
    from media_players.volumio import VolumioClient  # Already imported!
    # Problem: volumio already cached the real websocket
```

**Why rejected**: Python caches imports—`media_players/volumio.py` would already have imported the real `websocket` module.

### 2. Containerize Volumio (Real server in tests)
```yaml
# docker-compose.test.yml
services:
  volumio:
    image: volumio/volumio:latest
    ports:
      - "3000:3000"
```

**Why rejected**: 
- Slow (container startup ~5s)
- Fragile (network dependent)
- CI/CD complexity
- Overkill for unit tests

### 3. Async/Await with aiohttp
```python
import asyncio
from aiohttp import ClientSession

async def receive_message():
    async with ws.receive() as msg:
        return msg
```

**Why rejected**:
- Current `websocket-client` library is synchronous
- Would require major refactor
- Not necessary for our use case

## Pros & Cons

### Advantages ✅
1. **Tests run instantly** (no network, no server startup)
2. **Tests are deterministic** (no flaky network issues)
3. **Can test error scenarios** (timeouts, malformed JSON)
4. **Works with pytest** (simple fixture-based approach)
5. **Isolation per test** (deleting from sys.modules ensures no cross-contamination)

### Limitations ❌
1. **Doesn't catch real Socket.io protocol bugs** (edge cases with real server)
2. **Requires sys.modules manipulation** (slightly fragile)
3. **Performance: Slower than direct function mocks** (module import/delete per test)
4. **Limited to testing parsed state** (doesn't validate raw Socket.io frames)

## Trade-offs Made

| Aspect | Choice | Reason |
|--------|--------|--------|
| **Real vs Mock Server** | Mock | Tests must be fast and deterministic |
| **Module Injection Timing** | Before import | Only way to intercept module-level imports |
| **Cache Management** | Delete from sys.modules | Ensures test isolation |
| **Protocol Validation** | Skipped | Covered by integration tests (manual) |

## Implementation Status

- ✅ MockWebSocket class working
- ✅ 12 WebSocket tests passing
- ✅ Fixtures isolated per test
- ✅ All edge cases covered (timeouts, malformed JSON, None values)
- ✅ Pre-push hook validates before push to GitHub

## Future Considerations

1. **Integration Tests**: Could add optional `pytest -m integration` flag to run against real Volumio
2. **Snapshot Testing**: Could capture real Socket.io messages and replay them
3. **Mock Refinement**: Could add more realistic Socket.io frame formatting
4. **CI/CD**: Could containerize Volumio for nightly CI runs

## References

- [pytest monkeypatch documentation](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
- [Python sys.modules documentation](https://docs.python.org/3/library/sys.html#sys.modules)
- [websocket-client library](https://pypi.org/project/websocket-client/)
- [Socket.io protocol specification](https://socket.io/docs/v4/socket-io-protocol/)

## Decision Log

| Date | Event |
|------|-------|
| 2026-03-22 | Initial implementation with 12 tests |
| 2026-03-22 | Fixed monkeypatch timing (must delete volumio from sys.modules) |
| 2026-03-22 | All 55 tests passing (including 12 WebSocket tests) |
| 2026-03-22 | ADR documented |

---

**Author**: alemser  
**Last Updated**: March 2026  
**Affected Components**: tests/conftest.py, tests/test_volumio.py

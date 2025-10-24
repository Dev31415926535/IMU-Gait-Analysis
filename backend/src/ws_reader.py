# src/ws_reader.py
import json
import time
from websocket import create_connection, WebSocketConnectionClosedException

class IMUWebSocketReader:
    def __init__(self, esp_ip, port=81, timeout=5):
        self.esp_ip = esp_ip
        self.port = port
        self.url = f"ws://{esp_ip}:{port}"
        self.ws = None
        self.timeout = timeout

    def connect(self):
        try:
            self.ws = create_connection(self.url, timeout=self.timeout)
            print(f"✅ Connected to {self.url}")
            return True
        except Exception as e:
            print(f"❌ WebSocket connect error: {e}")
            return False

    def read_packet(self):
        if self.ws is None:
            return None
        try:
            raw = self.ws.recv()
            return json.loads(raw)
        except WebSocketConnectionClosedException:
            print("❌ Connection closed by remote.")
            self.ws = None
            return None
        except Exception as e:
            # sometimes ESP prints other messages; ignore non-json lines
            print(f"⚠ read error: {e}")
            return None

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
            print("🔌 WebSocket closed")
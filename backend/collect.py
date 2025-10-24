import websocket
import json

ESP_IP = "10.62.139.36"

ws = websocket.WebSocket()
ws.connect(f"ws://{ESP_IP}:81")
print("✅ Connected to ESP32 WebSocket\n")

while True:
    data = ws.recv()
    imu_data = json.loads(data)
    print(json.dumps(imu_data, indent=2))

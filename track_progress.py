import websocket
import uuid
import json
import sys

# Your ComfyUI server address
server_address = "127.0.0.1:8188"
client_id = str(uuid.uuid4())

def on_message(ws, message):
    # ComfyUI sends binary data for image previews; we only care about text (JSON)
    if isinstance(message, str):
        try:
            msg = json.loads(message)
            msg_type = msg.get('type')
            data = msg.get('data', {})

            if msg_type == 'progress':
                current = data.get('value', 0)
                total = data.get('max', 1)
                
                # Calculate percentage and create a visual progress bar
                percent = (current / total) * 100
                bar_length = 40
                filled = int((current / total) * bar_length)
                bar = '█' * filled + '-' * (bar_length - filled)
                
                # \r overwrites the current line for a clean UI
                sys.stdout.write(f"\r🚀 Progress: [{bar}] {percent:.0f}% ({current}/{total})")
                sys.stdout.flush()

            elif msg_type == 'execution_start':
                print("\n\n⚡ Generation Started!")

            elif msg_type == 'execution_cached':
                print("\n⏭️  Generation Skipped: Result was already cached (change your KSampler seed!).")

            elif msg_type == 'executing':
                node = data.get('node')
                if node is None:
                    print("\n\n✅ Generation Complete!")
                # To see every node as it fires, uncomment the lines below:
                # else:
                #     print(f"\n⚙️  Processing Node: {node}")

        except json.JSONDecodeError:
            pass

def on_error(ws, error):
    print(f"\n❌ WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("\n🔌 Disconnected from ComfyUI.")

def on_open(ws):
    print(f"📡 Connected to ComfyUI ({server_address}) | Client ID: {client_id}")
    print("⏳ Waiting for generation to start... (Queue a prompt in UI or via API)")

if __name__ == "__main__":
    ws_url = f"ws://{server_address}/ws?clientId={client_id}"
    
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    try:
        ws.run_forever()
    except KeyboardInterrupt:
        print("\n🛑 Tracking stopped by user.")
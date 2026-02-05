# Relay Server (Push-based Streaming)

No port forwarding required! Cameras push frames to this server.

## Installation

```bash
pip install flask flask-cors
```

## Run

```bash
python relay_server.py
```

Server will run on port 5000 and accept:
- Frame pushes at `/camera/push_frame/{camera_num}`
- Alarm triggers at `/camera/trigger_alarm/{camera_num}`
- Website requests at `/video_feed/{camera_num}`

See `../docs/PUSH_STREAMING_SETUP.md` for complete documentation.

# Cross-Network Camera System Setup Guide

## Architecture Overview

```
Network A (Camera)           Internet (Relay)          Network B (Website)
┌─────────────────┐          ┌─────────────────┐       ┌─────────────────┐
│  Raspberry Pi   │          │  Cloud Relay    │       │   Your Computer │
│   Camera 1      │◄────────►│     Server      │◄─────►│    (Website)    │
│                 │          │  Public IP      │       │                 │
│  Streams video  │   HTTP   │                 │ HTTP  │ Views cameras   │
│  Sends alarms   │          │  Forwards data  │       │ Sees alarms     │
└─────────────────┘          └─────────────────┘       └─────────────────┘
```

The relay server acts as a bridge between your cameras and website when they're on different networks.

## Components

1. **Relay Server** (`relay_server.py`) - Hosted on cloud with public IP
2. **Camera Script** (`integrated_camera1.py`) - Runs on each Raspberry Pi
3. **Website** (`camera_website.html` + `server.py`) - Your monitoring interface

## Step 1: Deploy Relay Server

### Cloud Hosting Options
- AWS EC2 (Free tier available)
- DigitalOcean Droplet ($4/month)
- Google Cloud Compute Engine
- Azure VM
- Heroku

### Deploy Steps

1. **Create a cloud instance** with Ubuntu/Debian

2. **Install dependencies:**
```bash
sudo apt update
sudo apt install python3-pip
pip3 install flask flask-cors requests
```

3. **Upload relay_server.py:**
```bash
scp relay_server.py user@YOUR_SERVER_IP:/home/user/
```

4. **Run the relay server:**
```bash
python3 relay_server.py
```

5. **Make it run on boot (systemd service):**
```bash
sudo nano /etc/systemd/system/relay-server.service
```

Add:
```ini
[Unit]
Description=Camera Relay Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/user/relay_server.py
WorkingDirectory=/home/user
StandardOutput=inherit
StandardError=inherit
Restart=always
User=user

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable relay-server.service
sudo systemctl start relay-server.service
sudo systemctl status relay-server.service
```

6. **Open firewall port 5000:**
```bash
# For UFW (Ubuntu)
sudo ufw allow 5000

# For cloud providers, also open port 5000 in security group/firewall rules
```

7. **Test the relay:**
```bash
curl http://YOUR_RELAY_IP:5000/status
```

## Step 2: Configure Camera (Raspberry Pi)

### On Each Raspberry Pi:

1. **Install dependencies:**
```bash
sudo apt update
sudo apt install -y python3-pip python3-picamera2 python3-opencv
pip3 install flask requests RPi.GPIO --break-system-packages
```

2. **Edit integrated_camera1.py:**
```python
CAMERA_NUMBER = 1  # Change for each camera (1-4)
RELAY_SERVER_URL = "http://YOUR_RELAY_PUBLIC_IP:5000"  # Your relay server
MY_PUBLIC_URL = "http://YOUR_PI_PUBLIC_IP:5001"  # If you have public IP
# OR
MY_PUBLIC_URL = "http://YOUR_RELAY_IP:5001"  # If using port forwarding
```

3. **Options for video streaming:**

**Option A: Port forwarding (simplest)**
- Forward port 5001 on your router to your Pi
- Use your public IP in MY_PUBLIC_URL
- Cameras stream directly to website (faster, no relay bottleneck)

**Option B: Relay proxy (no port forwarding needed)**
- Leave MY_PUBLIC_URL as local IP
- Video streams through relay server
- Slightly slower but works without port forwarding

4. **Run the camera script:**
```bash
python3 integrated_camera1.py
```

5. **Set up as service (auto-start):**
```bash
sudo nano /etc/systemd/system/camera1.service
```

```ini
[Unit]
Description=Integrated Camera 1
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/integrated_camera1.py
WorkingDirectory=/home/pi
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable camera1.service
sudo systemctl start camera1.service
```

## Step 3: Configure Website

### On Your Computer (Network B):

1. **Edit camera_website.html:**
```javascript
const RELAY_SERVER_URL = 'http://YOUR_RELAY_PUBLIC_IP:5000';
```

2. **NO LONGER NEED server.py** - The website now connects directly to the relay server!

3. **Open camera_website.html in browser:**
- Just open the HTML file directly, OR
- Use Python simple server:
```bash
python3 -m http.server 8000
# Visit http://localhost:8000/camera_website.html
```

## Network Configuration Summary

### What needs a public IP?
- ✅ **Relay Server** - MUST have public IP (cloud server)
- ❓ **Cameras** - Optional (for direct streaming, otherwise relay proxies)
- ❌ **Website** - NO (runs locally on your computer)

### Ports to open:
- **Relay Server**: Port 5000 (incoming from cameras and website)
- **Cameras** (if using direct streaming): Port 5001 (incoming from website)

## Testing the System

### 1. Test Relay Server
```bash
curl http://RELAY_IP:5000/status
```

Should return JSON with camera status.

### 2. Test Camera Connection
On Raspberry Pi:
```bash
# Check logs
sudo journalctl -u camera1.service -f

# Should see:
# ✓ Registered with relay server
# Sending heartbeat every 15 seconds
```

### 3. Test Website
Open `camera_website.html` in browser. You should see:
- Video feeds loading (or red indicators if offline)
- Console logs showing "Camera X stream loaded successfully"

### 4. Test Alarm System
Trigger a detection by walking in front of camera. You should see:
- Camera console: "🚨 Person detected"
- Relay console: "🚨 Alarm triggered for Camera X"
- Website: Camera name flashes red, alarm sound plays

## Troubleshooting

### Cameras not connecting to relay
```bash
# On Pi, test connection
curl -X POST http://RELAY_IP:5000/camera/heartbeat/1

# Check Pi can reach relay
ping RELAY_IP
```

### Website not receiving alarms
```bash
# In browser console (F12)
# Check for CORS errors
# Check RELAY_SERVER_URL is correct
```

### Video not streaming
```bash
# Check if camera is streaming locally
curl http://LOCALHOST:5001/video_feed

# Check if registered with relay
curl http://RELAY_IP:5000/api/camera_streams

# Check relay proxy
curl http://RELAY_IP:5000/video_feed/1
```

### Relay server errors
```bash
# Check relay logs
sudo journalctl -u relay-server.service -f

# Check if port is open
sudo netstat -tulpn | grep 5000

# Test from outside
curl http://RELAY_PUBLIC_IP:5000/status
```

## Cost Estimate

- **Relay Server**: $4-5/month (DigitalOcean) or free (AWS free tier first year)
- **Cameras**: No additional cost (just Raspberry Pi power)
- **Website**: Free (runs locally)

Total: $0-5/month

## Security Considerations

### Basic Security (Minimum):
1. Change relay server port from 5000 to something else
2. Use HTTPS if possible (Let's Encrypt)
3. Keep software updated

### Advanced Security:
1. Add API authentication tokens
2. Use VPN instead of public relay
3. Encrypt video streams
4. Rate limiting on relay server

## Alternative: Using Ngrok (Quick Test)

For testing without deploying a relay:

1. **On Relay Server:**
```bash
pip install pyngrok
ngrok http 5000
```

2. **Use the ngrok URL:**
```
https://abc123.ngrok.io
```

This gives you a temporary public URL, but it's not permanent (resets when ngrok restarts).

## Summary

1. Deploy `relay_server.py` on cloud with public IP
2. Configure each Pi to send alarms to relay
3. Update website to poll relay for commands
4. All communication goes through relay
5. Cameras and website never need to directly connect!

#!/usr/bin/env python3
"""
Cloud Relay Server - Bridges cameras and website across different networks

This server should be hosted on a cloud service (AWS, DigitalOcean, etc.)
with a public IP that both the Raspberry Pi and the website can access.

Architecture:
- Cameras POST alarm triggers to this relay
- Cameras stream video through this relay (or direct if using public URL)
- Website polls this relay for alarm status
- Website fetches video streams from this relay (or direct from cameras)
"""

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
import requests
import time
from collections import defaultdict
import threading

app = Flask(__name__)
CORS(app)

# Store alarm states for each camera
alarm_states = {
    1: {'active': False, 'last_update': 0},
    2: {'active': False, 'last_update': 0},
    3: {'active': False, 'last_update': 0},
    4: {'active': False, 'last_update': 0}
}

# Store video stream URLs for each camera (cameras register themselves)
camera_streams = {
    1: None,
    2: None,
    3: None,
    4: None
}

# Latest command for polling
latest_command = None
command_lock = threading.Lock()

# =============================================================================
# CAMERA ENDPOINTS (Cameras call these)
# =============================================================================

@app.route('/camera/register/<int:camera_num>', methods=['POST'])
def register_camera(camera_num):
    """Cameras register their stream URL"""
    if 1 <= camera_num <= 4:
        data = request.get_json()
        camera_streams[camera_num] = data.get('stream_url')
        print(f"Camera {camera_num} registered: {camera_streams[camera_num]}")
        return jsonify({'status': 'success', 'camera': camera_num}), 200
    return jsonify({'status': 'error', 'message': 'Invalid camera number'}), 400


@app.route('/camera/trigger_alarm/<int:camera_num>', methods=['POST'])
def camera_trigger_alarm(camera_num):
    """Cameras call this to trigger their alarm"""
    global latest_command
    if 1 <= camera_num <= 4:
        alarm_states[camera_num]['active'] = True
        alarm_states[camera_num]['last_update'] = time.time()
        
        with command_lock:
            latest_command = f'trigger_alarm_{camera_num}'
        
        print(f"🚨 Alarm triggered for Camera {camera_num}")
        return jsonify({'status': 'success', 'command': latest_command}), 200
    return jsonify({'status': 'error', 'message': 'Invalid camera number'}), 400


@app.route('/camera/clear_alarm/<int:camera_num>', methods=['POST'])
def camera_clear_alarm(camera_num):
    """Cameras call this to clear their alarm"""
    global latest_command
    if 1 <= camera_num <= 4:
        alarm_states[camera_num]['active'] = False
        alarm_states[camera_num]['last_update'] = time.time()
        
        with command_lock:
            latest_command = f'clear_alarm_{camera_num}'
        
        print(f"✓ Alarm cleared for Camera {camera_num}")
        return jsonify({'status': 'success', 'command': latest_command}), 200
    return jsonify({'status': 'error', 'message': 'Invalid camera number'}), 400


@app.route('/camera/heartbeat/<int:camera_num>', methods=['POST'])
def camera_heartbeat(camera_num):
    """Cameras send heartbeat to show they're online"""
    if 1 <= camera_num <= 4:
        alarm_states[camera_num]['last_update'] = time.time()
        return jsonify({'status': 'success'}), 200
    return jsonify({'status': 'error'}), 400


# =============================================================================
# WEBSITE ENDPOINTS (Website calls these)
# =============================================================================

@app.route('/api/commands', methods=['GET'])
def get_commands():
    """Website polls for new commands"""
    global latest_command
    with command_lock:
        command = latest_command
        latest_command = None  # Clear after reading
    return jsonify({'command': command}), 200


@app.route('/api/alarm_status', methods=['GET'])
def get_alarm_status():
    """Get current alarm status for all cameras"""
    return jsonify({'alarms': alarm_states}), 200


@app.route('/api/camera_streams', methods=['GET'])
def get_camera_streams():
    """Get registered camera stream URLs"""
    return jsonify({'streams': camera_streams}), 200


@app.route('/api/trigger_alarm_<int:camera_num>', methods=['POST'])
def api_trigger_alarm(camera_num):
    """Manual alarm trigger from website (optional)"""
    global latest_command
    if 1 <= camera_num <= 4:
        alarm_states[camera_num]['active'] = True
        alarm_states[camera_num]['last_update'] = time.time()
        
        with command_lock:
            latest_command = f'trigger_alarm_{camera_num}'
        
        return jsonify({'status': 'success', 'command': latest_command}), 200
    return jsonify({'status': 'error', 'message': 'Invalid camera number'}), 400


@app.route('/api/clear_alarm_<int:camera_num>', methods=['POST'])
def api_clear_alarm(camera_num):
    """Manual alarm clear from website (optional)"""
    global latest_command
    if 1 <= camera_num <= 4:
        alarm_states[camera_num]['active'] = False
        alarm_states[camera_num]['last_update'] = time.time()
        
        with command_lock:
            latest_command = f'clear_alarm_{camera_num}'
        
        return jsonify({'status': 'success', 'command': latest_command}), 200
    return jsonify({'status': 'error', 'message': 'Invalid camera number'}), 400


@app.route('/api/clear_all_alarms', methods=['POST'])
def api_clear_all_alarms():
    """Clear all alarms"""
    global latest_command
    for camera_num in alarm_states:
        alarm_states[camera_num]['active'] = False
        alarm_states[camera_num]['last_update'] = time.time()
    
    with command_lock:
        latest_command = 'clear_all_alarms'
    
    return jsonify({'status': 'success', 'command': latest_command}), 200


# =============================================================================
# VIDEO PROXY ENDPOINTS (Optional - if cameras can't expose public URLs)
# =============================================================================

@app.route('/video_feed/<int:camera_num>')
def video_feed(camera_num):
    """Proxy video feed from camera to website"""
    if 1 <= camera_num <= 4 and camera_streams[camera_num]:
        try:
            # Stream video from camera
            def generate():
                response = requests.get(camera_streams[camera_num], stream=True, timeout=10)
                for chunk in response.iter_content(chunk_size=1024):
                    yield chunk
            
            return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
        except Exception as e:
            print(f"Error proxying video from camera {camera_num}: {e}")
            return jsonify({'error': 'Camera not available'}), 503
    
    return jsonify({'error': 'Invalid camera or not registered'}), 404


# =============================================================================
# STATUS AND MONITORING
# =============================================================================

@app.route('/status')
def status():
    """Overall system status"""
    current_time = time.time()
    camera_status = {}
    
    for cam_num in alarm_states:
        last_seen = current_time - alarm_states[cam_num]['last_update']
        camera_status[cam_num] = {
            'online': last_seen < 30,  # Online if seen in last 30 seconds
            'alarm_active': alarm_states[cam_num]['active'],
            'last_seen_seconds_ago': round(last_seen, 1),
            'stream_registered': camera_streams[cam_num] is not None
        }
    
    return jsonify({
        'status': 'running',
        'cameras': camera_status,
        'timestamp': current_time
    }), 200


@app.route('/')
def index():
    """API documentation"""
    return """
    <h1>Camera Relay Server</h1>
    <h2>Camera Endpoints:</h2>
    <ul>
        <li>POST /camera/register/&lt;camera_num&gt; - Register camera stream</li>
        <li>POST /camera/trigger_alarm/&lt;camera_num&gt; - Trigger alarm</li>
        <li>POST /camera/clear_alarm/&lt;camera_num&gt; - Clear alarm</li>
        <li>POST /camera/heartbeat/&lt;camera_num&gt; - Send heartbeat</li>
    </ul>
    <h2>Website Endpoints:</h2>
    <ul>
        <li>GET /api/commands - Poll for commands</li>
        <li>GET /api/alarm_status - Get all alarm states</li>
        <li>GET /api/camera_streams - Get camera stream URLs</li>
        <li>GET /video_feed/&lt;camera_num&gt; - Proxy video stream</li>
        <li>GET /status - System status</li>
    </ul>
    """


# =============================================================================
# CLEANUP TASK
# =============================================================================

def cleanup_task():
    """Periodically cleanup old camera states"""
    while True:
        time.sleep(60)  # Run every minute
        current_time = time.time()
        
        for cam_num in alarm_states:
            # Auto-clear alarms if camera hasn't been seen in 60 seconds
            last_seen = current_time - alarm_states[cam_num]['last_update']
            if last_seen > 60 and alarm_states[cam_num]['active']:
                print(f"Auto-clearing alarm for Camera {cam_num} (not seen for {last_seen:.0f}s)")
                alarm_states[cam_num]['active'] = False


if __name__ == '__main__':
    # Start cleanup task in background
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()
    
    print("\n" + "="*60)
    print("Camera Relay Server Starting")
    print("="*60)
    print("This server bridges cameras and website across networks")
    print("Deploy this on a cloud service with a public IP")
    print("="*60 + "\n")
    
    # Run on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

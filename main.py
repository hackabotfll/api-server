#!/usr/bin/env python3
"""
Cloud Relay Server - Push-based video streaming for cameras behind NAT

Architecture:
- Cameras PUSH video frames to this relay via HTTP POST
- Cameras POST alarm triggers to this relay
- Website polls this relay for alarm status
- Website fetches video streams from this relay's buffer
"""

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
import time
from collections import deque
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

# Store latest video frames for each camera (in-memory buffer)
# Using deque with maxlen=1 to only keep the most recent frame
camera_frames = {
    1: {'frame': None, 'last_update': 0, 'lock': threading.Lock()},
    2: {'frame': None, 'last_update': 0, 'lock': threading.Lock()},
    3: {'frame': None, 'last_update': 0, 'lock': threading.Lock()},
    4: {'frame': None, 'last_update': 0, 'lock': threading.Lock()}
}

# Latest command for polling
latest_command = None
command_lock = threading.Lock()

# =============================================================================
# CAMERA ENDPOINTS (Cameras call these)
# =============================================================================

@app.route('/camera/push_frame/<int:camera_num>', methods=['POST'])
def push_frame(camera_num):
    """Cameras push video frames here"""
    if 1 <= camera_num <= 4:
        try:
            # Get the frame data from the request
            frame_data = request.data
            
            if frame_data:
                camera_data = camera_frames[camera_num]
                with camera_data['lock']:
                    camera_data['frame'] = frame_data
                    camera_data['last_update'] = time.time()
                
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'status': 'error', 'message': 'No frame data'}), 400
        except Exception as e:
            print(f"Error receiving frame from camera {camera_num}: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
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
# VIDEO STREAMING ENDPOINTS
# =============================================================================

@app.route('/video_feed/<int:camera_num>')
def video_feed(camera_num):
    """Stream the latest frames from camera buffer (MJPEG)"""
    if 1 <= camera_num <= 4:
        def generate():
            camera_data = camera_frames[camera_num]
            last_frame = None
            
            while True:
                with camera_data['lock']:
                    current_frame = camera_data['frame']
                    last_update = camera_data['last_update']
                
                # Check if we have a new frame
                if current_frame and current_frame != last_frame:
                    last_frame = current_frame
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + current_frame + b'\r\n')
                else:
                    # No new frame, check if camera is still alive
                    if time.time() - last_update > 5:
                        # Camera hasn't sent frames in 5 seconds
                        # Could send a placeholder or just wait
                        pass
                
                # Small delay to prevent busy waiting
                time.sleep(0.033)  # ~30 FPS
        
        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    
    return jsonify({'error': 'Invalid camera number'}), 404


# =============================================================================
# STATUS AND MONITORING
# =============================================================================

@app.route('/status')
def status():
    """Overall system status"""
    current_time = time.time()
    camera_status = {}
    
    for cam_num in alarm_states:
        # Check both alarm state and frame updates
        alarm_last_seen = current_time - alarm_states[cam_num]['last_update']
        frame_last_seen = current_time - camera_frames[cam_num]['last_update']
        
        # Camera is online if we've seen either an alarm update or frame recently
        last_seen = min(alarm_last_seen, frame_last_seen)
        
        camera_status[cam_num] = {
            'online': last_seen < 30,  # Online if seen in last 30 seconds
            'alarm_active': alarm_states[cam_num]['active'],
            'last_seen_seconds_ago': round(last_seen, 1),
            'has_frames': camera_frames[cam_num]['frame'] is not None
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
    <h1>Camera Relay Server (Push-based Streaming)</h1>
    <h2>Camera Endpoints:</h2>
    <ul>
        <li>POST /camera/push_frame/&lt;camera_num&gt; - Push video frame</li>
        <li>POST /camera/trigger_alarm/&lt;camera_num&gt; - Trigger alarm</li>
        <li>POST /camera/clear_alarm/&lt;camera_num&gt; - Clear alarm</li>
        <li>POST /camera/heartbeat/&lt;camera_num&gt; - Send heartbeat</li>
    </ul>
    <h2>Website Endpoints:</h2>
    <ul>
        <li>GET /api/commands - Poll for commands</li>
        <li>GET /api/alarm_status - Get all alarm states</li>
        <li>GET /video_feed/&lt;camera_num&gt; - Stream video (MJPEG)</li>
        <li>GET /status - System status</li>
    </ul>
    <h3>Note:</h3>
    <p>This server uses push-based streaming. Cameras behind NAT/firewalls 
    can push frames via HTTP POST without port forwarding.</p>
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
            alarm_last_seen = current_time - alarm_states[cam_num]['last_update']
            frame_last_seen = current_time - camera_frames[cam_num]['last_update']
            last_seen = min(alarm_last_seen, frame_last_seen)
            
            if last_seen > 60 and alarm_states[cam_num]['active']:
                print(f"Auto-clearing alarm for Camera {cam_num} (not seen for {last_seen:.0f}s)")
                alarm_states[cam_num]['active'] = False


if __name__ == '__main__':
    # Start cleanup task in background
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()
    
    print("\n" + "="*60)
    print("Camera Relay Server Starting (Push-based Streaming)")
    print("="*60)
    print("Cameras behind NAT/firewall push frames to this server")
    print("No port forwarding required on camera networks")
    print("="*60 + "\n")
    
    # Run on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

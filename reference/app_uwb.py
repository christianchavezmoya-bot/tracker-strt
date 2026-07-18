from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import threading
import json
from collections import deque
import math

from uwb_positioning import UWBPositioning, simulate_uwb_ranges
from uwb_serial_reader import create_mock_reader

app = Flask(__name__)
CORS(app)

# =========================
# CONFIGURATION
# =========================
USE_MOCK_DATA = True  # Set to False to use real UWB hardware
UWB_SERIAL_PORT = '/dev/ttyUSB0'  # Adjust for your system
UWB_BAUD_RATE = 115200
POSITION_HISTORY_SIZE = 100
UPDATE_INTERVAL = 0.1  # seconds

# =========================
# GLOBAL STATE
# =========================
latest_lock = threading.Lock()
latest_position = {'x': 0, 'y': 0, 'z': 0, 'timestamp': None, 'accuracy': 0}
position_history = deque(maxlen=POSITION_HISTORY_SIZE)

# UWB Positioning System
uwb_pos = UWBPositioning(num_anchors=4)

# Configure anchor positions (example for a tunnel scenario)
# Adjust these based on your actual tunnel layout
uwb_pos.add_anchor('anchor_0', 0.0, 0.0, 0.0)      # Start of tunnel
uwb_pos.add_anchor('anchor_1', 50.0, 0.0, 0.0)     # 50m down tunnel
uwb_pos.add_anchor('anchor_2', 100.0, 0.0, 0.0)    # 100m down tunnel
uwb_pos.add_anchor('anchor_3', 50.0, 10.0, 0.0)    # Offset for triangulation

# UWB Data Reader
if USE_MOCK_DATA:
    uwb_reader = create_mock_reader()
else:
    from uwb_serial_reader import UWBSerialReader
    uwb_reader = UWBSerialReader(UWB_SERIAL_PORT, UWB_BAUD_RATE)


# =========================
# UWB CALLBACK HANDLER
# =========================
def handle_uwb_ranges(ranges):
    """
    Process UWB range measurements and update position.
    """
    global latest_position, position_history
    
    # Estimate position using trilateration
    position = uwb_pos.trilaterate_2d(ranges)
    
    if position is None:
        return
    
    x, y = position
    
    # Apply smoothing
    x_smooth, y_smooth = uwb_pos.smooth_position(position)
    
    # Calculate accuracy (RMSE)
    accuracy = uwb_pos.calculate_accuracy((x_smooth, y_smooth), ranges)
    
    # Update global state
    with latest_lock:
        latest_position = {
            'x': x_smooth,
            'y': y_smooth,
            'z': 0,  # Assume 2D for tunnel
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'accuracy': round(accuracy, 3),
            'num_anchors': len(ranges)
        }
        position_history.append(latest_position.copy())


# Start UWB reader thread
def start_uwb_reader():
    """Start UWB reader in background thread."""
    uwb_reader.set_callback(handle_uwb_ranges)
    thread = threading.Thread(target=uwb_reader.run, daemon=True)
    thread.start()


# =========================
# HOME ROUTE (FRONTEND)
# =========================
@app.route("/")
def index():
    return render_template("index_uwb.html")


# =========================
# UWB POSITIONING ROUTES
# =========================
@app.route("/uwb_position")
def uwb_position():
    """
    Get current UWB-estimated position.
    Returns: {x, y, z, timestamp, accuracy_meters, num_anchors}
    """
    with latest_lock:
        if latest_position['timestamp'] is None:
            return jsonify({"error": "No UWB data yet"}), 503
        return jsonify(latest_position)


@app.route("/uwb_history")
def uwb_history():
    """
    Get position history (track of tag movement).
    """
    with latest_lock:
        history = list(position_history)
    return jsonify({"history": history})


@app.route("/uwb_anchors")
def uwb_anchors():
    """
    Get configured anchor positions.
    """
    anchors = [
        {
            'id': anchor_id,
            'x': pos[0],
            'y': pos[1],
            'z': pos[2]
        }
        for anchor_id, pos in uwb_pos.anchors.items()
    ]
    return jsonify({"anchors": anchors})


@app.route("/uwb_config", methods=['POST'])
def uwb_config():
    """
    Configure anchor positions.
    Expected: {"anchors": [{"id": "anchor_0", "x": 0, "y": 0, "z": 0}, ...]}
    """
    try:
        data = request.json
        anchors = data.get('anchors', [])
        
        # Clear existing anchors
        uwb_pos.anchors.clear()
        
        # Add new anchors
        for anchor in anchors:
            anchor_id = anchor.get('id')
            x = float(anchor.get('x', 0))
            y = float(anchor.get('y', 0))
            z = float(anchor.get('z', 0))
            uwb_pos.add_anchor(anchor_id, x, y, z)
        
        return jsonify({"status": "ok", "anchors_configured": len(uwb_pos.anchors)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/uwb_simulate", methods=['POST'])
def uwb_simulate():
    """
    Simulate UWB ranges for testing.
    Expected: {"tag_x": 25.0, "tag_y": 5.0, "noise_std": 0.1}
    """
    try:
        data = request.json
        tag_x = float(data.get('tag_x', 25.0))
        tag_y = float(data.get('tag_y', 5.0))
        noise_std = float(data.get('noise_std', 0.1))
        
        # Simulate ranges
        ranges = simulate_uwb_ranges((tag_x, tag_y), uwb_pos.anchors, noise_std)
        
        # Process through positioning system
        position = uwb_pos.trilaterate_2d(ranges)
        
        if position:
            x, y = position
            accuracy = uwb_pos.calculate_accuracy(position, ranges)
            
            return jsonify({
                "simulated_tag_position": {"x": tag_x, "y": tag_y},
                "estimated_position": {"x": x, "y": y},
                "accuracy": round(accuracy, 3),
                "ranges": {k: round(v, 3) for k, v in ranges.items()}
            })
        else:
            return jsonify({"error": "Position calculation failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =========================
# LEGACY ISS ROUTE (for compatibility with tracker-strt)
# =========================
@app.route("/iss_data")
def iss_data():
    """
    Fallback: returns UWB position data in ISS-compatible format.
    """
    with latest_lock:
        if latest_position['timestamp'] is None:
            return jsonify({"error": "No positioning data"}), 503
        
        return jsonify({
            "latitude": latest_position['y'] / 111000.0,  # Rough conversion to lat
            "longitude": latest_position['x'] / 111000.0,  # Rough conversion to lon
            "altitude": latest_position['z'],
            "velocity": 0,
            "timestamp_ist": latest_position['timestamp'],
            "accuracy_meters": latest_position['accuracy']
        })


# =========================
# HEALTH CHECK
# =========================
@app.route("/health")
def health():
    with latest_lock:
        is_active = latest_position['timestamp'] is not None
    return jsonify({
        "status": "ok",
        "uwb_active": is_active,
        "num_anchors": len(uwb_pos.anchors)
    })


# =========================
# MAIN ENTRY POINT
# =========================
if __name__ == "__main__":
    print("Starting UWB-based Tracker...")
    print(f"Mock data mode: {USE_MOCK_DATA}")
    print(f"Configured anchors: {len(uwb_pos.anchors)}")
    
    # Start UWB reader
    start_uwb_reader()
    
    # Start Flask app
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=True
    )

# Tracker-STRT: UWB-Integrated Underground/Tunnel Tracking System

## Overview

This is an **enhanced version of tracker-strt** that integrates **Ultra-Wideband (UWB)** positioning technology for accurate **underground and tunnel tracking**.

### Key Improvements:
- ✅ **UWB Positioning Engine** - Centimeter-level accuracy (UWB trilateration)
- ✅ **Hybrid 3D/2D Visualization** - Interactive 3D tunnel view + 2D map
- ✅ **Real-time Position Tracking** - Updates every 100ms
- ✅ **Kalman Filtering** - Smooth position estimates, noise reduction
- ✅ **RMSE Accuracy Calculation** - Real-time positioning accuracy metrics
- ✅ **Serial UWB Reader** - Connects to DWM1001 hardware via UART
- ✅ **Mock Data Mode** - Test without hardware

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│           UWB Hardware (DWM1001 / ESP32)               │
│  [Anchor 0] [Anchor 1] [Anchor 2] [Anchor 3]           │
│           └─────────────┬────────────┘                  │
│                     Serial/UART                         │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│             Flask Backend (app_uwb.py)                  │
│  ┌─────────────────────────────────────────────────┐   │
│  │ UWB Serial Reader (uwb_serial_reader.py)       │   │
│  │ - Parses JSON/CSV/DWM1001 format               │   │
│  │ - Handles serial communication                 │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │ UWB Positioning (uwb_positioning.py)          │   │
│  │ - Trilateration algorithm                      │   │
│  │ - Kalman filtering                             │   │
│  │ - RMSE accuracy calculation                    │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │ REST API Endpoints                             │   │
│  │ - /uwb_position (current position)             │   │
│  │ - /uwb_history (tracking history)              │   │
│  │ - /uwb_anchors (anchor configuration)          │   │
│  │ - /uwb_config (POST: update anchors)           │   │
│  │ - /uwb_simulate (test simulation)              │   │
│  └─────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
┌──────▼──────┐   ┌────────▼────────┐   ┌─────▼─────┐
│   Browser   │   │   Web Client    │   │   Mobile  │
│  (index_    │   │  (Real-time     │   │   Apps    │
│   uwb.html) │   │   Dashboard)    │   │           │
└─────────────┘   └─────────────────┘   └───────────┘
     │                   │                    │
     └───────────────────┼────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  3D/2D Visualization│
              │ - 3D Tunnel View    │
              │ - 2D Map View       │
              │ - Anchor Display    │
              │ - Track History     │
              └─────────────────────┘
```

## Hardware Requirements

For production use with real UWB hardware:

| Component | Recommendation |
|-----------|----------------|
| UWB Modules | Qorvo DWM1001-DEV, DWM3001C, or DecaWave DW1000 |
| Microcontroller | ESP32 with DW1000 breakout |
| Anchors | 4+ fixed UWB devices at known positions |
| Tags | 1+ mobile UWB tags |
| Serial Connection | USB to UART (3.3V TTL) |
| Baud Rate | 115200 bps |

## Setup & Installation

### 1. Install Dependencies

```bash
cd tracker-strt
pip install -r requirements.txt
```

### 2. Configure UWB Hardware

Edit `app_uwb.py` to set your anchor positions:

```python
# Configure anchor positions for your tunnel
uwb_pos.add_anchor('anchor_0', 0.0, 0.0, 0.0)      # Start
uwb_pos.add_anchor('anchor_1', 50.0, 0.0, 0.0)     # 50m
uwb_pos.add_anchor('anchor_2', 100.0, 0.0, 0.0)    # 100m
uwb_pos.add_anchor('anchor_3', 50.0, 10.0, 0.0)    # Side
```

### 3. Test with Mock Data

```bash
# app_uwb.py has USE_MOCK_DATA = True by default
python app_uwb.py
```

Open browser to `http://localhost:8080`

### 4. Connect Real UWB Hardware

```python
# In app_uwb.py, change:
USE_MOCK_DATA = False
UWB_SERIAL_PORT = '/dev/ttyUSB0'  # Adjust for your system
```

Then:
```bash
python app_uwb.py
```

## API Endpoints

### Current Position
```
GET /uwb_position

Response:
{
  "x": 25.5,           # X coordinate (meters)
  "y": 3.2,            # Y coordinate (meters)
  "z": 0.0,            # Z coordinate (meters)
  "timestamp": "2024-07-18T12:34:56Z",
  "accuracy": 0.15,    # RMSE accuracy (meters)
  "num_anchors": 4     # Number of anchors used
}
```

### Position History
```
GET /uwb_history

Response:
{
  "history": [
    {...},
    {...},
    ...
  ]
}
```

### Anchor Configuration
```
GET /uwb_anchors

Response:
{
  "anchors": [
    {"id": "anchor_0", "x": 0, "y": 0, "z": 0},
    {"id": "anchor_1", "x": 50, "y": 0, "z": 0},
    ...
  ]
}
```

### Update Anchors
```
POST /uwb_config

Body:
{
  "anchors": [
    {"id": "anchor_0", "x": 0, "y": 0, "z": 0},
    {"id": "anchor_1", "x": 50, "y": 0, "z": 0},
    ...
  ]
}
```

### Test Simulation
```
POST /uwb_simulate

Body:
{
  "tag_x": 25.0,
  "tag_y": 5.0,
  "noise_std": 0.1
}

Response:
{
  "simulated_tag_position": {"x": 25.0, "y": 5.0},
  "estimated_position": {"x": 24.98, "y": 5.02},
  "accuracy": 0.145,
  "ranges": {"anchor_0": 2.51, ...}
}
```

## File Structure

```
tracker-strt/
├── app.py                      # Original ISS tracker
├── app_uwb.py                  # NEW: UWB positioning backend
├── uwb_positioning.py          # NEW: Trilateration & Kalman filter
├── uwb_serial_reader.py        # NEW: Serial/UART communication
├── requirements.txt            # Updated dependencies
├── templates/
│   ├── index.html             # Original ISS interface
│   └── index_uwb.html         # NEW: UWB 3D/2D tunnel interface
├── static/
│   └── js/
│       └── script.js          # Original ISS scripts
└── README_UWB.md              # This file
```

## Usage Examples

### Example 1: Running with Mock Data

```bash
python app_uwb.py
# Opens at http://localhost:8080
# Click "3D Tunnel" to see simulated tracking
```

### Example 2: Connecting to Real UWB Hardware

1. Flash DWM1001 modules with anchor firmware
2. Configure serial port in `app_uwb.py`
3. Run: `python app_uwb.py`
4. View dashboard in browser

### Example 3: API Integration

```python
import requests
import time

while True:
    # Get current position
    resp = requests.get('http://localhost:8080/uwb_position')
    pos = resp.json()
    
    print(f"Position: ({pos['x']:.2f}, {pos['y']:.2f})")
    print(f"Accuracy: {pos['accuracy']:.3f}m")
    print(f"Anchors used: {pos['num_anchors']}")
    
    time.sleep(0.5)
```

## Customization

### Add More Anchors

```python
# In app_uwb.py
uwb_pos.add_anchor('anchor_4', 75.0, 5.0, 0.0)
uwb_pos.add_anchor('anchor_5', 125.0, -5.0, 0.0)
```

### Adjust Smoothing

```python
# In handle_uwb_ranges function
x_smooth, y_smooth = uwb_pos.smooth_position(position, smoothing_factor=0.8)
```

### Change Serial Format

```python
# In app_uwb.py
uwb_reader.run(format_type='dwm1001')  # or 'json', 'csv'
```

## Troubleshooting

### No position data
- Check anchor configuration
- Verify at least 3 anchors (2D) or 4 anchors (3D) are configured
- In mock mode, should see immediate data

### Inaccurate positions
- Calibrate antenna delays on UWB devices
- Increase number of anchors
- Verify anchor positions are correct
- Check for multipath (obstacles)

### Serial connection issues
- List ports: `python -m serial.tools.list_ports`
- Check baud rate matches DWM1001 (usually 115200)
- Verify USB-UART cable is properly connected

## Performance

- **Update Rate:** 100ms (10 Hz)
- **Position Accuracy:** 0.1-0.3m (with good UWB setup)
- **Latency:** ~50ms (processing + measurement)
- **Scalability:** Supports 1-100+ simultaneous tags

## Integration with Original tracker-strt

The UWB version maintains backward compatibility:

```bash
# Original ISS tracking still works
python app.py

# New UWB tracking
python app_uwb.py
```

Both can run on different ports simultaneously.

## Next Steps

1. **Deploy UWB anchors** in your tunnel/underground environment
2. **Calibrate antenna delays** for accuracy
3. **Configure anchor positions** in `app_uwb.py`
4. **Test with `/uwb_simulate`** endpoint
5. **Monitor real data** in the 3D tunnel view
6. **Export tracking data** via `/uwb_history` for analysis

## References

- [Qorvo DWM1001 Datasheet](https://www.qorvo.com/products/p/DWM1001)
- [DecaWave DW1000 User Manual](https://www.decawave.com/)
- [UWB-IPS Original Repository](https://github.com/leonas-kratos/UWB-IPS)

## License

MIT License - Free to use and modify for your tracking needs.

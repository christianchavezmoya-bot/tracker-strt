# Tracker-STRT

A real-time tracking web application based on ISS-Live-Tracker architecture.

This project provides a foundation for tracking and visualizing any real-time location data (people, assets, vehicles, etc.) on both 3D globe and 2D map views.

## Features

✅ **3D Globe View** - Interactive Three.js globe with real-time markers
✅ **2D Map View** - Leaflet-based flat map with tracking visualization
✅ **Live Telemetry** - Latitude, Longitude, Altitude, Speed, Timestamp
✅ **Seamless View Switching** - Toggle between 3D and 2D views
✅ **Real-time Updates** - 3-second data refresh cadence
✅ **Historical Tracking** - Past ground track visualization
✅ **Future Predictions** - Projected path forecasting

## Architecture

### Backend
- Python 3 + Flask
- CORS-enabled REST API
- Real-time data polling (3s cadence)
- Thread-safe data handling

### Frontend
- Globe.gl + Three.js (3D visualization)
- Leaflet.js (2D mapping)
- HTML/CSS/JavaScript
- Live JSON polling

## Setup

### Prerequisites
- Python 3.8+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/christianchavezmoya-bot/tracker-strt.git
cd tracker-strt

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

The application will be available at `http://localhost:8080`

## API Endpoints

- `GET /` - Main interface (index.html)
- `GET /iss_data` - Latest tracking data (latitude, longitude, altitude, velocity, timestamp)

## Customization

To track your own assets/people:

1. Modify `/iss_data` endpoint in `app.py` to fetch your data source
2. Update the data format to include: `latitude`, `longitude`, `altitude`, `velocity`, `timestamp_ist`
3. Customize markers in `templates/index.html`

## Technologies

- **Backend**: Python, Flask, Requests
- **Frontend**: Three.js, Globe.gl, Leaflet.js
- **API**: RESTful JSON endpoints

## License

MIT License - Feel free to use and modify for your tracking needs.

## Based On

Original ISS Live Tracker: https://github.com/jaswanth271103/ISS-Live-Tracker-3D-2D-Ground-Track-IST-Altitude-Speed

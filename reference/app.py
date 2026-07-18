from flask import Flask, jsonify, render_template
from flask_cors import CORS
import requests
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# =========================
# HOME ROUTE (FRONTEND)
# =========================
@app.route("/")
def index():
    return render_template("index.html")


# =========================
# REAL-TIME DATA ROUTE
# =========================
@app.route("/iss_data")
def iss_data():
    try:
        # Reliable ISS API
        url = "https://api.wheretheiss.at/v1/satellites/25544"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return jsonify({"error": "ISS API failed"}), 500

        data = response.json()

        # Extract values
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        altitude = round(data.get("altitude"), 2)      # km
        velocity = round(data.get("velocity"), 2)      # km/h
        timestamp_utc = data.get("timestamp")

        # Convert UTC → IST
        ist_time = datetime.utcfromtimestamp(timestamp_utc) + timedelta(hours=5, minutes=30)
        ist_time_str = ist_time.strftime("%Y-%m-%d %H:%M:%S")

        return jsonify({
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "velocity": velocity,
            "timestamp_utc": timestamp_utc,
            "timestamp_ist": ist_time_str
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================
# MAIN ENTRY POINT
# =========================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=True
    )

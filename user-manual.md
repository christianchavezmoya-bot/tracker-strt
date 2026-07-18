# HOLO-RTLS — User Manual
## Indoor Real-Time Location System Command Center

> **Document Version:** 1.0 | **Application Version:** 1.0 | **Last Updated:** 2026-07-17

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Interface Overview](#2-interface-overview)
3. [Network & VLAN Setup](#3-network--vlan-setup)
4. [Map Calibration](#4-map-calibration)
5. [Managing Tracked Devices](#5-managing-tracked-devices)
6. [Zones, Sections & Layers](#6-zones-sections--layers)
7. [Alerts & Safety Monitoring](#7-alerts--safety-monitoring)
8. [Bi-Directional Control](#8-bi-directional-control)
9. [History & Playback](#9-history--playback)
10. [Reports & Statistics](#10-reports--statistics)
11. [AI Assistant](#11-ai-assistant)
12. [User Management](#12-user-management)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Getting Started

### 1.1 System Requirements

| Component | Minimum |
|---|---|
| PC | Gaming PC or workstation, RTX 3060+, 32GB RAM |
| OS | Windows 10 (21H2) or Windows 11 |
| Network | Ethernet connection to facility VLAN |
| Display | 1920×1080 or higher |

### 1.2 First Launch

1. **Run the application:** Double-click `HOLO-RTLS.exe`
2. **Login screen appears:** Enter your credentials (provided by your administrator)
   - Default admin account: `admin` / `admin123` (change this immediately)
   - Default operator account: `security` / `security123`
   - Default viewer account: `viewer` / `viewer123`
3. **Connect to network:** If not already configured, see [Section 3: Network & VLAN Setup](#3-network--vlan-setup)
4. **Load your CAD map:** The map loads automatically if pre-configured. If not, see [Section 4: Map Calibration](#4-map-calibration)
5. **Verify connection:** The status indicator in the top-right corner should turn green

### 1.3 Login Screen

| Field | Description |
|---|---|
| Username | Your assigned username (case-sensitive) |
| Password | Your password (case-sensitive) |
| Remember Me | Saves credentials for faster login (Admin only) |

**Note:** After 3 failed login attempts, the account is locked for 5 minutes as a security measure.

---

## 2. Interface Overview

### 2.1 Main Screen Regions

```
┌─────────────────────────────────────────────────────────────────┐
│ [Status: ● Connected]  [2D | 3D]  [Search: ____________] [⚙️] [👤]│  ← Top Bar
├────────────┬────────────────────────────────────────────────────┤
│            │                                                     │
│  TAG LIST  │                                                     │
│  ─────────  │                                                     │
│  🔍 Filter  │              HOLOGRAPHIC MAP VIEW                  │
│  ○ All      │                                                     │
│  ○ Personnel│          (CAD Image / 3D Tunnel / Zones)          │
│  ○ Machines │                                                     │
│  ○ Sensors  │                    [●] [●] [●]                     │
│            │                   (Tracking Dots)                  │
│  ─────────  │                                                     │
│  👤 John D. │                                                     │
│  👤 Jane S. │                                                     │
│  🔧 Fork-01 │                                                     │
│  🔧 Crane-2 │                                                     │
│            │                                                     │
├────────────┴────────────────────────────────────────────────────┤
│ [Statistics Bar:  287 Active  |  12 Alerts  |  45 Checked In]   │  ← Status Strip
└─────────────────────────────────────────────────────────────────┘
  ↑
  Left Panel
       ← Tag Detail Side Panel (appears when tag selected)
```

### 2.2 Top Bar

| Element | Function |
|---|---|
| Status indicator | Green = connected to MQTT broker. Red = disconnected. Yellow = reconnecting. |
| 2D / 3D toggle | Switch between floor plan view and 3D tunnel/perspective view |
| Search bar | Type name or hardware ID to instantly find and zoom to a tag |
| ⚙ Settings | Opens settings panel |
| 👤 User menu | Shows current user role; click for logout and user settings |

### 2.3 Left Panel (Tag List)

| Element | Function |
|---|---|
| Filter checkboxes | Show/hide by type: Personnel, Machines, Sensors |
| Alert filter | Show only tags with active alerts |
| Tag list | Scrollable list of all active tags. Click to select and zoom. |
| Color dots | Green = normal, Yellow = warning, Red = alert, Gray = offline |

### 2.4 Right Panel (Tag Detail — appears on selection)

| Tab | Contents |
|---|---|
| **Info** | Name, hardware ID, type, category, asset state, custom icon |
| **Vitals** | Heart rate (if smartwatch), SpO2, battery level, temperature |
| **Location** | Current section, current zone, floor/level, coordinates |
| **Stats** | Total distance traveled today, time in current section |
| **History** | Timeline of recent positions; "View Full History" button |
| **Actions** | Trigger alarm, send message, initiate call (role-dependent) |

### 2.5 Camera Controls

| Input | Action |
|---|---|
| **Right-click + drag** | Rotate camera around map center (360°) |
| **Scroll wheel** | Zoom in / out |
| **Middle-click + drag** | Pan the map |
| **Double-click on tag** | Zoom to and select that tag |
| **Double-click on empty space** | Reset camera to default position |
| **2D / 3D toggle** | Switch rendering mode |

### 2.6 Holographic Visual States

| Dot Color | Meaning |
|---|---|
| **Cyan (glowing)** | Normal — tag is active and reporting |
| **Yellow (pulsing)** | Warning — low battery, or in restricted zone |
| **Red (fast pulse)** | Critical alert — no signal, man-down, vitals critical |
| **Gray (dim)** | Offline, decommissioned, or in maintenance |
| **Blue ring** | Currently selected / in focus |
| **White lines** | Proximity connections to nearby tags |

---

## 3. Network & VLAN Setup

### 3.1 Opening Network Settings

1. Click the **⚙ Settings** icon in the top-right corner
2. Select **Network** from the settings menu
3. The Network Configuration panel opens

### 3.2 Configuring MQTT Connection

| Setting | Description | Default |
|---|---|---|
| **Broker IP** | IP address of your MQTT broker on the VLAN | `127.0.0.1` |
| **Broker Port** | MQTT port (TLS: 8883, Plain: 1883) | `1883` |
| **Use TLS/SSL** | Enable encrypted connection | Off (off) |
| **Username** | MQTT broker username | (blank) |
| **Password** | MQTT broker password | (blank) |
| **Auto-reconnect** | Automatically reconnect if connection drops | On |

**To test your connection:**
1. Enter the broker IP and port
2. Click **Test Connection**
3. Status will show ✓ Connected or ✗ Failed with error reason

### 3.3 NTP Time Sync

The system uses Coordinated Universal Time (UTC) for all timestamps.

If timestamps appear incorrect:
1. Go to **Settings → System**
2. Verify the NTP server address (contact your IT admin)
3. Click **Sync Time**

---

## 4. Map Calibration

### 4.1 Importing Your CAD Map

**Supported formats:** PNG (recommended), SVG, JPEG

1. Go to **Settings → Map**
2. Click **Import CAD Image**
3. Select your file
4. A dialog appears asking for real-world dimensions:
   - **Width:** Enter the width in meters (e.g., `50`)
   - **Height:** Enter the height in meters (e.g., `30`)
5. Click **Apply**
6. The map image now scales correctly: 100 pixels = 1 meter

**Tips for best results:**
- Export your CAD as a lossless PNG at 300 DPI
- Remove unnecessary borders and text labels from the CAD before import
- Use a dark-themed map image for best holographic contrast

### 4.2 Calibrating WiFi / BLE Nodes

WiFi nodes are the fixed anchor points that detect BLE tags and smartphones. They must be placed on the map in their exact real-world locations.

**To calibrate a node:**

1. Open **Admin Tools → Node Management**
2. Your deployed edge nodes appear as **glowing spheres** at the center of the map (uncalibrated)
3. **Click and drag** the sphere to the correct physical location on the floor plan
4. **Right-click** the sphere → **Rename** → enter a descriptive name (e.g., `North Entrance Node`, `Loading Dock Pi`)
5. Right-click → **Set Type** → choose:
   - **Standard:** Regular detection node
   - **Check-In:** Personnel must pass through to register as checked-in
   - **Check-Out:** Personnel pass through to register as checked-out
6. Changes save automatically

**Minimum calibration:** You need at least **3 nodes** for triangulation to work accurately. More nodes = better accuracy.

**Visual indicators:**
| Sphere Color | Status |
|---|---|
| Green | Active and reporting |
| Yellow | Active but weak signal |
| Red | Offline (no heartbeat in 10+ seconds) |
| Cyan (dim) | Uncalibrated — needs to be dragged to position |

### 4.3 Map Calibration Points (Advanced)

If your CAD image is rotated or skewed relative to real-world coordinates:

1. Go to **Settings → Map → Advanced**
2. Click **Add Calibration Point**
3. Click on the map where a known reference point is located (e.g., a building corner)
4. Enter the real-world X, Y coordinates for that point
5. Repeat for at least **2 points** (4 points recommended for full perspective correction)
6. Click **Apply Transformation Matrix**
7. The map now correctly maps to real-world coordinates

---

## 5. Managing Tracked Devices

### 5.1 Understanding Device Types

| Type | Icon | Description |
|---|---|---|
| **Personnel Tag** | 👤 | BLE badge/wearable carried by staff |
| **Smartwatch** | ⌚ | Wearable with vital sign monitoring |
| **Machine Tag** | 🔧 | BLE tag attached to equipment/vehicles |
| **Smartphone** | 📱 | Auto-detected BYOD device |
| **Environmental Sensor** | 🌡️ | Fixed gas/temperature sensor |
| **UWB Anchor** | 📡 | Fixed infrastructure for cm-accuracy zones |

### 5.2 Searching for a Tag

1. Click the **search bar** in the top bar (or press `Ctrl+F`)
2. Type the tag's assigned name or hardware ID
3. Results filter in real-time as you type
4. The map zooms to the matching tag
5. Press `Enter` to select it, or click the result in the dropdown

**Examples:**
- `"John"` → finds all tags with "John" in the name
- `"Tag-042"` → finds exact hardware ID match
- `"forklift"` → finds all tags with "forklift" (case-insensitive)

### 5.3 Filtering the Tag List

Use the left panel checkboxes to filter what you see:

| Filter | Shows |
|---|---|
| **Personnel** | Only personnel tags and smartwatches |
| **Machines** | Only machine tags |
| **Sensors** | Only environmental sensors |
| **Alerts Only** | Only tags with active alerts |
| **Offline Only** | Only tags that have stopped reporting |
| **Checked-In Only** | Only tags currently checked-in |

Filters apply to both the **map dots** and the **tag list panel** simultaneously.

### 5.4 Editing Tag Information

1. **Click a tag** on the map or in the tag list
2. The **Tag Detail Panel** opens on the right
3. Click the **Info** tab
4. Edit fields:
   - **Assigned Name:** Human-readable name (e.g., `John Martinez - Security`)
   - **Type:** Personnel / Machine / Sensor
   - **Category:** Tag / Smartphone / Smartwatch / UWB Anchor
   - **Custom Icon:** Click to upload a picture (PNG, 128×128px)
5. Click **Save** — changes persist to the database and sync to all connected screens

### 5.5 Assigning Custom Icons to Tags

1. Select the tag
2. Go to **Info** tab → **Custom Icon** section
3. Click **Choose Image**
4. Select a PNG or JPG file (recommended: 128×128px, transparent background)
5. Click **Apply**
6. The tag's icon updates across the map, tag list, and all reports

### 5.6 Asset Lifecycle

To prevent old devices from cluttering your active list:

| State | Description |
|---|---|
| **Active** | Normal operation, appears on map |
| **Offline** | Has not reported in >5 minutes. Still visible but grayed out |
| **Maintenance** | Tagged for repair. Hidden by default filter. |
| **Decommissioned** | Permanently retired. Archived but not shown. |

**To change asset state:**
1. Select tag → **Info** tab
2. Click the **State** dropdown
3. Select the new state
4. Click **Save**

---

## 6. Zones, Sections & Layers

### 6.1 Layer Types

| Layer | Color | Description |
|---|---|---|
| **POI** (Point of Interest) | Blue | Notable locations (exits, offices, break rooms) |
| **Safe Zone** | Green | Designated safe areas (muster points, shelters) |
| **Fuel Station** | Orange | Fueling or charging stations |
| **Restricted Zone** | Red | Hazardous areas — triggers alarm when entered |
| **Section** | Semi-transparent | Named areas for reporting (e.g., "Assembly Line A") |

### 6.2 Adding a Zone (Admin / Security Operator)

1. Click the **Draw Zone** tool in the toolbar (or press `Z`)
2. Choose zone type from the dropdown
3. **Click on the map** to place polygon points
4. Click near the first point to **close the polygon**
5. A dialog appears:
   - **Name:** Enter a name (e.g., `High Voltage Room`)
   - **Type:** Confirm the type (Restricted zones auto-trigger alerts)
   - **Color:** Choose or confirm the color
   - **Notes:** Optional description
6. Click **Create Zone**
7. The zone appears on the map and is saved to the database

### 6.3 Editing a Zone

1. **Right-click** the zone ring on the map → **Edit Zone**
2. Drag the **handles** to resize or reshape
3. Drag the **center** to move the zone
4. Right-click → **Rename** to change the name
5. Right-click → **Delete** to remove the zone

**To convert a zone type:**
- Right-click → **Set Type** → choose new type
- *Note: Changing to "Restricted" activates geofence alerts immediately*

### 6.4 Drawing a Section

Sections are larger areas used for reporting (dwell time, personnel count).

1. Click the **Draw Section** tool in the toolbar (or press `S`)
2. Click points to outline the area (can be any polygon shape)
3. Click near the starting point to close
4. Enter section name and details
5. Click **Create Section**

**Use cases:**
- Define work areas: "Assembly Line B", "Warehouse Zone 3"
- Set evacuation muster boundaries
- Create reporting regions for dwell-time analytics

### 6.5 Layer Visibility Toggles

Click the **Layers** button in the toolbar to show/hide each layer type:

```
☐ POI Markers
☑ Safe Zones
☑ Restricted Zones
☐ Fuel Stations
☑ Sections
☐ Heatmap
☐ WiFi Node Anchors
```

Turning off a layer hides its elements from the map without deleting them.

---

## 7. Alerts & Safety Monitoring

### 7.1 Alert Types

| Alert | Trigger | Visual | Sound |
|---|---|---|---|
| **No Signal** | Tag silent for X seconds (default: 30s) | Red dot, grayed out | Beep |
| **No Movement** | Tag stationary for X seconds (default: 5 min) | Yellow dot, pulsing | Beep |
| **Restricted Zone** | Tag enters restricted area | Red dot, red zone flash | Alarm |
| **Low Battery** | Battery below threshold (default: 20%) | Yellow battery icon | None |
| **Critical Vitals** | HR > 150, HR < 40, or SpO2 < 90% | Red dot, vitals panel flash | Alarm |
| **Environmental** | Gas PPM > threshold or temp > 60°C | Orange sensor icon | Alarm |
| **Node Offline** | WiFi node silent for 10+ seconds | Red sphere at node location | Beep |

### 7.2 Alert Thresholds (Admin Only)

1. Go to **Settings → Alerts**
2. Adjust thresholds:
   - **No Signal Timeout:** 15–300 seconds (slider)
   - **No Movement Timeout:** 1–30 minutes (slider)
   - **No Movement Distance:** 0.1–2.0 meters (slider)
   - **Low Battery Threshold:** 5–50% (slider)
   - **Critical HR High:** 100–200 bpm (slider)
   - **Critical HR Low:** 30–60 bpm (slider)
   - **Critical SpO2:** 80–95% (slider)
   - **Gas PPM Warning:** 100–1000 (slider)
3. Click **Apply** — changes take effect immediately

### 7.3 Alert Panel

Click the **bell icon** (🔔) in the top bar to open the Alert Panel:

| Column | Description |
|---|---|
| **Time** | When the alert was triggered (HH:MM:SS) |
| **Tag** | Name of the affected tag |
| **Alert Type** | Category of alert |
| **Zone/Section** | Where the alert occurred |
| **Status** | 🔴 Active / ✅ Acknowledged |

**To acknowledge an alert:**
1. Click the alert in the list
2. Click **Acknowledge** (or press `A`)
3. The alert moves to the acknowledged section
4. The audio alarm stops (if this was the last active critical alert)

### 7.4 Audio Alarm Behavior

| Situation | Audio Behavior |
|---|---|
| Normal alert (NoSignal, NoMovement) | Single beep, no repeat |
| Low battery | Silent (visual only) |
| Restricted zone entry | Repeating alarm (3 beeps) until acknowledged |
| Critical vitals | Urgent repeating alarm until acknowledged |
| Environmental hazard | Full evacuation alarm pattern |

**Mute controls:**
- 🔊 **Sound On** / 🔇 **Sound Off** — global mute
- 🔕 **Mute This Tag** — per-tag silence

---

## 8. Bi-Directional Control

> **Note:** Requires Security Operator or Admin role. These actions are logged in the audit trail.

### 8.1 Triggering an Alarm on a Tag

Use this to locate a person or make them aware of an emergency.

1. Select the tag on the map or in the tag list
2. Go to the **Actions** tab in the Tag Detail Panel
3. Click **🔴 Trigger Alarm**
4. Confirm the action
5. The tag's device vibrates/beeps loudly
6. The map shows an "Alarm Triggered" confirmation
7. **Audit log entry:** `User [name] triggered alarm on [tag] at [timestamp]`

### 8.2 Sending a Message to a Tag

For tags/smartwatches that support text display:

1. Select the tag
2. Click **💬 Send Message**
3. Type your message (max 140 characters)
4. Click **Send**
5. The message appears on the tag's screen

### 8.3 Initiating a Call

1. Select the tag
2. Click **📞 Initiate Call**
3. The tag receives a call notification
4. The tag holder can answer (if the device supports it)

### 8.4 Mass Alert (Broadcast)

**Emergency evacuation scenario:**

1. Go to **Admin Tools → Mass Alert**
2. Choose the scope:
   - **All Tags:** Every registered tag
   - **By Section:** Select a section → all tags in that area
   - **By Type:** All Personnel / All Machines
3. Choose the action: **Trigger Alarm** / **Send Message**
4. Enter message (if applicable)
5. Click **Send Broadcast**
6. Confirmation dialog shows how many tags will receive the command

---

## 9. History & Playback

### 9.1 Viewing Tag History

1. Select the tag on the map
2. Go to the **History** tab in the Tag Detail Panel
3. A **timeline** shows the tag's path over the last 60 seconds (live buffer)
4. The **path line** on the map shows where the tag has been

### 9.2 History Playback (Time Travel)

For detailed investigation:

1. With a tag selected, click **▶ Full History** in the History tab
2. The **Playback Panel** opens
3. Use the **time slider** to scrub through past positions
4. The map shows the tag at the selected point in time
5. The **timestamp display** shows the exact time: `2026-07-17 14:32:05`
6. Click **▶ Play** to animate the tag's path automatically

**Controls:**
| Button | Action |
|---|---|
| ▶ Play / ⏸ Pause | Animate playback at 1× speed |
| ⏮ | Jump to start |
| ⏭ | Jump to end |
| Speed: 1× / 2× / 4× | Playback speed |
| 📥 Export | Download history as CSV |

### 9.3 Long-Term History Query

To view data older than 60 seconds (stored in database):

1. Select tag → **History** tab → **Extended Query**
2. Set **Date Range:** Today / Last 7 Days / Custom Range
3. Click **Load**
4. The playback panel populates with historical data
5. Use the slider to navigate

---

## 10. Reports & Statistics

### 10.1 Statistics Dashboard

Click **📊 Stats** in the toolbar to open the real-time dashboard:

| Widget | Description |
|---|---|
| **Active Devices** | Count of tags reporting in the last 30 seconds |
| **Alert Summary** | Breakdown by alert type |
| **Personnel Count** | Current total across all sections |
| **Section Population** | Bar chart of tag count per section |
| **Battery Status** | % of tags above/below threshold |
| **Top Movers** | Tags that traveled the most distance today |

### 10.2 Generating a Report

1. Click **Reports** in the toolbar (or press `Ctrl+R`)
2. Choose report type:
   - **Daily Summary:** Overview of all activity for the day
   - **Personnel Report:** Check-in/out log, locations, duration
   - **Alert Report:** All alerts in the period
   - **Muster Report:** Current status of all checked-in personnel
   - **Custom Report:** Build your own with selected fields
3. Set **Date Range:** Today / Yesterday / Last 7 Days / Custom
4. Set **Filters:** By section, by tag type, by alert status
5. Click **Preview** to view in-app
6. Click **Export** to download

### 10.3 Email Report Delivery

**To schedule automatic email reports:**

1. Go to **Settings → Reports → Email Delivery**
2. Enter **Recipient Email** (add multiple, one per line)
3. Set **Schedule:**
   - **Daily** — sends at a configured time each day
   - **Weekly** — sends on a configured day each week
   - **On Demand** — only when manually triggered
4. Configure **SMTP Server:**
   - **SMTP Host:** e.g., `smtp.yourcompany.com`
   - **Port:** typically `587` (TLS) or `465` (SSL)
   - **Username / Password:** Email account credentials
   - **From Address:** The sender email shown in reports
5. Click **Send Test Email** to verify configuration
6. Click **Save Schedule**

### 10.4 Report Contents

Each report includes:
- Tag name, hardware ID, type, section
- Total distance traveled (in meters)
- Time spent in each section
- Alert count and types triggered
- Battery levels at start and end of period
- Check-in / check-out timestamps

---

## 11. AI Assistant

### 11.1 Opening the AI Panel

Click the **🤖 AI** icon in the bottom-left corner of the screen.

A chat panel opens. The AI assistant is powered by a local language model — no internet required.

### 11.2 Available Commands

Type naturally. Examples:

| Query | What Happens |
|---|---|
| `"Show me all tags with low battery"` | Filters to low-battery tags, highlights on map |
| `"Where is John Martinez?"` | Zooms to John's tag, opens detail panel |
| `"How many people are in Sector 4?"` | Shows personnel count for that section |
| `"Trigger alarm on all forklift operators"` | Opens mass alert confirmation with filtered list |
| `"What's the alert status right now?"` | Displays summary of all active alerts |
| `"Show movement patterns for the past hour"` | Displays heatmap or path visualization |
| `"Who hasn't moved in the last 10 minutes?"` | Shows stationary tags, filters to them |
| `"Generate a report for yesterday"` | Opens report panel with yesterday's date |

### 11.3 AI Chat History

- Chat history is shown in the panel
- Click a previous message to re-run the query
- The AI may ask clarifying questions if your query is ambiguous
- If the AI is unavailable (Ollama not running), the panel shows: *"AI Assistant is currently unavailable. Check that Ollama is running on the command PC."*

---

## 12. User Management

> **Note:** User management requires **Admin** role.

### 12.1 Adding a New User

1. Go to **Settings → Users** (Admin only)
2. Click **+ Add User**
3. Fill in:
   - **Username:** Unique login name
   - **Display Name:** Full name for display
   - **Password:** Initial password (user should change on first login)
   - **Role:** Admin / Security Operator / Viewer
4. Click **Create User**
5. The user appears in the user list

### 12.2 Roles Reference

| Permission | Admin | Security Operator | Viewer |
|---|---|---|---|
| View live map | ✅ | ✅ | ✅ |
| View history | ✅ | ✅ | ✅ |
| View reports | ✅ | ✅ | ✅ |
| Trigger alarms | ✅ | ✅ | ❌ |
| Send messages | ✅ | ✅ | ❌ |
| Edit tag names | ✅ | ✅ | ❌ |
| Draw zones | ✅ | ✅ | ❌ |
| Edit WiFi nodes | ✅ | ✅ | ❌ |
| Change alert thresholds | ✅ | ✅ | ❌ |
| Manage users | ✅ | ❌ | ❌ |
| System settings | ✅ | ❌ | ❌ |
| Delete sections | ✅ | ❌ | ❌ |

### 12.3 Editing a User

1. In **Settings → Users**, click the user row
2. Edit any field
3. Click **Save Changes**

### 12.4 Deactivating a User

1. Click the user row
2. Click **Deactivate Account**
3. The user cannot log in but their audit log history is preserved

### 12.5 Changing Your Password

1. Click your **👤 username** in the top bar
2. Select **Change Password**
3. Enter current password
4. Enter new password (min. 8 characters, recommend 12+)
5. Confirm new password
6. Click **Update Password**

---

## 13. Troubleshooting

### 13.1 Connection Issues

| Symptom | Solution |
|---|---|
| Status shows **Red** (disconnected) | Check that the MQTT broker PC is on and reachable |
| "Connection refused" error | Verify IP address, port, username, and password |
| Connects then disconnects immediately | Check if another instance is running with the same client ID |
| Tags not appearing | Verify WiFi nodes are powered on and connected to VLAN |
| Tags appearing but not moving | Check if RSSI values are changing. If static, check for WiFi node antenna issues. |

### 13.2 Performance Issues

| Symptom | Solution |
|---|---|
| Frame rate drops below 60 FPS | Close other applications; reduce overlay effects in Settings → Display |
| Tags jittery | Normal during peak message rate; the Kalman filter smooths within ~1 second |
| Map loading slowly | Ensure CAD image is <10MB; use PNG not TIFF |
| 300+ tags causing lag | Expected at maximum load; system is designed for this |
| History playback stuttering | Use the time slider slowly; playback speed 1× is recommended |

### 13.3 Alert Issues

| Symptom | Solution |
|---|---|
| "No Signal" on active tags | Check WiFi node near that area; tags may be out of range |
| Restricted zone alerts not firing | Verify the zone is set to **Restricted** type, not just colored red |
| Alerts spam repeatedly | Click **Acknowledge** — this clears the active alert state for that trigger |
| Can't acknowledge alert | Verify your role has permission (Security Operator or Admin) |

### 13.4 Edge Node (Pi) Issues

| Symptom | Solution |
|---|---|
| Node appears Red in Node Management | SSH into the Pi → `systemctl status rtls` → check logs |
| No RSSI data from a node | Check BLE antenna is connected; try `hciconfig hci0 up` |
| Pi overheating | Move to a cooler location; add heatsink; check PoE voltage |
| Pi disconnected from network | Check Ethernet cable; verify switch port configuration |

### 13.5 LLM / AI Issues

| Symptom | Solution |
|---|---|
| AI panel shows "unavailable" | Verify Ollama is running: `curl localhost:11434/api/tags` |
| AI gives wrong filter results | Try more specific phrasing; AI output is validated against schema |
| AI slow to respond | Normal for first query (model loading); subsequent queries are faster |
| AI ignores commands | AI only executes filtered commands — open-ended conversation is read-only |

---

*End of User Manual — HOLO-RTLS v1.0*

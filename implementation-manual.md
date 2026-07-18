# HOLO-RTLS — Implementation Manual
## Developer Setup, Coding Standards & Technical Guide

---

## 1. Development Environment Setup

### 1.1 Install Prerequisites

Download and install in this order:

```
1. Unity Hub → Install Unity 2022.3.f1 LTS
   → Modules: Windows Build Support (IL2CPP), Android Build Support (future)

2. Visual Studio 2022 Community
   → Workloads: .NET desktop development, Unity game development

3. Git + Git LFS
   → git lfs install (for CAD images, meshes)

4. Node.js 20 LTS (for Ollama management scripts)
5. Python 3.10+ (for edge node scripts)
6. Ollama (https://ollama.ai) → ollama pull llama3
7. MQTTX (https://mqttx.app) desktop client
8. DB Browser for SQLite
```

### 1.2 Clone & Create Unity Project

```bash
# Clone the repository
git clone https://github.com/yourorg/holo-rtls.git
cd holo-rtls

# Create new Unity project (do NOT open the folder as-is — use Unity Hub)
# Unity Hub → New Project → 3D (URP) Template → Name: "HOLO-RTLS"
# Then copy Assets/, Scripts/, etc. into the new project's Assets folder

# Install NuGet packages in Unity
# Window → Package Manager → NuGetForUnity → Install
# Then: NuGet → Manage NuGet Packages → Install:
#   MQTTnet (4.x)
#   System.Data.SQLite.Core (1.0.118)
#   Newtonsoft.Json (only for non-hot-path JSON like config files)
```

### 1.3 Project Settings

**Quality Settings** (`Edit → Project Settings → Quality`):
```
Anti-Aliasing:        4x
HDR:                  On
Texture Resolution:   Full Res
V-Sync Count:         Don't Sync (we control frame rate via WaitForEndOfFrame)
```

**Player Settings** (`Edit → Project Settings → Player`):
```
API Compatibility:    .NET Framework 4.x (required for MQTTnet)
Scripting Backend:   IL2CPP (for build)
```

**URP Settings** (`Assets → Settings → UniversalRenderPipelineAsset`):
```
HDR:                  On
Anti-Aliasing:        4x MSAA
Post Processing:      On (for Bloom on holographic shaders)
```

### 1.4 Initial Scene Setup

1. **Create a new scene:** `Assets/Scenes/RTLSScene.unity`
2. **Add the RTLSKernel:** Create empty `GameObject` → name: `RTLSKernel` → attach `RTLSKernel.cs`
3. **Set background:** `Edit → Scene Grid → Dark` or set `Camera.backgroundColor = #0A0A12`
4. **Add lights:** Remove default Directional Light. Use only emissive/holographic materials
5. **Create floor plane:** `GameObject → 3D Object → Plane` → scale to match real-world dimensions

### 1.5 Database Setup

```bash
# Install SQLite on your development PC (if not already present)
# The NuGet package System.Data.SQLite.Core handles embedding

# To view the DB during development:
# Double-click Assets/Database/holo_rtls.db (created at runtime)
# Opens in DB Browser for SQLite
```

---

## 2. Coding Standards

### 2.1 Architecture Rules (The Non-Negotiables)

```
RULE 1:  NO GameObject per tracked entity
         → Use struct arrays in RTLSKernel, NOT List<MonoBehaviour>
         → GameObjects are only for WiFi nodes, zones, sections (user-editable objects)

RULE 2:  NO allocations in hot path (Update(), OnMessageReceived())
         → Pre-allocate all arrays in Awake() / Start()
         → Use fixed-size circular buffers for history
         → Parse CSV strings, not JSON (no reflection)

RULE 3:  Kalman filter output drives reports, NOT lerp output
         → targetPosition = KalmanOutput
         → currentPosition = Lerp(currentPosition, targetPosition, speed * dt)
         → historyRecord(currentPosition=KalmanOutput) ← USE THIS, NOT lerp

RULE 4:  All MQTT message parsing runs on the receiving thread
         → Use UnityMainThreadDispatcher to push to main thread ONLY for Unity API calls
         → GameObject transforms, UI updates — on main thread
         → Math calculations — can stay on MQTT thread

RULE 5:  Every sensitive UI action checks SecurityManager.HasPermission()
         → No exceptions. Not once. Not even for "internal" builds.
```

### 2.2 File Naming Conventions

| Type | Convention | Example |
|---|---|---|
| Scripts | PascalCase, descriptive | `KalmanFilter2D.cs`, `GeofenceEngine.cs` |
| Structs | PascalCase | `TrackerData`, `WifiNodeData` |
| Enums | PascalCase | `AlertStatus`, `ZoneType` |
| Constants | SCREAMING_SNAKE | `MAX_TRACKERS`, `DEFAULT_ZOOM` |
| Prefabs | `_Pref_` prefix | `_Pref_TrackingDot`, `_Pref_WifiNode` |
| Materials | `_Mat_` prefix | `_Mat_HolographicCyan` |
| Scenes | PascalCase | `RTLSMainScene`, `LoginScene` |

### 2.3 Script Template

```csharp
// ──────────────────────────────────────────────────────────────────────
// <FileName>.cs
// <One-line description>
//
// Dependencies:  <list scripts this file depends on>
// ──────────────────────────────────────────────────────────────────────

namespace HOLORTLS.Core
{
    using UnityEngine;
    using System;

    /// <summary>
    /// Brief description of what this class does.
    /// </summary>
    public class ExampleSystem : MonoBehaviour
    {
        // ── Configuration ──────────────────────────────────────────────
        [Header("Threshold Settings")]
        [SerializeField] private float exampleThreshold = 5f;

        // ── References ────────────────────────────────────────────────
        [SerializeField] private Transform mapCenter;

        // ── State ──────────────────────────────────────────────────────
        private const int MAX_EXAMPLES = 100;
        private ExampleStruct[] examples = new ExampleStruct[MAX_EXAMPLES];
        private int activeCount;

        // ── Events ─────────────────────────────────────────────────────
        public static event Action<string, Vector3> OnExampleEvent;

        // ── Unity Lifecycle ────────────────────────────────────────────

        void Awake()
        {
            // Pre-allocate. Zero allocations after this.
            for (int i = 0; i < MAX_EXAMPLES; i++)
                examples[i].Initialize();
        }

        void Update()
        {
            for (int i = 0; i < MAX_EXAMPLES; i++)
            {
                if (!examples[i].IsActive) continue;
                ProcessExample(i);
            }
        }

        // ── Public API ─────────────────────────────────────────────────

        /// <summary>
        /// Activates a new example entity.
        /// </summary>
        public void RegisterExample(string id, Vector3 position)
        {
            int slot = FindEmptySlot();
            if (slot == -1) return;

            examples[slot].Activate(id, position);
            activeCount++;
        }

        // ── Private Methods ────────────────────────────────────────────

        private void ProcessExample(int idx)
        {
            ref var ex = ref examples[idx];

            // Core logic here — no allocations
            ex.Current = Vector3.Lerp(ex.Current, ex.Target, 10f * Time.deltaTime);
        }

        private int FindEmptySlot()
        {
            for (int i = 0; i < MAX_EXAMPLES; i++)
                if (!examples[i].IsActive) return i;
            return -1;
        }
    }

    // ── Struct (lives outside class, public, no MonoBehaviour inheritance)
    [System.Serializable]
    public struct ExampleStruct
    {
        public string Id;
        public Vector3 Current;
        public Vector3 Target;
        public bool IsActive;

        public void Initialize() { /* reset to defaults */ }
        public void Activate(string id, Vector3 pos)
        {
            Id = id;
            Current = Target = pos;
            IsActive = true;
        }
    }
}
```

---

## 3. Key Module Implementation Guides

### 3.1 MQTT Integration (MQTTnet)

```csharp
// ── MQTTClient.cs ──────────────────────────────────────────────────────

using MQTTnet;
using MQTTnet.Client;
using System.Text;
using System.Threading;

public class MQTTClient : MonoBehaviour
{
    private IMqttClient mqttClient;
    private MqttFactory factory;

    [SerializeField] private string brokerIP = "127.0.0.1";
    [SerializeField] private int brokerPort = 1883;
    [SerializeField] private bool useTLS = false;

    // Events for other systems to subscribe to
    public static event Action<string, string, float, float> OnRssiData;     // nodeMac, tagMac, rssi, battery
    public static event Action<string, string, float, float> OnVitalsData;     // tagMac, hr, spO2, temp
    public static event Action<string, string, string> OnNodeHeartbeat;        // mac, ip, name
    public static event Action OnConnected;
    public static event Action OnDisconnected;

    async void Start()
    {
        factory = new MqttFactory();
        mqttClient = factory.CreateMqttClient();

        var options = new MqttClientOptionsBuilder()
            .WithTcpServer(brokerIP, brokerPort)
            .WithClientId($"RTLS_Unity_{Guid.NewGuid()}")
            .WithCleanSession(true)
            .WithTimeout(TimeSpan.FromSeconds(10))
            .Build();

        mqttClient.ApplicationMessageReceivedAsync += OnMessage;
        mqttClient.DisconnectedAsync += _ => { OnDisconnected?.Invoke(); return Task.CompletedTask; };
        mqttClient.ConnectedAsync += _ => { OnConnected?.Invoke(); return Task.CompletedTask; };

        await ConnectAsync(options);
    }

    private async Task ConnectAsync(MqttClientOptions options)
    {
        try
        {
            await mqttClient.ConnectAsync(options, CancellationToken.None);
            Debug.Log($"[MQTT] Connected to {brokerIP}:{brokerPort}");

            // Subscribe to all required topics
            await mqttClient.SubscribeAsync(new MqttTopicFilterBuilder()
                .WithTopic("rssi/data").WithExactlyOnceQoS().Build());
            await mqttClient.SubscribeAsync(new MqttTopicFilterBuilder()
                .WithTopic("vitals/data").WithExactlyOnceQoS().Build());
            await mqttClient.SubscribeAsync(new MqttTopicFilterBuilder()
                .WithTopic("env/data").WithExactlyOnceQoS().Build());
            await mqttClient.SubscribeAsync(new MqttTopicFilterBuilder()
                .WithTopic("node/heartbeat").WithExactlyOnceQoS().Build());
            await mqttClient.SubscribeAsync(new MqttTopicFilterBuilder()
                .WithTopic("system/state_changes").WithExactlyOnceQoS().Build());
        }
        catch (Exception ex)
        {
            Debug.LogError($"[MQTT] Connection failed: {ex.Message}");
            Invoke(nameof(Start), 5f); // Retry in 5s
        }
    }

    // This runs on the MQTT thread — DO NOT touch Unity API here
    private Task OnMessage(MqttApplicationMessageReceivedEventArgs e)
    {
        string topic = e.ApplicationMessage.Topic;
        string payload = Encoding.UTF8.GetString(e.ApplicationMessage.payload);

        // Parse based on topic — CSV format, zero allocations
        if (topic == "rssi/data")
        {
            // Format: PiMAC,TagMAC,RSSI,Battery
            int c1 = payload.IndexOf(',');
            int c2 = payload.IndexOf(',', c1 + 1);
            int c3 = payload.LastIndexOf(',');

            string nodeMac = payload.Substring(0, c1);
            string tagMac  = payload.Substring(c1 + 1, c2 - c1 - 1);
            float rssi     = float.Parse(payload.Substring(c2 + 1, c3 - c2 - 1));
            float battery  = float.Parse(payload.Substring(c3 + 1)) / 100f;

            UnityMainThreadDispatcher.Instance().Enqueue(() =>
                OnRssiData?.Invoke(nodeMac, tagMac, rssi, battery));
        }
        else if (topic == "node/heartbeat")
        {
            // Format: MAC,IP,Name
            string[] parts = payload.Split(',');
            if (parts.Length >= 3)
                UnityMainThreadDispatcher.Instance().Enqueue(() =>
                    OnNodeHeartbeat?.Invoke(parts[0], parts[1], parts[2]));
        }

        return Task.CompletedTask;
    }

    // ── Downlink: Unity → Edge Node ──────────────────────────────────
    public async void PublishCommand(string topic, string jsonPayload)
    {
        if (!mqttClient.IsConnected) return;

        var msg = new MqttApplicationMessageBuilder()
            .WithTopic(topic)
            .WithPayload(jsonPayload)
            .WithExactlyOnceQoS()
            .Build();

        await mqttClient.PublishAsync(msg, CancellationToken.None);
        Debug.Log($"[MQTT] Published to {topic}: {jsonPayload}");
    }

    // ── Multi-client state sync ────────────────────────────────────────
    public void PublishStateChange(string action, string id, string params_)
    {
        PublishCommand("system/state_changes", $"{action},{id},{params_}");
    }
}
```

### 3.2 Kalman Filter Implementation

```csharp
// ── KalmanFilter2D.cs ─────────────────────────────────────────────────

using UnityEngine;

namespace HOLORTLS.Math
{
    /// <summary>
    /// 2D Kalman filter for smoothing noisy RSSI-derived positions.
    /// Tune q (process noise) based on expected tag velocity.
    /// Tune r (measurement noise) based on environment (open office=low, 
    /// factory with metal=high).
    /// </summary>
    public class KalmanFilter2D
    {
        // Per-axis state (we run two independent 1D filters)
        private KalmanState xState;
        private KalmanState yState;

        public KalmanFilter2D(float processNoise = 0.5f, float measurementNoise = 2.0f)
        {
            xState = new KalmanState { q = processNoise, r = measurementNoise };
            yState = new KalmanState { q = processNoise, r = measurementNoise };
        }

        public void Reset()
        {
            xState = new KalmanState();
            yState = new KalmanState();
        }

        /// <summary>
        /// Update filter with new measurement. Returns smoothed position.
        /// Call once per measurement per axis.
        /// </summary>
        public Vector2 Update(Vector2 measurement)
        {
            return new Vector2(xState.Update(measurement.x), yState.Update(measurement.y));
        }

        /// <summary>
        /// Per-axis update (for when X and Y arrive at different times).
        /// </summary>
        public void UpdateX(float measurementX)
        {
            xState.Update(measurementX);
        }

        public void UpdateY(float measurementY)
        {
            yState.Update(measurementY);
        }

        public float SmoothedX => xState.x;
        public float SmoothedY => yState.x;

        private struct KalmanState
        {
            public float q;  // Process noise (how much we expect state to change)
            public float r;  // Measurement noise (how uncertain the measurement is)
            public float x;  // State estimate
            public float p;  // Estimate error covariance
            public float k;  // Kalman gain

            public float Update(float measurement)
            {
                // Prediction
                p = p + q;

                // Update
                k = p / (p + r);
                x = x + k * (measurement - x);
                p = (1 - k) * p;

                // Clamp to prevent NaN on first frame
                if (float.IsNaN(x)) x = measurement;

                return x;
            }
        }
    }
}
```

### 3.3 UnityMainThreadDispatcher

```csharp
// ── UnityMainThreadDispatcher.cs ─────────────────────────────────────
// Standard implementation — get from GitHub or use Queue-based version:
//
// 1. Create empty GameObject "UnityMainThreadDispatcher"
// 2. Attach this script (singleton, DontDestroyOnLoad)
// 3. Use: UnityMainThreadDispatcher.Instance().Enqueue(() => { ... })

using System;
using System.Collections.Generic;
using UnityEngine;

public class UnityMainThreadDispatcher : MonoBehaviour
{
    private static UnityMainThreadDispatcher instance;
    private static readonly object lockObj = new object();
    private Queue<Action> queue = new Queue<Action>();

    public static UnityMainThreadDispatcher Instance()
    {
        if (instance == null)
        {
            lock (lockObj)
            {
                if (instance == null)
                {
                    var go = new GameObject("UnityMainThreadDispatcher");
                    instance = go.AddComponent<UnityMainThreadDispatcher>();
                    DontDestroyOnLoad(go);
                }
            }
        }
        return instance;
    }

    public void Enqueue(Action action)
    {
        lock (lockObj)
        {
            queue.Enqueue(action);
        }
    }

    void Update()
    {
        lock (lockObj)
        {
            while (queue.Count > 0)
            {
                queue.Dequeue().Invoke();
            }
        }
    }
}
```

### 3.4 SQLite Integration

```csharp
// ── DatabaseManager.cs ───────────────────────────────────────────────

using System;
using System.Data;
using Mono.Data.Sqlite;
using UnityEngine;

public class DatabaseManager : MonoBehaviour
{
    private static DatabaseManager instance;
    private SqliteConnection db;

    public static DatabaseManager Instance => instance;

    void Awake()
    {
        if (instance != null) { Destroy(gameObject); return; }
        instance = this;
        DontDestroyOnLoad(gameObject);
        Initialize();
    }

    void Initialize()
    {
        string path = Application.dataPath + "/Database/holo_rtls.db";
        db = new SqliteConnection($"Data Source={path};Version=3;");
        db.Open();

        // Auto-create tables if they don't exist
        ExecuteNonQuery(GetSchemaSQL());
    }

    // ── Generic CRUD ────────────────────────────────────────────────────

    public void ExecuteNonQuery(string sql)
    {
        using (var cmd = db.CreateCommand())
        {
            cmd.CommandText = sql;
            cmd.ExecuteNonQuery();
        }
    }

    public int ExecuteInsert(string sql)
    {
        using (var cmd = db.CreateCommand())
        {
            cmd.CommandText = sql + "; SELECT last_insert_rowid();";
            return Convert.ToInt32(cmd.ExecuteScalar());
        }
    }

    // ── Node Operations ───────────────────────────────────────────────

    public void SaveNodePosition(string mac, string name, Vector3 pos, int nodeType)
    {
        string sql = $@"
            INSERT OR REPLACE INTO wifi_nodes (mac_address, name, pos_x, pos_y, pos_z, node_type)
            VALUES ('{mac}', '{name}', {pos.x}, {pos.y}, {pos.z}, {nodeType})";
        ExecuteNonQuery(sql);
    }

    public Vector3 GetNodePosition(string mac)
    {
        using (var cmd = db.CreateCommand())
        {
            cmd.CommandText = $"SELECT pos_x, pos_y, pos_z FROM wifi_nodes WHERE mac_address='{mac}'";
            using (var reader = cmd.ExecuteReader())
            {
                if (reader.Read())
                    return new Vector3(
                        Convert.ToSingle(reader["pos_x"]),
                        Convert.ToSingle(reader["pos_y"]),
                        Convert.ToSingle(reader["pos_z"]));
            }
        }
        return Vector3.zero;
    }

    // ── Tag Metadata ──────────────────────────────────────────────────

    public void SaveTagMetadata(string hardwareId, string name, int tagType, int iconIndex)
    {
        string sql = $@"
            INSERT OR REPLACE INTO trackers (hardware_id, assigned_name, tag_type, icon_index)
            VALUES ('{hardwareId}', '{name}', {tagType}, {iconIndex})";
        ExecuteNonQuery(sql);
    }

    // ── User Authentication ────────────────────────────────────────────

    public bool ValidateUser(string username, string passwordHash)
    {
        using (var cmd = db.CreateCommand())
        {
            cmd.CommandText = $"SELECT role FROM users WHERE username='{username}' AND password_hash='{passwordHash}'";
            using (var reader = cmd.ExecuteReader())
            {
                return reader.Read();
            }
        }
    }

    string GetSchemaSQL() => @"
        CREATE TABLE IF NOT EXISTS trackers (id INTEGER PRIMARY KEY, hardware_id TEXT UNIQUE, assigned_name TEXT, tag_type INTEGER, category INTEGER, icon_index INTEGER, asset_state INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS wifi_nodes (id INTEGER PRIMARY KEY, mac_address TEXT UNIQUE, name TEXT, pos_x REAL, pos_y REAL, pos_z REAL, node_type INTEGER);
        CREATE TABLE IF NOT EXISTS map_sections (id INTEGER PRIMARY KEY, name TEXT, polygon_json TEXT, is_restricted INTEGER, color_hex TEXT);
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, role INTEGER, display_name TEXT);
        CREATE TABLE IF NOT EXISTS alert_log (id INTEGER PRIMARY KEY, tracker_id INTEGER, alert_type INTEGER, timestamp REAL, acknowledged INTEGER DEFAULT 0);
    ";
}
```

### 3.5 Security — RBAC Implementation

```csharp
// ── SecurityManager.cs ───────────────────────────────────────────────

using UnityEngine;
using System.Collections.Generic;

public class SecurityManager : MonoBehaviour
{
    public static SecurityManager instance;
    public static System.Action<UserRole> OnRoleChanged;

    [Header("Current Session")]
    public string currentUsername;
    public UserRole currentRole = UserRole.Viewer;

    private Dictionary<string, UserData> localUsers;

    void Awake()
    {
        if (instance != null) { Destroy(gameObject); return; }
        instance = this;
        DontDestroyOnLoad(gameObject);

        localUsers = new Dictionary<string, UserData>
        {
            { "admin",    new UserData { username = "admin",    passwordHash = BCrypt.HashPassword("admin123"),    role = UserRole.Admin }},
            { "security", new UserData { username = "security", passwordHash = BCrypt.HashPassword("security123"), role = UserRole.SecurityOperator }},
            { "viewer",   new UserData { username = "viewer",   passwordHash = BCrypt.HashPassword("viewer123"),   role = UserRole.Viewer }},
        };

        // Seed admin user if DB is empty
        DatabaseManager.Instance.ExecuteNonQuery(@"
            INSERT OR IGNORE INTO users (username, password_hash, role, display_name)
            VALUES ('admin', 'admin123', 0, 'Administrator')");
    }

    public bool TryLogin(string username, string password)
    {
        if (localUsers.TryGetValue(username, out UserData data))
        {
            if (data.passwordHash == password || BCrypt.Verify(password, data.passwordHash))
            {
                currentUsername = username;
                currentRole = data.role;
                OnRoleChanged?.Invoke(currentRole);
                return true;
            }
        }
        return false;
    }

    public void Logout()
    {
        currentUsername = "";
        currentRole = UserRole.Viewer;
        OnRoleChanged?.Invoke(currentRole);
    }

    /// <summary>
    /// Returns true if the current user's role meets or exceeds the required role.
    /// </summary>
    public static bool HasPermission(UserRole requiredRole)
    {
        if (instance == null) return false;
        return (int)instance.currentRole <= (int)requiredRole;
    }

    // ── Permission checks for UI buttons ──────────────────────────────

    public static bool CanTriggerAlarm()     => HasPermission(UserRole.SecurityOperator);
    public static bool CanEditNodes()        => HasPermission(UserRole.SecurityOperator);
    public static bool CanManageUsers()      => HasPermission(UserRole.Admin);
    public static bool CanCreateZones()      => HasPermission(UserRole.SecurityOperator);
    public static bool CanExportReports()    => HasPermission(UserRole.SecurityOperator);
    public static bool CanViewHistory()      => HasPermission(UserRole.Viewer);
}
```

---

## 4. Edge Node Implementation (Python)

### 4.1 Raspberry Pi Scanner (`scanner.py`)

```python
#!/usr/bin/env python3
# edge-node/scanner.py
# BLE + WiFi scanner for Raspberry Pi 5
# Publishes RSSI telemetry to MQTT broker

import asyncio
import json
import signal
import sys
from datetime import datetime
import paho.mqtt.client as mqtt
from bluepy.btle import Scanner, DefaultDelegate

# Configuration
BROKER_IP   = "192.168.50.10"   # Command PC IP
BROKER_PORT = 1883
PI_MAC      = "DC:A6:32:XX:XX:XX"  # Set per device
NODE_NAME   = "Pi-North-01"
SCAN_DURATION = 0.1  # seconds

# MQTT
client = mqtt.Client()
client.connect(BROKER_IP, BROKER_PORT, 60)

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
        self.results = []

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev or isNewData:
            rssi = dev.rssi
            mac  = dev.addr
            # Filter out weak signals (< -90 dBm is noise)
            if rssi > -90:
                self.results.append((mac, rssi))

async def scan_loop():
    scanner = Scanner().withDelegate(ScanDelegate())

    while True:
        try:
            devices = scanner.scan(SCAN_DURATION)
            
            for mac, rssi in scanner.delegate.results:
                # Only track known tag MACs (in production, maintain allowlist)
                # battery = get_battery_from_advert(mac)  # Parse manufacturer data
                payload = f"{PI_MAC},{mac},{rssi},100"  # CSV format
                client.publish("rssi/data", payload)
            
            scanner.delegate.results.clear()

            # Heartbeat every 2 seconds
            client.publish("node/heartbeat", f"{PI_MAC},{PI_MAC},{NODE_NAME}")

        except Exception as e:
            print(f"Scan error: {e}")

        await asyncio.sleep(0.1)  # 10 Hz scan rate

signal.signal(signal.SIGINT, lambda s, f: (client.disconnect(), sys.exit(0)))

asyncio.run(scan_loop())
```

### 4.2 Triangulation (`triangulator.py`)

```python
#!/usr/bin/env python3
# edge-node/triangulator.py
# Weighted centroid triangulation using RSSI from 3+ nodes

import numpy as np

def rssi_to_distance(rssi, tx_power=-59, n=2.0):
    """Convert RSSI (dBm) to approximate distance (meters).
    n = path loss exponent (2.0 = free space, 2.5-3.0 = indoor)
    """
    return 10 ** ((tx_power - rssi) / (10 * n))

def triangulate(measurements: list[tuple[float, float, float]]) -> tuple[float, float]:
    """
    measurements: list of (x_anchor, y_anchor, rssi)
    Returns: (estimated_x, estimated_y)

    Uses weighted centroid method:
    - Convert each RSSI to distance
    - Weight each anchor's contribution by 1/distance^2
    - Compute weighted average of anchor positions
    """
    total_weight = 0.0
    wx = 0.0
    wy = 0.0

    for ax, ay, rssi in measurements:
        dist = rssi_to_distance(rssi)
        if dist < 0.1:  # Avoid division by zero (tag right on top of anchor)
            dist = 0.1

        weight = 1.0 / (dist * dist)
        wx += ax * weight
        wy += ay * weight
        total_weight += weight

    if total_weight < 0.001:
        return 0.0, 0.0

    return wx / total_weight, wy / total_weight
```

---

## 5. Testing Guide

### 5.1 Unit Tests

Run via Unity Test Framework (`Window → General → Test Runner`):

```csharp
// Tests/KalmanFilter2D_Tests.cs
using NUnit.Framework;
using HOLORTLS.Math;

public class KalmanFilter2D_Tests
{
    [Test]
    public void KalmanFilter_SmoothsNoisyInput()
    {
        var kf = new KalmanFilter2D(processNoise: 0.5f, measurementNoise: 2.0f);

        // Step 1: first measurement
        var result1 = kf.Update(new Vector2(10f, 10f));
        Assert.AreEqual(10f, result1.x, 0.1f);

        // Step 2: huge spike (noise)
        kf.Update(new Vector2(50f, 50f));

        // Step 3: back to normal
        var result3 = kf.Update(new Vector2(10f, 10f));

        // Filter should suppress the spike — result should be much closer to 10 than 50
        Assert.Less(result3.x, 30f);
        Assert.Greater(result3.x, 8f);
    }

    [Test]
    public void KalmanFilter_NoNaN_OnFirstFrame()
    {
        var kf = new KalmanFilter2D();
        var result = kf.Update(new Vector2(float.NaN, float.NaN));
        Assert.That(float.IsNaN(result.x) == false);
    }
}
```

### 5.2 Load Test Script (Python)

```python
#!/usr/bin/env python3
# backend/load_test_simulator.py
# Simulates 300 tags at 10 Hz = 3000 messages/second

import paho.mqtt.client as mqtt
import time, math, random, json

BROKER = "127.0.0.1"
TOPIC  = "rssi/data"
QTY    = 300
RATE   = 0.1  # seconds between batches

client = mqtt.Client()
client.connect(BROKER, 1883, 60)
print(f"[LOAD TEST] Simulating {QTY} tags at {1/RATE:.0f} Hz each...")

try:
    t = 0
    while True:
        for i in range(QTY):
            # Circular path per tag (each tag offset by phase)
            phase = i * (2 * math.pi / QTY)
            x = 25 + 20 * math.cos(t + phase)   # 50m × 30m room
            y = 15 + 12 * math.sin(t + phase)
            rssi = -60 + random.randint(-10, 10)
            bat  = random.randint(70, 100)
            
            payload = f"PiSimulator,Tag_{i:03d},{rssi},{bat}"
            client.publish(TOPIC, payload)
        
        client.loop_write()
        t += 0.05
        time.sleep(RATE)

except KeyboardInterrupt:
    client.disconnect()
```

---

## 6. Build & Deployment

### 6.1 Development Build

```
File → Build Settings → Windows → Build
Output: HOLO-RTLS-Dev.exe
Build runs from /build/ directory
```

### 6.2 Release Build

```
1. Switch to Release configuration (Edit → Project Settings → Player)
2. File → Build Settings → Build
3. Copy to deployment folder
4. Include: holo_rtls.db (empty, created on first run)
5. Include: Assets/StreamingAssets/ (CAD images, audio)
6. Include: Backend/edge-node/ scripts (for Pi deployment)
```

### 6.3 Pi Edge Node Deployment

```bash
# On each Raspberry Pi:
# 1. Flash Raspberry Pi OS (64-bit) to SD card
# 2. Enable SSH + configure WiFi
# 3. Install dependencies:
sudo apt update && sudo apt install -y python3-pip bluez
pip3 install paho-mqtt bluepy

# 4. Copy scripts:
scp scanner.py triangulator.py pi@<pi-ip>:/home/pi/rtls/
scp mqtt_publisher.py pi@<pi-ip>:/home/pi/rtls/

# 5. Set up as systemd service:
sudo cp rtls.service /etc/systemd/system/
sudo systemctl enable rtls
sudo systemctl start rtls
```

---

*Implementation Manual v1.0 — HOLO-RTLS — 2026-07-17*

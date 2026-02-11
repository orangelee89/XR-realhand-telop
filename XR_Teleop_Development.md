# XR Teleop ROS2 Development Documentation

> LinkerHand O6 Dual Hand VR Teleoperation System

---

## Development Goal

Receive hand tracking data from Android XR (Samsung Galaxy XR) and control dual LinkerHand O6 dexterous hands via ROS2.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Android XR Device                                   │
│                     (Samsung Galaxy XR / Emulator)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  TeleopXR App                                                        │   │
│  │  - Hand Tracking (26 joints per hand)                               │   │
│  │  - Convert to O6 values [0-255] x 6                                 │   │
│  │  - Send via UDP                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ UDP (port 5000)
                                    │ JSON: {"type":"hand_pose", "hand":"left/right", "o6_values":[...]}
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ROS2 System (Docker)                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  teleop_receiver node                                                │   │
│  │  - Listen UDP port 5000                                             │   │
│  │  - Parse JSON data                                                   │   │
│  │  - Publish to ROS2 topics                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                 │                                     │                     │
│                 │ /cb_left_hand_control_cmd          │ /cb_right_hand_control_cmd
│                 ▼                                     ▼                     │
│  ┌──────────────────────────┐         ┌──────────────────────────┐        │
│  │  linker_hand_sdk_left    │         │  linker_hand_sdk_right   │        │
│  │  - Subscribe topic       │         │  - Subscribe topic       │        │
│  │  - Send CAN commands     │         │  - Send CAN commands     │        │
│  └──────────────────────────┘         └──────────────────────────┘        │
│                 │                                     │                     │
└─────────────────┼─────────────────────────────────────┼─────────────────────┘
                  │ CAN0                                │ CAN1
                  ▼                                     ▼
        ┌─────────────────┐                   ┌─────────────────┐
        │  LinkerHand O6  │                   │  LinkerHand O6  │
        │   (Left Hand)   │                   │  (Right Hand)   │
        └─────────────────┘                   └─────────────────┘
```

---

## Components Developed

### 1. teleop_receiver Node

**File:** `linker_hand_ros2_sdk/linker_hand_ros2_sdk/teleop_receiver.py`

A ROS2 node that receives hand tracking data from Android XR via UDP and publishes control commands.

**Features:**
- UDP socket listening on configurable port (default: 5000)
- JSON parsing of hand pose data
- Supports left, right, or both hands
- Thread-safe asynchronous receiving
- Graceful shutdown handling

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `port` | int | 5000 | UDP listening port |
| `buffer_size` | int | 1024 | UDP buffer size |
| `hand_type` | string | "left" | "left", "right", or "both" |

**Published Topics:**
| Topic | Message Type | Description |
|-------|--------------|-------------|
| `/cb_left_hand_control_cmd` | sensor_msgs/JointState | Left hand O6 control values |
| `/cb_right_hand_control_cmd` | sensor_msgs/JointState | Right hand O6 control values |
| `/teleop_raw_data` | std_msgs/String | Raw JSON data for debugging |

**Expected UDP Data Format:**
```json
{
    "type": "hand_pose",
    "hand": "left",
    "timestamp": 1234567890123,
    "o6_values": [0, 128, 255, 200, 150, 100]
}
```

**O6 Values Mapping:**
| Index | Finger | Range | Description |
|-------|--------|-------|-------------|
| 0 | Thumb | 0-255 | Thumb bend angle |
| 1 | Index | 0-255 | Index finger bend |
| 2 | Middle | 0-255 | Middle finger bend |
| 3 | Ring | 0-255 | Ring finger bend |
| 4 | Little | 0-255 | Little finger bend |
| 5 | Thumb Rotation | 0-255 | Thumb lateral movement |

---

### 2. VR_teleop.launch.py

**File:** `linker_hand_ros2_sdk/launch/VR_teleop.launch.py`

Combined launch file that starts all nodes required for VR teleoperation.

**Nodes Launched:**
1. `linker_hand_sdk_left` - Left hand driver (can0)
2. `linker_hand_sdk_right` - Right hand driver (can1)
3. `teleop_receiver` - UDP receiver (delayed 3 seconds)

**Configuration:**
```python
# Left hand
parameters=[{
    'hand_type': 'left',
    'hand_joint': "O6",
    'is_touch': False,
    'can': 'can0',
    "modbus": "None"
}]

# Right hand
parameters=[{
    'hand_type': 'right',
    'hand_joint': "O6",
    'is_touch': False,
    'can': 'can1',
    "modbus": "None"
}]

# Teleop receiver
parameters=[{
    'port': 5000,
    'hand_type': 'both',
    'hand_joint': 'O6',
}]
```

---

### 3. linker_hand_double.launch.py

**File:** `linker_hand_ros2_sdk/launch/linker_hand_double.launch.py`

Launch file for dual hand hardware initialization without teleop.

**Changes:**
- Configured left hand to use can0
- Configured right hand to use can1
- Set hand type to O6

---

### 4. start_dual_hands.sh

**File:** `/home/yuxia/linker_hand_ros2_sdk/start_dual_hands.sh`

Shell script for complete system setup including:
- CAN interface setup (can0, can1)
- Docker container management
- User instructions

---

### 5. GUI Control

**File:** `gui_control/launch/gui_control.launch.py`

Optional GUI for manual hand control and monitoring.

**Changes:**
- Added dual hand GUI control support
- Configured left and right hand node parameters

**Launch:** `ros2 launch gui_control gui_control.launch.py`

---

### 6. Registered teleop_receiver Entry Point

**File:** `linker_hand_ros2_sdk/setup.py`

```python
entry_points={
    'console_scripts': [
        'linker_hand_sdk = linker_hand_ros2_sdk.linker_hand:main',
        'teleop_receiver = linker_hand_ros2_sdk.teleop_receiver:main',
        # ... other executables
    ],
}
```

---

## Quick Start Guide

### Prerequisites
- Docker with `realhand` container
- Two CAN adapters connected
- Network access to Android XR device

### Step 1: Setup CAN Interfaces
```bash
cd ~/linker_hand_ros2_sdk
./start_dual_hands.sh
```

### Step 2: Inside Docker Container
```bash
# Source workspace
cd /root/linker_hand_ros2_sdk
source install/setup.bash

# Launch VR teleop (combined)
ros2 launch linker_hand_ros2_sdk VR_teleop.launch.py
```

### Step 3: Start Android XR App
1. Launch TeleopXR app on Samsung Galaxy XR
2. Ensure device is on same network
3. Configure target IP and port (5000)
4. Start hand tracking

### Step 4: Optional - GUI Control
```bash
# In another terminal
docker exec -it realhand bash
cd /root/linker_hand_ros2_sdk && source install/setup.bash
ros2 launch gui_control gui_control.launch.py
```

---

## ROS2 Topic Structure

```
/cb_left_hand_control_cmd    [sensor_msgs/JointState]  <- teleop_receiver publishes
        |
        └──► linker_hand_sdk_left subscribes -> CAN0 -> Left Hand

/cb_right_hand_control_cmd   [sensor_msgs/JointState]  <- teleop_receiver publishes
        |
        └──► linker_hand_sdk_right subscribes -> CAN1 -> Right Hand

/teleop_raw_data             [std_msgs/String]         <- Debug topic
```

---

## Debugging

### Check Topics
```bash
# List all topics
ros2 topic list

# Monitor left hand commands
ros2 topic echo /cb_left_hand_control_cmd

# Monitor right hand commands
ros2 topic echo /cb_right_hand_control_cmd

# Monitor raw UDP data
ros2 topic echo /teleop_raw_data
```

### Check Node Status
```bash
ros2 node list
ros2 node info /teleop_receiver
```

### Test UDP Connection
```bash
# Send test data from another terminal
echo '{"type":"hand_pose","hand":"left","o6_values":[128,128,128,128,128,128]}' | nc -u localhost 5000
```

---

## File Structure

```
linker_hand_ros2_sdk/
├── launch/
│   ├── VR_teleop.launch.py          # Combined VR teleop launch
│   ├── linker_hand_double.launch.py # Dual hand hardware only
│   └── linker_hand.launch.py        # Single hand launch
├── linker_hand_ros2_sdk/
│   ├── teleop_receiver.py           # UDP receiver node
│   ├── linker_hand.py               # Main hand driver
│   └── LinkerHand/                  # LinkerHand API
├── setup.py                         # Package setup with entry points
└── package.xml
```

---

## New Files

| File | Type | Description |
|-----|------|------|
| `teleop_receiver.py` | New | UDP receiver node |
| `VR_teleop.launch.py` | New | Combined launch file |
| `start_dual_hands.sh` | New | System startup script |

## Modified Files

| File | Changes |
|-----|---------|
| `setup.py` | Added teleop_receiver entry point |
| `linker_hand_double.launch.py` | Configured dual hand CAN |
| `gui_control.launch.py` | Added dual hand support |

---

## Docker Commands

```bash
# Start container
docker start realhand

# Enter container
docker exec -it realhand bash

# Open additional terminal
docker exec -it realhand bash

# Check container status
docker ps | grep realhand
```

---

## Network Configuration

| Component | IP | Port | Protocol |
|-----------|----|----|----------|
| ROS2 Host | 0.0.0.0 (all interfaces) | 5000 | UDP |
| Android XR | (device IP) | - | UDP client |

**Firewall:** Ensure port 5000 is open for UDP traffic.

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-02 | 1.0 | Initial VR teleop implementation |
| | | - teleop_receiver node |
| | | - VR_teleop.launch.py |
| | | - Dual hand support |
| | | - GUI control integration |

---

## References

- [LinkerHand ROS2 SDK](https://github.com/linker-bot/linkerhand-ros2-sdk)
- [TeleopXR Android App](https://github.com/orangelee89/XR-realhand-telop)
- [Android XR Hand Tracking](https://developer.android.com/develop/xr/jetpack-xr-sdk/arcore/hands)

---

*Documentation updated: 2026-02*

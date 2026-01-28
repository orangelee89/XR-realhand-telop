# TeleopXR - LinkerHand Teleoperation System

## Overview

This system enables teleoperation of LinkerHand O6 dexterous hand using Android XR (Samsung Galaxy XR) hand tracking.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Samsung Galaxy XR                            │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ Android XR SDK  │ -> │ HandPoseConverter│ -> │ HandDataSender│  │
│  │ (26 joints)     │    │ (26 -> 6 values) │    │ (UDP sender)  │  │
│  └─────────────────┘    └──────────────────┘    └───────┬───────┘  │
└─────────────────────────────────────────────────────────┼──────────┘
                                                          │
                                          UDP (port 5000) │
                                                          │
┌─────────────────────────────────────────────────────────┼──────────┐
│                        Ubuntu Computer                  │          │
│  ┌───────────────┐    ┌─────────────────────┐          │          │
│  │teleop_receiver│ <- │ UDP socket (5000)   │ <────────┘          │
│  │ (ROS2 node)   │    └─────────────────────┘                     │
│  └───────┬───────┘                                                │
│          │                                                        │
│          │ /cb_left_hand_control_cmd                              │
│          ▼                                                        │
│  ┌───────────────┐    ┌─────────────────────┐                     │
│  │linker_hand_sdk│ -> │ CAN bus (can0)      │ -> LinkerHand O6    │
│  │ (ROS2 node)   │    └─────────────────────┘                     │
│  └───────────────┘                                                │
└───────────────────────────────────────────────────────────────────┘
```

## Files Created/Modified

### TeleopXR (Android) - New Files

| File | Description |
|------|-------------|
| `app/src/main/java/com/example/teleop/hand/HandPoseConverter.kt` | Converts 26 Android XR joints to 6 O6 control values |
| `app/src/main/java/com/example/teleop/hand/HandDataSender.kt` | Sends hand data via UDP to ROS2 |
| `app/src/main/java/com/example/teleop/hand/TeleopManager.kt` | Main controller integrating converter and sender |

### TeleopXR (Android) - Modified Files

| File | Changes |
|------|---------|
| `app/src/main/java/com/example/teleop/TeleopViewModel.kt` | Added TeleopManager integration |
| `app/src/main/AndroidManifest.xml` | Added INTERNET permission |

### LinkerHand ROS2 SDK - New Files

| File | Description |
|------|-------------|
| `linker_hand_ros2_sdk/teleop_receiver.py` | ROS2 node that receives UDP and publishes to hand topics |
| `linker_hand_ros2_sdk/launch/teleop_receiver.launch.py` | Launch file for teleop system |

### LinkerHand ROS2 SDK - Modified Files

| File | Changes |
|------|---------|
| `linker_hand_ros2_sdk/setup.py` | Added teleop_receiver entry point |

## Usage

### Step 1: Configure IP Address

Edit `TeleopViewModel.kt` and set your Ubuntu computer's IP:

```kotlin
private var targetHost = "192.168.1.100"  // Change this
private var targetPort = 5000
```

Or use the API:
```kotlin
teleopViewModel.setTargetHost("192.168.1.100")
```

### Step 2: Start ROS2 Nodes (Ubuntu)

```bash
# Terminal 1: Build and source
cd ~/linker_hand_ros2_sdk
colcon build --symlink-install
source install/setup.bash

# Start teleop receiver and LinkerHand SDK
ros2 launch linker_hand_ros2_sdk teleop_receiver.launch.py
```

Or run separately:
```bash
# Terminal 1: Teleop receiver
ros2 run linker_hand_ros2_sdk teleop_receiver --ros-args -p port:=5000

# Terminal 2: LinkerHand SDK
ros2 launch linker_hand_ros2_sdk linker_hand.launch.py
```

### Step 3: Run Android App

1. Build and install TeleopXR on Samsung Galaxy XR
2. Launch the app
3. Hand tracking will automatically start and send data

### Step 4: Verify Communication

```bash
# Check if data is being received
ros2 topic echo /teleop_raw_data

# Check hand control commands
ros2 topic echo /cb_left_hand_control_cmd
```

## O6 Control Mapping

| Index | O6 Joint | Android XR Source |
|-------|----------|-------------------|
| 0 | Thumb bend (大拇指弯曲) | THUMB joints distance to palm |
| 1 | Thumb yaw (大拇指横摆) | THUMB lateral position |
| 2 | Index bend (食指弯曲) | INDEX_TIP distance to palm |
| 3 | Middle bend (中指弯曲) | MIDDLE_TIP distance to palm |
| 4 | Ring bend (无名指弯曲) | RING_TIP distance to palm |
| 5 | Pinky bend (小指弯曲) | LITTLE_TIP distance to palm |

## Data Format (UDP JSON)

```json
{
  "type": "hand_pose",
  "hand": "left",
  "timestamp": 1706345123456,
  "o6_values": [128, 64, 200, 180, 150, 100],
  "finger_bend": [0.5, 0.25, 0.78, 0.71, 0.59, 0.39]
}
```

## Troubleshooting

### No data received
1. Check firewall: `sudo ufw allow 5000/udp`
2. Verify IP address is correct
3. Check both devices are on same network

### Hand not moving
1. Verify LinkerHand SDK is running and connected to O6
2. Check CAN connection: `ip link show can0`
3. Check topic publishing: `ros2 topic hz /cb_left_hand_control_cmd`

### Latency issues
- UDP should have ~5-15ms latency on local WiFi
- If higher, check WiFi signal strength
- Consider using 5GHz WiFi band

## Notes

- Head tracking uses left eye pose as workaround (SDK bug)
- O6 has 6 active + 5 passive DoF, we control the 6 active ones
- Send rate is ~30 Hz (configurable in HandDataSender.kt)

# TeleopXR Development Documentation

## Project Overview

A hand teleoperation system based on Samsung Galaxy XR that tracks user hand gestures through a VR headset and controls the LinkerHand O6 robotic hand in real-time.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Samsung Galaxy XR                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      TeleopXR App (Kotlin)                        │   │
│  │                                                                    │   │
│  │   Android XR SDK                                                   │   │
│  │        │                                                           │   │
│  │        ▼ 26 Hand Joint 3D Coordinates                              │   │
│  │   HandPoseConverter                                                │   │
│  │        │ Palm-to-Fingertip Distance Calculation                    │   │
│  │        ▼ 6 O6 Control Values (0-255)                               │   │
│  │   HandDataSender ──────── UDP (JSON) ──────────┐                   │   │
│  │        @ 30Hz                                   │                   │   │
│  └─────────────────────────────────────────────────│──────────────────┘   │
└────────────────────────────────────────────────────│──────────────────────┘
                                                     │
                                                     ▼ Port 5000
┌─────────────────────────────────────────────────────────────────────────┐
│                         Ubuntu Computer                                  │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                  teleop_receiver.py (ROS2 Node)                   │   │
│  │                           │                                        │   │
│  │                           ▼                                        │   │
│  │              /cb_left_hand_control_cmd                             │   │
│  │              /cb_right_hand_control_cmd                            │   │
│  │                           │                                        │   │
│  │                           ▼                                        │   │
│  │                  linker_hand_ros2_sdk                              │   │
│  │                           │                                        │   │
│  │                           ▼                                        │   │
│  │                    LinkerHand O6                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Modules

### 1. TeleopXR App (Android)

| File | Description |
|------|-------------|
| `MainActivity.kt` | UI entry point, configures hand tracking |
| `TeleopViewModel.kt` | Collects hand data, manages connection state |
| `HandPoseConverter.kt` | Converts 26 joints → 6 O6 values |
| `HandDataSender.kt` | UDP network transmission |
| `TeleopManager.kt` | Integrates converter and sender |

### 2. ROS2 Side (Python)

| File | Description |
|------|-------------|
| `teleop_receiver.py` | Receives UDP, publishes to ROS2 topics |
| `linker_hand_*.py` | LinkerHand SDK drivers |

## Hand Gesture Conversion Algorithm

### Input
Android XR SDK provides 26 hand joint 3D coordinates (Vector3)

### Output
6 O6 control values (0-255):
- `[0]` Thumb bend
- `[1]` Thumb yaw (lateral movement)
- `[2]` Index finger bend
- `[3]` Middle finger bend
- `[4]` Ring finger bend
- `[5]` Pinky finger bend

### Algorithm
```
finger_bend = (palm_to_tip_distance - MIN) / (MAX - MIN)

Far distance (~12cm)  = Extended → 1.0 → 255
Close distance (~6cm) = Fist     → 0.0 → 0
```

### Distance Thresholds (meters)
| Finger | MIN (Fist) | MAX (Extended) |
|--------|------------|----------------|
| Thumb | 0.05 | 0.10 |
| Index | 0.06 | 0.12 |
| Middle | 0.06 | 0.13 |
| Ring | 0.06 | 0.12 |
| Pinky | 0.05 | 0.10 |

## Data Format

UDP JSON payload:
```json
{
  "type": "hand_pose",
  "hand": "left",
  "timestamp": 1234567890123,
  "o6_values": [128, 64, 255, 200, 150, 100],
  "finger_bend": [0.5, 0.25, 1.0, 0.78, 0.59, 0.39]
}
```

## Usage

### VR Side
1. Install TeleopXR.apk on Samsung Galaxy XR
2. Modify IP address in `MainActivity.kt`
3. Launch the App

### Ubuntu Side
```bash
# Launch LinkerHand driver
ros2 launch linker_hand_ros2_sdk linker_hand.launch.py

# Launch teleop receiver
ros2 run linker_hand_ros2_sdk teleop_receiver --ros-args -p port:=5000
```

## Development Environment

- **VR Device**: Samsung Galaxy XR
- **Android SDK**: Android XR SDK (Jetpack XR)
- **Language**: Kotlin, Jetpack Compose
- **ROS Version**: ROS2 Humble
- **Robotic Hand**: LinkerHand O6

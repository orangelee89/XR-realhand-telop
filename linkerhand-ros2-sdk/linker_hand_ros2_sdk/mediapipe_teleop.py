#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mediapipe_teleop.py - Ubuntu Hand Tracking Teleoperation

Uses MediaPipe to track hand via webcam, sends UDP data to teleop_receiver

MediaPipe Hand Landmarks (21 points):
    0: WRIST
    1-4: THUMB (CMC, MCP, IP, TIP)
    5-8: INDEX (MCP, PIP, DIP, TIP)
    9-12: MIDDLE (MCP, PIP, DIP, TIP)
    13-16: RING (MCP, PIP, DIP, TIP)
    17-20: PINKY (MCP, PIP, DIP, TIP)

O6 Control Value Mapping (6 values):
    0: Thumb bend - thumb tip to palm distance
    1: Thumb yaw - thumb lateral position
    2: Index bend - index tip to palm distance
    3: Middle bend - middle tip to palm distance
    4: Ring bend - ring tip to palm distance
    5: Pinky bend - pinky tip to palm distance

Usage:
    python3 mediapipe_teleop.py [--host HOST] [--port PORT] [--camera CAMERA_ID]

Keys:
    q: Quit
    h: Switch left/right hand detection
    d: Show/hide debug info
"""

import cv2
import mediapipe as mp
import numpy as np
import socket
import json
import time
import argparse
import math


class MediaPipeTeleop:
    """MediaPipe-based hand tracking teleoperation"""

    # MediaPipe hand landmark indices
    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_MCP = 5
    INDEX_PIP = 6
    INDEX_DIP = 7
    INDEX_TIP = 8
    MIDDLE_MCP = 9
    MIDDLE_PIP = 10
    MIDDLE_DIP = 11
    MIDDLE_TIP = 12
    RING_MCP = 13
    RING_PIP = 14
    RING_DIP = 15
    RING_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20

    def __init__(self, host: str = "127.0.0.1", port: int = 5000, camera_id: int = 0):
        """
        Initialize

        Args:
            host: teleop_receiver IP address
            port: UDP port
            camera_id: Camera device ID
        """
        self.host = host
        self.port = port
        self.camera_id = camera_id

        # UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # MediaPipe hand detection
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.8,
            min_tracking_confidence=0.6
        )

        # State
        self.target_hand = "left"  # Target hand: left or right
        self.show_debug = True
        self.last_send_time = 0
        self.send_interval = 1.0 / 30  # 30 Hz

        # Smoothing filter
        self.smoothing = 0.15  # EMA factor (0-1, lower = more smooth)
        self.deadzone = 8  # Ignore changes smaller than this (0-255)
        self.max_velocity = 30  # Max change per frame (velocity limit)
        self.prev_values = None  # Previous filtered values

        print(f"MediaPipe Teleop Initialized")
        print(f"  Target: {host}:{port}")
        print(f"  Camera: /dev/video{camera_id}")
        print(f"  Hand: {self.target_hand}")

    def calculate_distance(self, p1, p2) -> float:
        """Calculate 3D distance between two points"""
        return math.sqrt(
            (p1.x - p2.x) ** 2 +
            (p1.y - p2.y) ** 2 +
            (p1.z - p2.z) ** 2
        )

    def calculate_finger_bend(self, landmarks, tip_idx: int, mcp_idx: int, wrist_idx: int = 0) -> float:
        """
        Calculate finger bend using tip to wrist distance ratio
        Simple and robust
        """
        tip = landmarks[tip_idx]
        mcp = landmarks[mcp_idx]
        wrist = landmarks[wrist_idx]

        # Distance from tip to wrist
        tip_to_wrist = self.calculate_distance(tip, wrist)

        # Distance from MCP to wrist (reference)
        mcp_to_wrist = self.calculate_distance(mcp, wrist)

        if mcp_to_wrist < 0.01:
            return 0.5

        # Ratio: higher = finger extended, lower = finger bent
        ratio = tip_to_wrist / mcp_to_wrist

        # Map: ratio 2.0 = open (0.0), ratio 0.8 = bent (1.0)
        bend = (2.0 - ratio) / 1.2

        return max(0.0, min(1.0, bend))

    def calculate_thumb_bend(self, landmarks) -> float:
        """Calculate thumb bend using tip to CMC distance ratio"""
        thumb_tip = landmarks[self.THUMB_TIP]
        thumb_cmc = landmarks[self.THUMB_CMC]
        index_mcp = landmarks[self.INDEX_MCP]
        wrist = landmarks[self.WRIST]

        # Distance from thumb tip to index MCP (reference for closed)
        tip_to_index = self.calculate_distance(thumb_tip, index_mcp)

        # Distance from CMC to wrist (reference length)
        cmc_to_wrist = self.calculate_distance(thumb_cmc, wrist)

        if cmc_to_wrist < 0.01:
            return 0.5

        # Ratio: smaller = thumb closer to palm = more bent
        ratio = tip_to_index / cmc_to_wrist

        # Map: ratio 2.0+ = open (0.0), ratio 0.5 = bent (1.0)
        bend = (2.0 - ratio) / 1.5

        return max(0.0, min(1.0, bend))

    def calculate_thumb_yaw(self, landmarks) -> float:
        """
        Calculate thumb yaw using angle between thumb direction and palm plane.

        This method is independent of palm orientation.

        - Thumb spread (pointing out): angle_to_plane ≈ 90° → yaw = 0 (open)
        - Thumb adducted (lying flat): angle_to_plane ≈ 0° → yaw = 1 (closed)
        """
        # Step 1: Build palm plane from MCP points
        mcp_points = np.array([
            [landmarks[self.INDEX_MCP].x, landmarks[self.INDEX_MCP].y, landmarks[self.INDEX_MCP].z],
            [landmarks[self.MIDDLE_MCP].x, landmarks[self.MIDDLE_MCP].y, landmarks[self.MIDDLE_MCP].z],
            [landmarks[self.RING_MCP].x, landmarks[self.RING_MCP].y, landmarks[self.RING_MCP].z],
            [landmarks[self.PINKY_MCP].x, landmarks[self.PINKY_MCP].y, landmarks[self.PINKY_MCP].z]
        ])

        # Use SVD to find plane normal
        centroid = np.mean(mcp_points, axis=0)
        centered = mcp_points - centroid
        _, _, vh = np.linalg.svd(centered)
        palm_normal = vh[2, :]

        # Ensure normal points outward
        wrist = np.array([landmarks[self.WRIST].x, landmarks[self.WRIST].y, landmarks[self.WRIST].z])
        middle_mcp = np.array([landmarks[self.MIDDLE_MCP].x, landmarks[self.MIDDLE_MCP].y, landmarks[self.MIDDLE_MCP].z])
        wrist_to_middle = middle_mcp - wrist
        if np.dot(palm_normal, wrist_to_middle) < 0:
            palm_normal = -palm_normal

        # Step 2: Thumb direction: CMC → TIP
        thumb_cmc = np.array([landmarks[self.THUMB_CMC].x, landmarks[self.THUMB_CMC].y, landmarks[self.THUMB_CMC].z])
        thumb_tip = np.array([landmarks[self.THUMB_TIP].x, landmarks[self.THUMB_TIP].y, landmarks[self.THUMB_TIP].z])
        thumb_vec = thumb_tip - thumb_cmc
        thumb_vec = thumb_vec / (np.linalg.norm(thumb_vec) + 1e-6)

        # Step 3: Angle between thumb and palm normal
        cos_angle_to_normal = np.dot(thumb_vec, palm_normal)
        cos_angle_to_normal = np.clip(cos_angle_to_normal, -1.0, 1.0)
        angle_to_normal = np.degrees(np.arccos(np.abs(cos_angle_to_normal)))

        # Angle to palm plane = 90° - angle to normal
        angle_to_plane = 90 - angle_to_normal

        # Map: 90° (spread) → 0.0, 0° (adducted) → 1.0
        yaw_normalized = 1.0 - (angle_to_plane / 90.0)
        return max(0.0, min(1.0, yaw_normalized))

    def convert_to_o6(self, landmarks) -> list:
        """
        Convert MediaPipe hand landmarks to O6 control values

        Returns:
            [thumb_bend, thumb_yaw, index_bend, middle_bend, ring_bend, pinky_bend]
            Each value range 0-255
        """
        # Calculate finger bend amounts (0.0-1.0)
        thumb_bend = self.calculate_thumb_bend(landmarks)
        thumb_yaw = self.calculate_thumb_yaw(landmarks)
        index_bend = self.calculate_finger_bend(landmarks, self.INDEX_TIP, self.INDEX_MCP)
        middle_bend = self.calculate_finger_bend(landmarks, self.MIDDLE_TIP, self.MIDDLE_MCP)
        ring_bend = self.calculate_finger_bend(landmarks, self.RING_TIP, self.RING_MCP)
        pinky_bend = self.calculate_finger_bend(landmarks, self.PINKY_TIP, self.PINKY_MCP)

        finger_bends = [thumb_bend, thumb_yaw, index_bend, middle_bend, ring_bend, pinky_bend]

        # Debug: print raw bend values
        print(f"Raw: Th={thumb_bend:.2f} Yaw={thumb_yaw:.2f} I={index_bend:.2f} M={middle_bend:.2f} R={ring_bend:.2f} P={pinky_bend:.2f}")

        # Convert to O6 value ranges
        # Thumb bend: 102 (closed) to 250 (open)
        # Thumb yaw: 18 (closed) to 250 (open)
        # Other fingers: 0 (closed) to 255 (open)
        thumb_val = int(250 - (thumb_bend * 148))  # 250 -> 102
        thumb_yaw_val = int(250 - (thumb_yaw * 232))  # 250 -> 18
        index_val = 255 - int(index_bend * 255)
        middle_val = 255 - int(middle_bend * 255)
        ring_val = 255 - int(ring_bend * 255)
        pinky_val = 255 - int(pinky_bend * 255)

        o6_values = [thumb_val, thumb_yaw_val, index_val, middle_val, ring_val, pinky_val]

        # Apply smoothing filter
        o6_values = self.apply_filter(o6_values)

        return o6_values, finger_bends

    def apply_filter(self, values: list) -> list:
        """Apply EMA smoothing, deadzone, and velocity limit filter"""
        if self.prev_values is None:
            self.prev_values = values[:]
            return values

        filtered = []
        for i, (new_val, prev_val) in enumerate(zip(values, self.prev_values)):
            # EMA smoothing
            smoothed = int(self.smoothing * new_val + (1 - self.smoothing) * prev_val)

            # Velocity limit: prevent sudden jumps
            delta = smoothed - prev_val
            if abs(delta) > self.max_velocity:
                smoothed = prev_val + int(self.max_velocity * (1 if delta > 0 else -1))

            # Deadzone: only update if change is significant
            if abs(smoothed - prev_val) < self.deadzone:
                smoothed = prev_val

            # Clamp to valid range
            smoothed = max(0, min(255, smoothed))

            filtered.append(smoothed)
            self.prev_values[i] = smoothed

        return filtered

    def send_hand_data(self, hand_type: str, o6_values: list, finger_bends: list):
        """Send hand data to teleop_receiver"""
        current_time = time.time()

        # Rate limiting
        if current_time - self.last_send_time < self.send_interval:
            return

        self.last_send_time = current_time

        # Build JSON data (compatible with Android format)
        data = {
            "type": "hand_pose",
            "hand": hand_type,
            "timestamp": int(current_time * 1000),
            "o6_values": o6_values,
            "finger_bend": finger_bends
        }

        # Send UDP
        try:
            message = json.dumps(data).encode('utf-8')
            self.socket.sendto(message, (self.host, self.port))
        except Exception as e:
            print(f"Send failed: {e}")

    def run(self):
        """Run hand tracking"""
        cap = cv2.VideoCapture(self.camera_id)

        if not cap.isOpened():
            print(f"Error: Cannot open camera /dev/video{self.camera_id}")
            return

        # Set resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        print("\nStarting hand tracking...")
        print("Keys: q=quit, h=switch hand, d=toggle debug")
        print("-" * 50)

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Cannot read camera")
                break

            # No mirror flip, keep real left/right hand

            # BGR -> RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # MediaPipe hand detection
            results = self.hands.process(rgb_frame)

            # Process detection results
            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(
                    results.multi_hand_landmarks,
                    results.multi_handedness
                ):
                    # Get hand type (Left/Right)
                    # MediaPipe detects from camera view, so we flip it for user view
                    label = handedness.classification[0].label
                    hand_type = "right" if label == "Left" else "left"

                    # Only process target hand
                    if hand_type != self.target_hand:
                        continue

                    # Draw hand landmarks
                    self.mp_drawing.draw_landmarks(
                        frame,
                        hand_landmarks,
                        self.mp_hands.HAND_CONNECTIONS
                    )

                    # Convert to O6 values
                    landmarks = hand_landmarks.landmark
                    o6_values, finger_bends = self.convert_to_o6(landmarks)

                    # Send data (left hand -> left robot, right hand -> right robot)
                    self.send_hand_data(hand_type, o6_values, finger_bends)

                    # Show debug info
                    if self.show_debug:
                        # O6 values
                        y_offset = 30
                        labels = ["Thumb", "ThumbYaw", "Index", "Middle", "Ring", "Pinky"]
                        for i, (lbl, val) in enumerate(zip(labels, o6_values)):
                            text = f"{lbl}: {val}"
                            cv2.putText(frame, text, (10, y_offset + i * 25),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                        # Hand type
                        cv2.putText(frame, f"Hand: {hand_type}", (10, y_offset + 6 * 25),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

            # Show target settings
            cv2.putText(frame, f"Target: {self.target_hand} -> {self.host}:{self.port}",
                       (10, frame.shape[0] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Display frame
            cv2.imshow("MediaPipe Hand Tracking - O6 Teleop", frame)

            # Key handling
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Exiting...")
                break
            elif key == ord('h'):
                self.target_hand = "right" if self.target_hand == "left" else "left"
                print(f"Switched target hand: {self.target_hand}")
            elif key == ord('d'):
                self.show_debug = not self.show_debug
                print(f"Debug info: {'shown' if self.show_debug else 'hidden'}")

        # Cleanup
        cap.release()
        cv2.destroyAllWindows()
        self.socket.close()
        print("Exited")


def main():
    parser = argparse.ArgumentParser(description="MediaPipe Hand Tracking Teleoperation")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                       help="teleop_receiver IP address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000,
                       help="UDP port (default: 5000)")
    parser.add_argument("--camera", type=int, default=0,
                       help="Camera device ID (default: 0)")

    args = parser.parse_args()

    teleop = MediaPipeTeleop(
        host=args.host,
        port=args.port,
        camera_id=args.camera
    )

    teleop.run()


if __name__ == "__main__":
    main()

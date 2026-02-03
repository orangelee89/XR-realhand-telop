#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mediapipe_teleop_depth.py - Hand Tracking with RealSense Depth

Uses MediaPipe + Intel RealSense depth for accurate 3D hand tracking.
The real depth data improves yaw/rotation detection accuracy.

Usage:
    python3 mediapipe_teleop_depth.py [--host HOST] [--port PORT]
"""

import cv2
import mediapipe as mp
import numpy as np
import pyrealsense2 as rs
import socket
import json
import time
import argparse
import math


class RealSenseMediaPipeTeleop:
    """Hand tracking with RealSense depth + MediaPipe"""

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

    def __init__(self, host: str = "127.0.0.1", port: int = 5000):
        self.host = host
        self.port = port

        # UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # MediaPipe hand detection
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )

        # RealSense pipeline
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.align = None

        # State
        self.target_hand = "left"
        self.show_debug = True
        self.last_send_time = 0
        self.send_interval = 1.0 / 30

        # Smoothing filter
        self.smoothing = 0.15
        self.deadzone = 8
        self.max_velocity = 30
        self.prev_values = None

        print(f"RealSense + MediaPipe Teleop")
        print(f"  Target: {host}:{port}")
        print(f"  Hand: {self.target_hand}")

    def init_realsense(self):
        """Initialize RealSense camera"""
        try:
            # Enable RGB and Depth streams
            # L515 depth only supports 320x240
            self.config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            self.config.enable_stream(rs.stream.depth, 320, 240, rs.format.z16, 30)

            # Start pipeline
            profile = self.pipeline.start(self.config)

            # Create align object (align depth to color)
            self.align = rs.align(rs.stream.color)

            # Get depth scale
            depth_sensor = profile.get_device().first_depth_sensor()
            self.depth_scale = depth_sensor.get_depth_scale()

            print(f"RealSense initialized, depth scale: {self.depth_scale}")
            return True
        except Exception as e:
            print(f"RealSense init failed: {e}")
            return False

    def get_3d_landmarks(self, landmarks_2d, depth_frame, w, h):
        """Convert 2D landmarks to 3D using depth data"""
        landmarks_3d = []

        for lm in landmarks_2d:
            # Get pixel coordinates
            px = int(lm.x * w)
            py = int(lm.y * h)

            # Clamp to valid range
            px = max(0, min(w - 1, px))
            py = max(0, min(h - 1, py))

            # Get depth value (in meters)
            depth = depth_frame.get_distance(px, py)

            # If depth is invalid, use MediaPipe's estimated Z
            if depth <= 0 or depth > 2.0:
                depth = lm.z * 0.5 + 0.5  # Rough estimate

            landmarks_3d.append({
                'x': lm.x,
                'y': lm.y,
                'z': depth,  # Real depth in meters
                'px': px,
                'py': py
            })

        return landmarks_3d

    def calculate_distance_3d(self, p1, p2) -> float:
        """Calculate 3D distance between two points"""
        return math.sqrt(
            (p1['x'] - p2['x']) ** 2 +
            (p1['y'] - p2['y']) ** 2 +
            (p1['z'] - p2['z']) ** 2
        )

    def calculate_thumb_bend(self, lm3d) -> float:
        """Calculate thumb bend using distance ratio"""
        thumb_tip = lm3d[self.THUMB_TIP]
        thumb_cmc = lm3d[self.THUMB_CMC]
        index_mcp = lm3d[self.INDEX_MCP]
        wrist = lm3d[self.WRIST]

        tip_to_index = self.calculate_distance_3d(thumb_tip, index_mcp)
        cmc_to_wrist = self.calculate_distance_3d(thumb_cmc, wrist)

        if cmc_to_wrist < 0.001:
            return 0.5

        ratio = tip_to_index / cmc_to_wrist
        bend = (2.0 - ratio) / 1.5

        return max(0.0, min(1.0, bend))

    def calculate_thumb_yaw(self, lm3d) -> float:
        """
        Calculate thumb yaw using angle between thumb direction and palm plane.

        This method is independent of palm orientation.

        - Thumb spread (pointing out): angle_to_plane ≈ 90° → yaw = 0 (open)
        - Thumb adducted (lying flat): angle_to_plane ≈ 0° → yaw = 1 (closed)
        """
        # Step 1: Build palm plane from MCP points
        mcp_points = np.array([
            [lm3d[self.INDEX_MCP]['x'], lm3d[self.INDEX_MCP]['y'], lm3d[self.INDEX_MCP]['z']],
            [lm3d[self.MIDDLE_MCP]['x'], lm3d[self.MIDDLE_MCP]['y'], lm3d[self.MIDDLE_MCP]['z']],
            [lm3d[self.RING_MCP]['x'], lm3d[self.RING_MCP]['y'], lm3d[self.RING_MCP]['z']],
            [lm3d[self.PINKY_MCP]['x'], lm3d[self.PINKY_MCP]['y'], lm3d[self.PINKY_MCP]['z']]
        ])

        # Use SVD to find plane normal
        centroid = np.mean(mcp_points, axis=0)
        centered = mcp_points - centroid
        _, _, vh = np.linalg.svd(centered)
        palm_normal = vh[2, :]

        # Ensure normal points outward
        wrist = np.array([lm3d[self.WRIST]['x'], lm3d[self.WRIST]['y'], lm3d[self.WRIST]['z']])
        middle_mcp = np.array([lm3d[self.MIDDLE_MCP]['x'], lm3d[self.MIDDLE_MCP]['y'], lm3d[self.MIDDLE_MCP]['z']])
        wrist_to_middle = middle_mcp - wrist
        if np.dot(palm_normal, wrist_to_middle) < 0:
            palm_normal = -palm_normal

        # Step 2: Thumb direction: CMC → TIP
        thumb_cmc = np.array([lm3d[self.THUMB_CMC]['x'], lm3d[self.THUMB_CMC]['y'], lm3d[self.THUMB_CMC]['z']])
        thumb_tip = np.array([lm3d[self.THUMB_TIP]['x'], lm3d[self.THUMB_TIP]['y'], lm3d[self.THUMB_TIP]['z']])
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

    def calculate_finger_bend(self, lm3d, tip_idx: int, mcp_idx: int) -> float:
        """Calculate finger bend using distance ratio"""
        tip = lm3d[tip_idx]
        mcp = lm3d[mcp_idx]
        wrist = lm3d[self.WRIST]

        tip_to_wrist = self.calculate_distance_3d(tip, wrist)
        mcp_to_wrist = self.calculate_distance_3d(mcp, wrist)

        if mcp_to_wrist < 0.001:
            return 0.5

        ratio = tip_to_wrist / mcp_to_wrist
        bend = (2.0 - ratio) / 1.2

        return max(0.0, min(1.0, bend))

    def convert_to_o6(self, lm3d) -> list:
        """Convert 3D landmarks to O6 values"""
        thumb_bend = self.calculate_thumb_bend(lm3d)
        thumb_yaw = self.calculate_thumb_yaw(lm3d)
        index_bend = self.calculate_finger_bend(lm3d, self.INDEX_TIP, self.INDEX_MCP)
        middle_bend = self.calculate_finger_bend(lm3d, self.MIDDLE_TIP, self.MIDDLE_MCP)
        ring_bend = self.calculate_finger_bend(lm3d, self.RING_TIP, self.RING_MCP)
        pinky_bend = self.calculate_finger_bend(lm3d, self.PINKY_TIP, self.PINKY_MCP)

        finger_bends = [thumb_bend, thumb_yaw, index_bend, middle_bend, ring_bend, pinky_bend]

        # Debug output
        print(f"Raw: Th={thumb_bend:.2f} Yaw={thumb_yaw:.2f} I={index_bend:.2f} M={middle_bend:.2f} R={ring_bend:.2f} P={pinky_bend:.2f}")

        # Convert to O6 ranges
        thumb_val = int(250 - (thumb_bend * 148))
        thumb_yaw_val = int(250 - (thumb_yaw * 232))
        index_val = 255 - int(index_bend * 255)
        middle_val = 255 - int(middle_bend * 255)
        ring_val = 255 - int(ring_bend * 255)
        pinky_val = 255 - int(pinky_bend * 255)

        o6_values = [thumb_val, thumb_yaw_val, index_val, middle_val, ring_val, pinky_val]
        o6_values = self.apply_filter(o6_values)

        return o6_values, finger_bends

    def apply_filter(self, values: list) -> list:
        """Apply smoothing filter"""
        if self.prev_values is None:
            self.prev_values = values[:]
            return values

        filtered = []
        for i, (new_val, prev_val) in enumerate(zip(values, self.prev_values)):
            smoothed = int(self.smoothing * new_val + (1 - self.smoothing) * prev_val)

            delta = smoothed - prev_val
            if abs(delta) > self.max_velocity:
                smoothed = prev_val + int(self.max_velocity * (1 if delta > 0 else -1))

            if abs(smoothed - prev_val) < self.deadzone:
                smoothed = prev_val

            smoothed = max(0, min(255, smoothed))
            filtered.append(smoothed)
            self.prev_values[i] = smoothed

        return filtered

    def send_hand_data(self, hand_type: str, o6_values: list):
        """Send data via UDP"""
        current_time = time.time()
        if current_time - self.last_send_time < self.send_interval:
            return

        self.last_send_time = current_time

        data = {
            "type": "hand_pose",
            "hand": hand_type,
            "timestamp": int(current_time * 1000),
            "o6_values": o6_values
        }

        try:
            message = json.dumps(data).encode('utf-8')
            self.socket.sendto(message, (self.host, self.port))
        except Exception as e:
            print(f"Send failed: {e}")

    def run(self):
        """Main loop"""
        if not self.init_realsense():
            print("Failed to initialize RealSense")
            return

        print("\nStarting hand tracking with depth...")
        print("Keys: q=quit, h=switch hand, d=toggle debug")
        print("-" * 50)

        try:
            while True:
                # Get frames
                frames = self.pipeline.wait_for_frames()
                aligned_frames = self.align.process(frames)

                color_frame = aligned_frames.get_color_frame()
                depth_frame = aligned_frames.get_depth_frame()

                if not color_frame or not depth_frame:
                    continue

                # Convert to numpy
                color_image = np.asanyarray(color_frame.get_data())
                h, w = color_image.shape[:2]

                # MediaPipe detection
                rgb_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
                results = self.hands.process(rgb_image)

                if results.multi_hand_landmarks and results.multi_handedness:
                    for hand_landmarks, handedness in zip(
                        results.multi_hand_landmarks,
                        results.multi_handedness
                    ):
                        label = handedness.classification[0].label
                        hand_type = "right" if label == "Left" else "left"

                        if hand_type != self.target_hand:
                            continue

                        # Draw landmarks
                        self.mp_drawing.draw_landmarks(
                            color_image, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                        )

                        # Get 3D landmarks with real depth
                        lm3d = self.get_3d_landmarks(
                            hand_landmarks.landmark, depth_frame, w, h
                        )

                        # Convert to O6
                        o6_values, finger_bends = self.convert_to_o6(lm3d)

                        # Send
                        self.send_hand_data(hand_type, o6_values)

                        # Display
                        if self.show_debug:
                            y_offset = 30
                            labels = ["Thumb", "ThumbYaw", "Index", "Middle", "Ring", "Pinky"]
                            for i, (lbl, val) in enumerate(zip(labels, o6_values)):
                                cv2.putText(color_image, f"{lbl}: {val}",
                                           (10, y_offset + i * 25),
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                            # Show depth at wrist
                            wrist = lm3d[self.WRIST]
                            cv2.putText(color_image, f"Depth: {wrist['z']:.3f}m",
                                       (10, y_offset + 7 * 25),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

                cv2.putText(color_image, f"Target: {self.target_hand} (RealSense Depth)",
                           (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                cv2.imshow("RealSense + MediaPipe Hand Tracking", color_image)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('h'):
                    self.target_hand = "right" if self.target_hand == "left" else "left"
                    print(f"Switched to: {self.target_hand}")
                elif key == ord('d'):
                    self.show_debug = not self.show_debug

        finally:
            self.pipeline.stop()
            cv2.destroyAllWindows()
            self.socket.close()
            print("Exited")


def main():
    parser = argparse.ArgumentParser(description="RealSense + MediaPipe Hand Tracking")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)

    args = parser.parse_args()

    teleop = RealSenseMediaPipeTeleop(host=args.host, port=args.port)
    teleop.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dex_teleop.py - Dexterous Hand Teleoperation with improved retargeting

Based on dex-retargeting algorithms for better hand tracking accuracy.
Supports both regular webcam and RealSense depth camera.

Usage:
    python3 dex_teleop.py [--host HOST] [--port PORT] [--camera CAMERA_ID]
    python3 dex_teleop.py --depth  # Use RealSense depth camera
"""

import cv2
import mediapipe as mp
import numpy as np
import socket
import json
import time
import argparse
from typing import Optional, Tuple

# Coordinate transformation matrices (from dex-retargeting)
OPERATOR2MANO_RIGHT = np.array([
    [0, 0, -1],
    [-1, 0, 0],
    [0, 1, 0],
])

OPERATOR2MANO_LEFT = np.array([
    [0, 0, -1],
    [1, 0, 0],
    [0, -1, 0],
])


class HandDetector:
    """Improved hand detector based on dex-retargeting SingleHandDetector"""

    def __init__(self, hand_type="left", selfie=False):
        self.hand_detector = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.8,
            min_tracking_confidence=0.7,
        )
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_hands = mp.solutions.hands

        self.selfie = selfie
        self.hand_type = hand_type

        # MediaPipe detection from camera view:
        # - Your LEFT hand appears on RIGHT side of image -> MediaPipe says "Right"
        # - Your RIGHT hand appears on LEFT side of image -> MediaPipe says "Left"
        # So to detect your real left hand, we look for MediaPipe "Right" label
        if hand_type == "left":
            self.detected_hand_type = "Right"  # Your left hand -> MediaPipe "Right"
            self.operator2mano = OPERATOR2MANO_LEFT
        else:
            self.detected_hand_type = "Left"   # Your right hand -> MediaPipe "Left"
            self.operator2mano = OPERATOR2MANO_RIGHT

    def detect(self, rgb: np.ndarray) -> Tuple[int, Optional[np.ndarray], Optional[object]]:
        """
        Detect hand and return 3D joint positions

        Returns:
            num_hands: Number of detected hands
            joint_pos: 21x3 array of joint positions in MANO coordinates
            keypoint_2d: MediaPipe landmarks for drawing
        """
        results = self.hand_detector.process(rgb)

        if not results.multi_hand_landmarks:
            return 0, None, None

        # Find the desired hand
        desired_hand_idx = -1
        for i in range(len(results.multi_hand_landmarks)):
            label = results.multi_handedness[i].classification[0].label
            if label == self.detected_hand_type:
                desired_hand_idx = i
                break

        if desired_hand_idx < 0:
            return 0, None, None

        # Get 3D world landmarks (real-world coordinates)
        keypoint_3d = results.multi_hand_world_landmarks[desired_hand_idx]
        keypoint_2d = results.multi_hand_landmarks[desired_hand_idx]

        # Parse 3D keypoints
        keypoint_3d_array = np.empty([21, 3])
        for i in range(21):
            keypoint_3d_array[i][0] = keypoint_3d.landmark[i].x
            keypoint_3d_array[i][1] = keypoint_3d.landmark[i].y
            keypoint_3d_array[i][2] = keypoint_3d.landmark[i].z

        # Center at wrist
        keypoint_3d_array = keypoint_3d_array - keypoint_3d_array[0:1, :]

        # Compute wrist frame and transform to MANO coordinates
        wrist_rot = self._estimate_wrist_frame(keypoint_3d_array)
        joint_pos = keypoint_3d_array @ wrist_rot @ self.operator2mano

        return len(results.multi_hand_landmarks), joint_pos, keypoint_2d

    def _estimate_wrist_frame(self, keypoint_3d: np.ndarray) -> np.ndarray:
        """Estimate coordinate frame from hand keypoints"""
        points = keypoint_3d[[0, 5, 9], :]  # wrist, index_mcp, middle_mcp

        # Vector from middle MCP to wrist
        x_vector = points[0] - points[2]

        # Fit plane with SVD
        points_centered = points - np.mean(points, axis=0, keepdims=True)
        _, _, v = np.linalg.svd(points_centered)
        normal = v[2, :]

        # Gram-Schmidt orthonormalization
        x = x_vector - np.sum(x_vector * normal) * normal
        x = x / (np.linalg.norm(x) + 1e-6)
        z = np.cross(x, normal)

        # Ensure correct orientation
        if np.sum(z * (points[1] - points[2])) < 0:
            normal *= -1
            z *= -1

        frame = np.stack([x, normal, z], axis=1)
        return frame

    def draw_landmarks(self, image, keypoint_2d):
        """Draw hand landmarks on image"""
        if keypoint_2d is not None:
            self.mp_drawing.draw_landmarks(
                image, keypoint_2d, self.mp_hands.HAND_CONNECTIONS
            )


class LinkerHandRetargeting:
    """
    Retargeting algorithm for LinkerHand O6

    Uses vector-based retargeting similar to dex-retargeting.
    Maps fingertip-to-wrist vectors to joint positions.
    """

    # MediaPipe landmark indices
    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_MCP = 5
    INDEX_TIP = 8
    MIDDLE_MCP = 9
    MIDDLE_TIP = 12
    RING_MCP = 13
    RING_TIP = 16
    PINKY_MCP = 17
    PINKY_TIP = 20

    def __init__(self):
        # Smoothing parameters
        self.alpha = 0.2  # Low-pass filter coefficient
        self.prev_values = None
        self.deadzone = 5
        self.max_velocity = 25

        # O6 value ranges
        # thumb_bend: 102 (closed) - 250 (open)
        # thumb_yaw:  18 (closed) - 250 (open)
        # others:     0 (closed) - 255 (open)

        # Dynamic calibration for thumb yaw
        self.thumb_yaw_min = 1.0  # Will be updated to actual min observed
        self.thumb_yaw_max = 0.0  # Will be updated to actual max observed
        self.calibration_samples = 0

    def reset_calibration(self):
        """Reset thumb yaw calibration"""
        self.thumb_yaw_min = 1.0
        self.thumb_yaw_max = 0.0
        self.calibration_samples = 0

    def retarget(self, joint_pos: np.ndarray) -> Tuple[list, list]:
        """
        Convert 3D hand joint positions to LinkerHand O6 values

        Args:
            joint_pos: 21x3 array of joint positions

        Returns:
            o6_values: [thumb_bend, thumb_yaw, index, middle, ring, pinky]
            raw_bends: Raw bend values (0-1) for debugging
        """
        # Calculate finger vectors (tip - origin)
        # Origin is wrist (index 0) for all fingers
        thumb_vec = joint_pos[self.THUMB_TIP] - joint_pos[self.WRIST]
        index_vec = joint_pos[self.INDEX_TIP] - joint_pos[self.WRIST]
        middle_vec = joint_pos[self.MIDDLE_TIP] - joint_pos[self.WRIST]
        ring_vec = joint_pos[self.RING_TIP] - joint_pos[self.WRIST]
        pinky_vec = joint_pos[self.PINKY_TIP] - joint_pos[self.WRIST]

        # Reference vectors (MCP - wrist) for normalization
        index_ref = joint_pos[self.INDEX_MCP] - joint_pos[self.WRIST]
        middle_ref = joint_pos[self.MIDDLE_MCP] - joint_pos[self.WRIST]
        ring_ref = joint_pos[self.RING_MCP] - joint_pos[self.WRIST]
        pinky_ref = joint_pos[self.PINKY_MCP] - joint_pos[self.WRIST]
        thumb_ref = joint_pos[self.THUMB_CMC] - joint_pos[self.WRIST]

        # Calculate bend ratios (vector length ratio)
        index_bend = self._calc_bend_ratio(index_vec, index_ref)
        middle_bend = self._calc_bend_ratio(middle_vec, middle_ref)
        ring_bend = self._calc_bend_ratio(ring_vec, ring_ref)
        pinky_bend = self._calc_bend_ratio(pinky_vec, pinky_ref)

        # Thumb bend: distance from thumb tip to index MCP
        thumb_to_index = joint_pos[self.THUMB_TIP] - joint_pos[self.INDEX_MCP]
        thumb_bend = self._calc_bend_ratio(thumb_to_index, thumb_ref)

        # Thumb yaw: angle between thumb direction and palm plane
        thumb_yaw = self._calc_thumb_yaw(joint_pos)

        raw_bends = [thumb_bend, thumb_yaw, index_bend, middle_bend, ring_bend, pinky_bend]

        # Convert to O6 values
        # Higher bend value = more closed = lower O6 value
        thumb_val = int(250 - thumb_bend * 148)      # 250 -> 102
        thumb_yaw_val = int(250 - thumb_yaw * 232)   # 250 -> 18
        index_val = int(255 - index_bend * 255)      # 255 -> 0
        middle_val = int(255 - middle_bend * 255)
        ring_val = int(255 - ring_bend * 255)
        pinky_val = int(255 - pinky_bend * 255)

        o6_values = [thumb_val, thumb_yaw_val, index_val, middle_val, ring_val, pinky_val]

        # Apply low-pass filter
        o6_values = self._apply_filter(o6_values)

        return o6_values, raw_bends

    def _calc_bend_ratio(self, vec: np.ndarray, ref: np.ndarray) -> float:
        """Calculate bend ratio from vector lengths"""
        vec_len = np.linalg.norm(vec)
        ref_len = np.linalg.norm(ref)

        if ref_len < 0.001:
            return 0.5

        ratio = vec_len / ref_len
        # Map: ratio 2.0+ = open (0.0), ratio 0.8 = closed (1.0)
        bend = (2.0 - ratio) / 1.2
        return max(0.0, min(1.0, bend))

    def _calc_thumb_yaw(self, joint_pos: np.ndarray) -> float:
        """
        Calculate thumb yaw using the angle between thumb direction and palm plane.

        This method is independent of palm orientation.

        1. Build palm plane from 4 MCP points using SVD
        2. Get palm normal (perpendicular to palm)
        3. Thumb direction: THUMB_CMC → THUMB_TIP
        4. Angle to palm plane = 90° - angle_to_normal

        When thumb spread (pointing out of palm): angle to plane is small
        When thumb adducted (lying in palm): angle to plane is large
        """
        # Step 1: Build palm plane from MCP points
        mcp_points = np.array([
            joint_pos[self.INDEX_MCP],
            joint_pos[self.MIDDLE_MCP],
            joint_pos[self.RING_MCP],
            joint_pos[self.PINKY_MCP]
        ])

        # Center the points and use SVD to find plane normal
        centroid = np.mean(mcp_points, axis=0)
        centered = mcp_points - centroid
        _, _, vh = np.linalg.svd(centered)
        palm_normal = vh[2, :]  # Normal to the palm plane

        # Ensure normal points outward (away from palm surface)
        # Use wrist → middle_mcp as reference
        wrist_to_middle = joint_pos[self.MIDDLE_MCP] - joint_pos[self.WRIST]
        if np.dot(palm_normal, wrist_to_middle) < 0:
            palm_normal = -palm_normal

        # Step 2: Thumb direction: CMC → TIP
        thumb_cmc = joint_pos[self.THUMB_CMC]
        thumb_tip = joint_pos[self.THUMB_TIP]
        thumb_vec = thumb_tip - thumb_cmc
        thumb_vec = thumb_vec / (np.linalg.norm(thumb_vec) + 1e-6)

        # Step 3: Angle between thumb and palm normal
        cos_angle_to_normal = np.dot(thumb_vec, palm_normal)
        cos_angle_to_normal = np.clip(cos_angle_to_normal, -1.0, 1.0)
        angle_to_normal = np.degrees(np.arccos(np.abs(cos_angle_to_normal)))

        # Angle to palm plane = 90° - angle to normal
        # - Thumb perpendicular to palm (spread): angle_to_plane ≈ 90°
        # - Thumb lying in palm (adducted): angle_to_plane ≈ 0°
        angle_to_plane = 90 - angle_to_normal

        # Raw yaw value (before calibration)
        raw_yaw = 1.0 - (angle_to_plane / 90.0)

        # Dynamic calibration: update observed min/max
        self.calibration_samples += 1
        if raw_yaw < self.thumb_yaw_min:
            self.thumb_yaw_min = raw_yaw
        if raw_yaw > self.thumb_yaw_max:
            self.thumb_yaw_max = raw_yaw

        # After enough samples, normalize based on observed range
        if self.calibration_samples > 30:  # ~1 second at 30fps
            range_size = self.thumb_yaw_max - self.thumb_yaw_min
            if range_size > 0.1:  # Avoid division by small number
                yaw_normalized = (raw_yaw - self.thumb_yaw_min) / range_size
            else:
                yaw_normalized = raw_yaw
        else:
            yaw_normalized = raw_yaw

        # Invert: spread (大) → 0, adducted (小) → 1
        yaw_normalized = 1.0 - yaw_normalized

        return max(0.0, min(1.0, yaw_normalized))

    def _apply_filter(self, values: list) -> list:
        """Apply low-pass filter with deadzone and velocity limit"""
        if self.prev_values is None:
            self.prev_values = values[:]
            return values

        filtered = []
        for i, (new_val, prev_val) in enumerate(zip(values, self.prev_values)):
            # Low-pass filter (EMA)
            smoothed = int(self.alpha * new_val + (1 - self.alpha) * prev_val)

            # Velocity limit
            delta = smoothed - prev_val
            if abs(delta) > self.max_velocity:
                smoothed = prev_val + int(self.max_velocity * np.sign(delta))

            # Deadzone
            if abs(smoothed - prev_val) < self.deadzone:
                smoothed = prev_val

            # Clamp
            smoothed = max(0, min(255, smoothed))
            filtered.append(smoothed)
            self.prev_values[i] = smoothed

        return filtered


class DexTeleop:
    """Main teleoperation controller"""

    def __init__(self, host: str = "127.0.0.1", port: int = 5000,
                 camera_id: int = 0, use_depth: bool = False):
        self.host = host
        self.port = port
        self.camera_id = camera_id
        self.use_depth = use_depth

        # UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Hand detector and retargeting
        self.target_hand = "left"
        self.detector = HandDetector(hand_type=self.target_hand, selfie=False)
        self.retargeting = LinkerHandRetargeting()

        # Rate limiting
        self.last_send_time = 0
        self.send_interval = 1.0 / 30  # 30 Hz

        # Display
        self.show_debug = True

        # RealSense (if using depth)
        self.pipeline = None
        self.align = None

        print(f"Dex Teleop Initialized")
        print(f"  Target: {host}:{port}")
        if use_depth:
            print(f"  Camera: RealSense Depth (color + depth)")
        else:
            print(f"  Camera: /dev/video{camera_id} (RGB only, no depth)")
        print(f"  Hand: {self.target_hand}")
        print(f"")
        print(f"With --depth:    Real depth data, better thumb yaw accuracy")
        print(f"Without --depth: MediaPipe estimated depth, less accurate")

    def init_realsense(self) -> bool:
        """Initialize RealSense camera"""
        try:
            import pyrealsense2 as rs
            self.pipeline = rs.pipeline()
            config = rs.config()

            # L515 supports: color 640x480@30, depth 320x240@30
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            config.enable_stream(rs.stream.depth, 320, 240, rs.format.z16, 30)

            profile = self.pipeline.start(config)
            self.align = rs.align(rs.stream.color)

            depth_sensor = profile.get_device().first_depth_sensor()
            self.depth_scale = depth_sensor.get_depth_scale()

            print(f"RealSense initialized, depth scale: {self.depth_scale}")
            return True
        except Exception as e:
            print(f"RealSense init failed: {e}")
            return False

    def send_data(self, hand_type: str, o6_values: list):
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

    def switch_hand(self):
        """Switch between left and right hand"""
        self.target_hand = "right" if self.target_hand == "left" else "left"
        self.detector = HandDetector(hand_type=self.target_hand, selfie=False)
        self.retargeting = LinkerHandRetargeting()
        print(f"Switched to: {self.target_hand}")

    def run_webcam(self):
        """Run with regular webcam"""
        cap = cv2.VideoCapture(self.camera_id)
        if not cap.isOpened():
            print(f"Error: Cannot open camera {self.camera_id}")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        print("\nStarting hand tracking...")
        print("Keys: q=quit, h=switch hand, d=toggle debug, c=reset calibration")
        print("-" * 50)

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                self._process_frame(frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('h'):
                    self.switch_hand()
                elif key == ord('d'):
                    self.show_debug = not self.show_debug
                elif key == ord('c'):
                    self.retargeting.reset_calibration()
                    print("Calibration reset!")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.socket.close()

    def run_realsense(self):
        """Run with RealSense depth camera"""
        if not self.init_realsense():
            print("Failed to initialize RealSense")
            return

        import pyrealsense2 as rs

        print("\nStarting hand tracking with depth...")
        print("Keys: q=quit, h=switch hand, d=toggle debug, c=reset calibration")
        print("-" * 50)

        try:
            while True:
                frames = self.pipeline.wait_for_frames()
                aligned = self.align.process(frames)

                color_frame = aligned.get_color_frame()
                depth_frame = aligned.get_depth_frame()

                if not color_frame:
                    continue

                frame = np.asanyarray(color_frame.get_data())
                self._process_frame(frame, depth_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('h'):
                    self.switch_hand()
                elif key == ord('d'):
                    self.show_debug = not self.show_debug
                elif key == ord('c'):
                    self.retargeting.reset_calibration()
                    print("Calibration reset!")
        finally:
            self.pipeline.stop()
            cv2.destroyAllWindows()
            self.socket.close()

    def _process_frame(self, frame: np.ndarray, depth_frame=None):
        """Process a single frame"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]

        # Detect hand
        num_hands, joint_pos, keypoint_2d = self.detector.detect(rgb)

        if num_hands > 0 and joint_pos is not None:
            # Draw landmarks
            self.detector.draw_landmarks(frame, keypoint_2d)

            # Retarget to O6 values
            o6_values, raw_bends = self.retargeting.retarget(joint_pos)

            # Send data
            self.send_data(self.target_hand, o6_values)

            # Debug display
            if self.show_debug:
                labels = ["Thumb", "ThumbYaw", "Index", "Middle", "Ring", "Pinky"]
                for i, (lbl, val, bend) in enumerate(zip(labels, o6_values, raw_bends)):
                    cv2.putText(frame, f"{lbl}: {val} ({bend:.2f})",
                               (10, 30 + i * 25),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                # Show calibration info for thumb yaw
                calib_min = self.retargeting.thumb_yaw_min
                calib_max = self.retargeting.thumb_yaw_max
                calib_samples = self.retargeting.calibration_samples
                cv2.putText(frame, f"Yaw Calib: [{calib_min:.2f}-{calib_max:.2f}] n={calib_samples}",
                           (10, 30 + 6 * 25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        # Show status
        mode = "RealSense Depth" if self.use_depth else "Webcam"
        cv2.putText(frame, f"Target: {self.target_hand} ({mode}) [c=recalib]",
                   (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow("Dex Teleop - LinkerHand O6", frame)

    def run(self):
        """Main run loop"""
        if self.use_depth:
            self.run_realsense()
        else:
            self.run_webcam()


def main():
    parser = argparse.ArgumentParser(description="Dexterous Hand Teleoperation")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                       help="teleop_receiver IP address")
    parser.add_argument("--port", type=int, default=5000,
                       help="UDP port")
    parser.add_argument("--camera", type=int, default=6,
                       help="Camera device ID (default 6 for RealSense L515 RGB)")
    parser.add_argument("--depth", action="store_true",
                       help="Use RealSense depth camera")

    args = parser.parse_args()

    teleop = DexTeleop(
        host=args.host,
        port=args.port,
        camera_id=args.camera,
        use_depth=args.depth
    )
    teleop.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Hand Tracking Visualizer
Receives hand data via UDP and displays a simple hand visualization.
"""

import socket
import json
import cv2
import numpy as np
import argparse
import math


class HandVisualizer:
    def __init__(self, port: int = 5000):
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', port))
        self.socket.settimeout(0.1)

        # Window size
        self.width = 800
        self.height = 600

        # Hand data
        self.left_hand = [0, 0, 0, 0, 0, 0]
        self.right_hand = [0, 0, 0, 0, 0, 0]

        print(f"Hand Visualizer listening on UDP port {port}")
        print("Press 'q' to quit")

    def draw_hand(self, img, o6_values, hand_side, offset_x):
        """Draw a simple hand representation"""
        # o6_values: [thumb_bend, thumb_yaw, index, middle, ring, pinky]
        # Values are 0-255, where 0=open, 255=closed

        # Palm center
        palm_x = offset_x
        palm_y = 350
        palm_radius = 60

        # Draw palm
        cv2.circle(img, (palm_x, palm_y), palm_radius, (100, 100, 100), -1)
        cv2.circle(img, (palm_x, palm_y), palm_radius, (150, 150, 150), 2)

        # Finger parameters
        finger_names = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
        finger_colors = [
            (0, 200, 200),   # Thumb - yellow
            (0, 200, 0),     # Index - green
            (200, 0, 0),     # Middle - blue
            (200, 0, 200),   # Ring - magenta
            (0, 100, 200),   # Pinky - orange
        ]

        # Finger base positions (relative to palm center)
        if hand_side == "right":
            finger_bases = [
                (-55, 20),   # Thumb
                (-35, -55),  # Index
                (-5, -60),   # Middle
                (25, -55),   # Ring
                (50, -40),   # Pinky
            ]
            thumb_angle_base = -120
        else:
            finger_bases = [
                (55, 20),    # Thumb
                (35, -55),   # Index
                (5, -60),    # Middle
                (-25, -55),  # Ring
                (-50, -40),  # Pinky
            ]
            thumb_angle_base = -60

        # Draw fingers
        # Index 0: thumb_bend, Index 1: thumb_yaw, Index 2-5: other fingers
        finger_bends = [o6_values[0], o6_values[2], o6_values[3], o6_values[4], o6_values[5]]
        thumb_yaw = o6_values[1]

        for i, (name, color, (bx, by), bend) in enumerate(zip(
            finger_names, finger_colors, finger_bases, finger_bends
        )):
            base_x = palm_x + bx
            base_y = palm_y + by

            # Calculate finger angle based on bend
            # O6: 0=closed/bent, 255=open/straight
            # So we invert: bend_ratio = 1 - (value/255)
            bend_ratio = 1.0 - (bend / 255.0)  # 0=straight, 1=fully bent

            if i == 0:  # Thumb
                # Thumb yaw: 0=adducted (towards palm), 255=abducted (spread)
                yaw_ratio = thumb_yaw / 255.0  # 0=closed, 1=spread
                yaw_offset = yaw_ratio * 40  # 0-40 degrees spread
                if hand_side == "right":
                    base_angle = thumb_angle_base + yaw_offset
                else:
                    base_angle = thumb_angle_base - yaw_offset
                bend_angle = bend_ratio * 60  # Max 60 degrees bend
            else:
                base_angle = -90  # Fingers point up
                bend_angle = bend_ratio * 90  # Max 90 degrees bend

            # Finger segments
            seg1_len = 35
            seg2_len = 25
            seg3_len = 20

            # First segment
            angle1 = math.radians(base_angle)
            end1_x = int(base_x + seg1_len * math.cos(angle1))
            end1_y = int(base_y + seg1_len * math.sin(angle1))
            cv2.line(img, (base_x, base_y), (end1_x, end1_y), color, 8)
            cv2.circle(img, (base_x, base_y), 6, color, -1)

            # Second segment (bent)
            angle2 = angle1 + math.radians(bend_angle * 0.5)
            end2_x = int(end1_x + seg2_len * math.cos(angle2))
            end2_y = int(end1_y + seg2_len * math.sin(angle2))
            cv2.line(img, (end1_x, end1_y), (end2_x, end2_y), color, 6)
            cv2.circle(img, (end1_x, end1_y), 5, color, -1)

            # Third segment (more bent)
            angle3 = angle2 + math.radians(bend_angle * 0.5)
            end3_x = int(end2_x + seg3_len * math.cos(angle3))
            end3_y = int(end2_y + seg3_len * math.sin(angle3))
            cv2.line(img, (end2_x, end2_y), (end3_x, end3_y), color, 4)
            cv2.circle(img, (end2_x, end2_y), 4, color, -1)
            cv2.circle(img, (end3_x, end3_y), 3, color, -1)

        # Draw hand label
        cv2.putText(img, f"{hand_side.upper()} HAND",
                   (palm_x - 50, palm_y + 100),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Draw O6 values
        # O6: 0=closed, 255=open
        labels = ["ThumbB", "ThumbY", "Index", "Middle", "Ring", "Pinky"]
        for i, (label, val) in enumerate(zip(labels, o6_values)):
            y_pos = 30 + i * 25
            x_pos = offset_x - 80

            # Value bar (255=full bar=open, 0=empty=closed)
            bar_width = int((val / 255.0) * 100)
            cv2.rectangle(img, (x_pos, y_pos - 12), (x_pos + 100, y_pos + 5), (50, 50, 50), -1)
            cv2.rectangle(img, (x_pos, y_pos - 12), (x_pos + bar_width, y_pos + 5), finger_colors[min(i, 4)], -1)

            # Label and value (show open/closed state)
            state = "OPEN" if val > 200 else "CLOSED" if val < 55 else ""
            cv2.putText(img, f"{label}: {val:3d} {state}",
                       (x_pos - 80, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    def run(self):
        """Main visualization loop"""
        cv2.namedWindow("Hand Tracking Visualizer", cv2.WINDOW_NORMAL)

        while True:
            # Create blank image
            img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            img[:] = (30, 30, 30)  # Dark gray background

            # Try to receive data
            try:
                data, addr = self.socket.recvfrom(4096)
                json_str = data.decode('utf-8')
                hand_data = json.loads(json_str)

                if hand_data.get('type') == 'hand_pose':
                    hand = hand_data.get('hand', 'left')
                    o6_values = hand_data.get('o6_values', [0]*6)

                    # Handle string format
                    if isinstance(o6_values, str):
                        o6_values = json.loads(o6_values)

                    if hand == 'left':
                        self.left_hand = o6_values
                    else:
                        self.right_hand = o6_values

            except socket.timeout:
                pass
            except Exception as e:
                print(f"Error: {e}")

            # Draw both hands
            self.draw_hand(img, self.left_hand, "left", 200)
            self.draw_hand(img, self.right_hand, "right", 600)

            # Title
            cv2.putText(img, "VR Hand Tracking Visualizer (Palm facing you)",
                       (180, 560),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            cv2.putText(img, f"UDP Port: {self.port} | O6: 0=closed, 255=open",
                       (270, 585),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

            # Show image
            cv2.imshow("Hand Tracking Visualizer", img)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

        cv2.destroyAllWindows()
        self.socket.close()


def main():
    parser = argparse.ArgumentParser(description="Hand Tracking Visualizer")
    parser.add_argument('--port', type=int, default=5000, help='UDP port')
    args = parser.parse_args()

    visualizer = HandVisualizer(port=args.port)
    visualizer.run()


if __name__ == '__main__':
    main()

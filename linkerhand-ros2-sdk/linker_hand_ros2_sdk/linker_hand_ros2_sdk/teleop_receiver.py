#!/usr/bin/env python3
"""
teleop_receiver.py - ROS2 node to receive hand tracking data from Android XR

This node receives UDP packets from the TeleopXR Android app and publishes
hand control commands to LinkerHand topics.

Data Flow:
    Android XR (Samsung Galaxy XR)
           |
           | UDP (port 5000)
           v
    teleop_receiver (this node)
           |
           | ROS2 Topics
           v
    /cb_left_hand_control_cmd
    /cb_right_hand_control_cmd
           |
           v
    LinkerHand O6 (via linker_hand_sdk)

Usage:
    ros2 run linker_hand_ros2_sdk teleop_receiver --ros-args -p port:=5000

Author: TeleopXR Integration
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import String

import socket
import json
import threading
from typing import Optional, Dict, Any


class TeleopReceiver(Node):
    """
    ROS2 node that receives hand tracking data via UDP and publishes to LinkerHand topics.
    """

    def __init__(self):
        super().__init__('teleop_receiver')

        # Declare parameters
        self.declare_parameter('port', 5000)
        self.declare_parameter('buffer_size', 1024)
        self.declare_parameter('hand_type', 'left')  # 'left', 'right', or 'both'

        # Get parameters
        self.port = self.get_parameter('port').value
        self.buffer_size = self.get_parameter('buffer_size').value
        self.hand_type = self.get_parameter('hand_type').value

        # Create publishers for LinkerHand control
        self.left_hand_pub = self.create_publisher(
            JointState,
            '/cb_left_hand_control_cmd',
            10
        )
        self.right_hand_pub = self.create_publisher(
            JointState,
            '/cb_right_hand_control_cmd',
            10
        )

        # Publisher for raw teleop data (for debugging)
        self.raw_data_pub = self.create_publisher(
            String,
            '/teleop_raw_data',
            10
        )

        # Initialize UDP socket
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.bind(('0.0.0.0', self.port))
        self.udp_socket.settimeout(1.0)  # 1 second timeout for graceful shutdown

        # Thread control
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()

        self.get_logger().info(f'TeleopReceiver started on UDP port {self.port}')
        self.get_logger().info(f'Controlling hand type: {self.hand_type}')

    def _receive_loop(self):
        """
        Main loop to receive UDP packets and process hand data.
        Runs in a separate thread.
        """
        while self.running:
            try:
                # Receive UDP packet
                data, addr = self.udp_socket.recvfrom(self.buffer_size)

                # Parse JSON data
                json_str = data.decode('utf-8')
                hand_data = json.loads(json_str)

                # Process the hand data
                self._process_hand_data(hand_data, addr)

            except socket.timeout:
                # Normal timeout, continue loop
                continue
            except json.JSONDecodeError as e:
                self.get_logger().warn(f'Invalid JSON received: {e}')
            except Exception as e:
                if self.running:
                    self.get_logger().error(f'Receive error: {e}')

    def _process_hand_data(self, data: Dict[str, Any], addr: tuple):
        """
        Process received hand data and publish to ROS2 topics.

        Expected data format:
        {
            "type": "hand_pose",
            "hand": "left" | "right",
            "timestamp": 1234567890123,
            "o6_values": [0, 128, 255, 200, 150, 100],
            "finger_bend": [0.0, 0.5, 1.0, 0.8, 0.6, 0.4]
        }

        Args:
            data: Parsed JSON dictionary
            addr: Source address tuple (ip, port)
        """
        # Validate data type
        if data.get('type') != 'hand_pose':
            self.get_logger().debug(f'Ignoring non-hand_pose data type: {data.get("type")}')
            return

        # Get hand side
        hand = data.get('hand', 'left')

        # Get O6 control values
        o6_values = data.get('o6_values', [])
        if len(o6_values) != 6:
            self.get_logger().warn(f'Invalid o6_values length: {len(o6_values)}, expected 6')
            return

        # Create JointState message
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = f'{hand}_hand'

        # Convert O6 values to float positions
        # O6 expects values in range 0-255
        msg.position = [float(v) for v in o6_values]

        # Publish to appropriate topic
        if hand == 'left' and self.hand_type in ['left', 'both']:
            self.left_hand_pub.publish(msg)
            self.get_logger().debug(f'Published left hand: {o6_values}')

        elif hand == 'right' and self.hand_type in ['right', 'both']:
            self.right_hand_pub.publish(msg)
            self.get_logger().debug(f'Published right hand: {o6_values}')

        # Publish raw data for debugging
        raw_msg = String()
        raw_msg.data = json.dumps(data)
        self.raw_data_pub.publish(raw_msg)

    def destroy_node(self):
        """
        Clean up resources when node is destroyed.
        """
        self.get_logger().info('Shutting down TeleopReceiver...')

        # Stop receive thread
        self.running = False
        if self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2.0)

        # Close socket
        try:
            self.udp_socket.close()
        except Exception as e:
            self.get_logger().warn(f'Error closing socket: {e}')

        super().destroy_node()


def main(args=None):
    """
    Main entry point for the teleop_receiver node.
    """
    rclpy.init(args=args)

    node = TeleopReceiver()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

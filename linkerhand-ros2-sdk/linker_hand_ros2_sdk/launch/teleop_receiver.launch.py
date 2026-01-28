#!/usr/bin/env python3
"""
teleop_receiver.launch.py - Launch file for Android XR teleoperation receiver

This launch file starts:
1. teleop_receiver - UDP receiver that converts Android XR data to ROS2 topics
2. linker_hand_sdk - LinkerHand SDK for controlling the O6 hand

Usage:
    ros2 launch linker_hand_ros2_sdk teleop_receiver.launch.py

Parameters:
    port: UDP port to listen on (default: 5000)
    hand_type: 'left', 'right', or 'both' (default: 'left')
    hand_joint: LinkerHand model - O6, L6, L7, L10, etc. (default: 'O6')
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Declare launch arguments
    port_arg = DeclareLaunchArgument(
        'port',
        default_value='5000',
        description='UDP port for receiving hand tracking data'
    )

    hand_type_arg = DeclareLaunchArgument(
        'hand_type',
        default_value='left',
        description='Hand type to control: left, right, or both'
    )

    hand_joint_arg = DeclareLaunchArgument(
        'hand_joint',
        default_value='O6',
        description='LinkerHand model: O6, L6, L7, L10, L20, G20, L21'
    )

    # Teleop receiver node - receives UDP from Android XR
    teleop_receiver_node = Node(
        package='linker_hand_ros2_sdk',
        executable='teleop_receiver',
        name='teleop_receiver',
        output='screen',
        parameters=[{
            'port': LaunchConfiguration('port'),
            'hand_type': LaunchConfiguration('hand_type'),
        }],
    )

    # LinkerHand SDK node - controls the physical hand
    linker_hand_node = Node(
        package='linker_hand_ros2_sdk',
        executable='linker_hand_sdk',
        name='linker_hand_sdk',
        output='screen',
        parameters=[{
            'hand_type': LaunchConfiguration('hand_type'),
            'hand_joint': LaunchConfiguration('hand_joint'),
        }],
    )

    return LaunchDescription([
        port_arg,
        hand_type_arg,
        hand_joint_arg,
        teleop_receiver_node,
        linker_hand_node,
    ])

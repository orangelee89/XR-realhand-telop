#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Combined launch file for dual hand VR teleop
Launches both linker_hand_sdk (dual) and teleop_receiver
"""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import TimerAction, LogInfo

def generate_launch_description():
    # Left hand node
    left_hand_node = Node(
        package='linker_hand_ros2_sdk',
        executable='linker_hand_sdk',
        name='linker_hand_sdk_left',
        output='screen',
        parameters=[{
            'hand_type': 'left',
            'hand_joint': "O6",
            'is_touch': False,
            'can': 'can0',
            "modbus": "None"
        }],
    )

    # Right hand node
    right_hand_node = Node(
        package='linker_hand_ros2_sdk',
        executable='linker_hand_sdk',
        name='linker_hand_sdk_right',
        output='screen',
        parameters=[{
            'hand_type': 'right',
            'hand_joint': "O6",
            'is_touch': False,
            'can': 'can1',
            "modbus": "None"
        }],
    )

    # Teleop receiver node - delayed start to ensure hands are initialized
    teleop_receiver_node = TimerAction(
        period=3.0,  # Wait 3 seconds for hands to initialize
        actions=[
            Node(
                package='linker_hand_ros2_sdk',
                executable='teleop_receiver',
                name='teleop_receiver',
                output='screen',
                parameters=[{
                    'port': 5000,
                    'hand_type': 'both',
                    'hand_joint': 'O6',
                }],
            )
        ]
    )

    # Show GUI info message after 5 seconds
    gui_info_message = TimerAction(
        period=5.0,
        actions=[
            LogInfo(msg='\n\n\n\n\n'),
            LogInfo(msg='========================================================'),
            LogInfo(msg='  VR Teleop is READY! You can now operate in XR.'),
            LogInfo(msg='========================================================'),
            LogInfo(msg=''),
            LogInfo(msg='  GUI Control can be run by:'),
            LogInfo(msg='  ros2 launch gui_control gui_control.launch.py'),
            LogInfo(msg='========================================================'),
            LogInfo(msg='\n'),
        ]
    )

    return LaunchDescription([
        left_hand_node,
        right_hand_node,
        teleop_receiver_node,
        gui_info_message,
    ])

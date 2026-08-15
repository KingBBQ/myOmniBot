"""Modell in RViz2 anschauen, ohne Roboter und ohne Bordrechner.

    ros2 launch omnibot_description display.launch.py

Gut geeignet, um nach einer Aenderung am URDF zu pruefen, ob die Masse stimmen -
Fixed Frame steht in der mitgelieferten Konfiguration auf base_footprint.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory("omnibot_description")

    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(share, "launch", "description.launch.py")
            )
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            output="screen",
            arguments=["-d", os.path.join(share, "rviz", "omnibot.rviz")],
        ),
    ])

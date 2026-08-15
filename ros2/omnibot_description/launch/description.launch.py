"""Nur das Modell: robot_state_publisher mit dem expandierten URDF.

Wird von omnibot_bringup eingebunden. Alleine gestartet ist es nuetzlich, um
das URDF in RViz2 anzuschauen, ohne dass ein Roboter dranhaengt:

    ros2 launch omnibot_description display.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    urdf = os.path.join(
        get_package_share_directory("omnibot_description"), "urdf", "omnibot.urdf.xacro"
    )

    use_sim_time = LaunchConfiguration("use_sim_time")

    # ParameterValue mit value_type=str ist noetig: ohne das versucht ROS, das
    # XML als YAML zu interpretieren, und der Start scheitert kryptisch.
    robot_description = ParameterValue(Command(["xacro ", urdf]), value_type=str)

    return LaunchDescription([
        DeclareLaunchArgument(
            "use_sim_time", default_value="false",
            description="Simulationszeit verwenden"),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{
                "robot_description": robot_description,
                "use_sim_time": use_sim_time,
            }],
        ),
    ])

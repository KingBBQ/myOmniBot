"""Der ganze Roboter auf dem Bordrechner: Modell, Motorknoten, LIDAR.

    ros2 launch omnibot_bringup bringup.launch.py

Danach faehrt er auf /cmd_vel und liefert /odom, /scan und den TF-Baum
odom -> base_footprint -> base_link -> base_laser.

Argumente:
    motor_port:=/dev/ttyAMA0    GPIO-UART zum RoboESP32
    lidar_port:=/dev/ttyLIDAR   udev-Symlink aus docs/pi-setup.md
    use_lidar:=false            ohne LIDAR starten (nur Fahrbetrieb testen)
    use_rviz:=true              RViz2 dazu (auf dem Pi besser nicht)
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    description_share = get_package_share_directory("omnibot_description")
    bringup_share = get_package_share_directory("omnibot_bringup")
    base_params = os.path.join(
        get_package_share_directory("omnibot_base"), "config", "omnibot_base.yaml"
    )

    motor_port = LaunchConfiguration("motor_port")
    lidar_port = LaunchConfiguration("lidar_port")
    use_lidar = LaunchConfiguration("use_lidar")
    use_rviz = LaunchConfiguration("use_rviz")

    arguments = [
        DeclareLaunchArgument("motor_port", default_value="/dev/ttyAMA0"),
        DeclareLaunchArgument("lidar_port", default_value="/dev/ttyLIDAR"),
        DeclareLaunchArgument("use_lidar", default_value="true"),
        DeclareLaunchArgument("use_rviz", default_value="false"),
    ]

    description = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(description_share, "launch", "description.launch.py")
        )
    )

    motor = Node(
        package="omnibot_base",
        executable="motor_node",
        name="omnibot_base",
        output="screen",
        parameters=[base_params, {"port": motor_port}],
    )

    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_share, "launch", "lidar.launch.py")
        ),
        launch_arguments={"lidar_port": lidar_port}.items(),
        condition=IfCondition(use_lidar),
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="screen",
        arguments=["-d", os.path.join(description_share, "rviz", "omnibot.rviz")],
        condition=IfCondition(use_rviz),
    )

    return LaunchDescription(arguments + [description, motor, lidar, rviz])

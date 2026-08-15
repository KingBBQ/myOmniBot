"""LDROBOT STL-19P (LD19-Baureihe) am Bordrechner.

Der Treiber bringt einen eigenen ld19.launch.py mit, der aber fest auf
/dev/ttyUSB0 zeigt. Auf dem Pi haengt das LIDAR unter dem udev-Symlink
/dev/ttyLIDAR (siehe docs/pi-setup.md), deshalb wird der Knoten hier direkt
mit den passenden Parametern gestartet.

ACHTUNG: die Parameternamen stammen aus dem ld19.launch.py des Treibers. Wenn
der Start mit "parameter not declared" abbricht, einmal

    ros2 pkg prefix ldlidar_stl_ros2
    cat $(ros2 pkg prefix ldlidar_stl_ros2)/share/ldlidar_stl_ros2/launch/ld19.launch.py

vergleichen und die Namen hier angleichen.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    lidar_port = LaunchConfiguration("lidar_port")

    return LaunchDescription([
        DeclareLaunchArgument("lidar_port", default_value="/dev/ttyLIDAR"),
        Node(
            package="ldlidar_stl_ros2",
            executable="ldlidar_stl_ros2_node",
            name="ldlidar_node",
            output="screen",
            parameters=[{
                "product_name": "LDLiDAR_LD19",
                "topic_name": "scan",
                # Muss zum URDF passen, sonst haengt der Scan im Nichts
                "frame_id": "base_laser",
                "port_name": lidar_port,
                "port_baudrate": 230400,
                # True = gegen den Uhrzeigersinn, Default des Treibers
                "laser_scan_dir": True,
                "enable_angle_crop_func": False,
                "angle_crop_min": 135.0,
                "angle_crop_max": 225.0,
            }],
        ),
    ])

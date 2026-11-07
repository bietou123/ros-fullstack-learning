"""在 rviz 里跑挖掘机运动学仿真。

    ros2 launch excavator_sim excavator.launch.py
    ros2 launch excavator_sim excavator.launch.py speed:=0.4 rviz:=false
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    share = get_package_share_directory("excavator_sim")
    urdf_path = os.path.join(share, "urdf", "excavator.urdf")
    rviz_path = os.path.join(share, "config", "excavator.rviz")

    # robot_state_publisher 要的是 URDF 文本，不是路径，这里直接读进来。
    with open(urdf_path, "r", encoding="utf-8") as fh:
        robot_description = fh.read()

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_path],
        condition=IfCondition(LaunchConfiguration("rviz")),
        output="screen",
        # Wayland 会话下必须强制 X11：GTK 会挂到 Wayland，而 rviz 的 Ogre
        # 用 GLX 建上下文，拿到的是 Wayland parent window handle，直接
        # 报 "Invalid parentWindowHandle (wrong server or screen)"。
        additional_env={"GDK_BACKEND": "x11", "QT_QPA_PLATFORM": "xcb"},
    )

    return LaunchDescription([
        DeclareLaunchArgument("rviz", default_value="true",
                              description="是否启动 rviz2 预览"),
        DeclareLaunchArgument("speed", default_value="1.0",
                              description="动作循环倍速"),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            parameters=[{"robot_description": robot_description}],
            output="screen",
        ),
        Node(
            package="excavator_sim",
            executable="excavator_anim",
            name="excavator_anim",
            parameters=[{"speed": LaunchConfiguration("speed")}],
            output="screen",
        ),
        rviz,
    ])

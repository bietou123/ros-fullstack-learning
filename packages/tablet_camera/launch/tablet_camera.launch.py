"""Start the tablet camera node, optionally with an Image view."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory("tablet_camera")
    rviz_config = os.path.join(share, "config", "tablet_camera.rviz")

    args = [
        DeclareLaunchArgument("width", default_value="960"),
        DeclareLaunchArgument("height", default_value="600"),
        DeclareLaunchArgument("fps", default_value="15.0"),
        DeclareLaunchArgument("camera_name", default_value=""),
        DeclareLaunchArgument("exposure_value", default_value="2.5"),
        DeclareLaunchArgument("awb_enable", default_value="true"),
        DeclareLaunchArgument("topic", default_value="/camera/image_raw"),
        DeclareLaunchArgument("frame_id", default_value="camera_optical_frame"),
        DeclareLaunchArgument("hfov_deg", default_value="60.0"),
        DeclareLaunchArgument("rviz", default_value="true"),
    ]

    cam = Node(
        package="tablet_camera",
        executable="cam_pub",
        name="tablet_camera",
        output="screen",
        parameters=[{
            "width": LaunchConfiguration("width"),
            "height": LaunchConfiguration("height"),
            "fps": LaunchConfiguration("fps"),
            "camera_name": LaunchConfiguration("camera_name"),
            "exposure_value": LaunchConfiguration("exposure_value"),
            "awb_enable": LaunchConfiguration("awb_enable"),
            "topic": LaunchConfiguration("topic"),
            "frame_id": LaunchConfiguration("frame_id"),
            "hfov_deg": LaunchConfiguration("hfov_deg"),
        }],
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_config],
        parameters=[{"use_sim_time": False}],
        condition=IfCondition(LaunchConfiguration("rviz")),
        output="screen",
        # Wayland 会话下必须强制 X11：GTK 会挂到 Wayland，而 rviz 的 Ogre
        # 用 GLX 建上下文，拿到的是 Wayland parent window handle，直接
        # 报 "Invalid parentWindowHandle (wrong server or screen)"。
        additional_env={"GDK_BACKEND": "x11", "QT_QPA_PLATFORM": "xcb"},
    )

    return LaunchDescription(args + [cam, rviz])

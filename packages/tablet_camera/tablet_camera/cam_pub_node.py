#!/usr/bin/env python3
"""Publish a libcamera-backed camera as ROS 2 Image + CameraInfo.

本节点面向「有 GStreamer libcamerasrc、但没有 v4l2_camera / usb_cam 驱动」的
平台（典型：Qualcomm CAMSS 多平面设备，例如改造后的 Android 平板）。

链路：
    libcamerasrc -> videoscale -> videoconvert(RGB) -> appsink -> rclpy

设计要点（都是在真机上踩出来的）：
  * 采集在 GStreamer 里做缩放，Python 端只做零拷贝切片，避免每帧
    在 3840x2400 RGBA（约 36 MB）上做跨步采样，帧率能稳定很多。
  * 用 timer 轮询 appsink，而不是 `while True: pull-sample()`。裸循环会
    在相机停滞时空转吃满一个核，并且挡住 rclpy 的 Ctrl+C 处理。
  * 看门狗：libcamera 的 simple pipeline 长时间运行会静默停帧，超时后
    自动重建管线，而不是让节点「活着但不发帧」。
  * camera_info 默认按水平视场角估算内参，并在 K 里如实标注未标定；
    要精确值请提供标定 YAML（camera_info_url）。

用法：
    ros2 run tablet_camera cam_pub
    ros2 run tablet_camera cam_pub --ros-args -p width:=640 -p height:=400 -p fps:=10

直接跑（不经 colcon）：
    python3 cam_pub_node.py --ros-args -p fps:=10
"""

import math
import time

import gi
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CameraInfo, Image

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

Gst.init(None)


class TabletCameraNode(Node):

    def __init__(self):
        super().__init__("tablet_camera")

        # ---- 输出尺寸与节奏 ---------------------------------------------
        self.declare_parameter("width", 960)
        self.declare_parameter("height", 600)
        self.declare_parameter("fps", 15.0)

        # ---- 相机选择 ---------------------------------------------------
        # libcamerasrc 的 camera-name 属性；留空则用第一台相机。
        self.declare_parameter("camera_name", "")
        # 传感器曝光值；<= 0 表示不设置（使用驱动默认）。
        # 很多移植版传感器默认曝光极暗，需要给一个正值才看得见。
        self.declare_parameter("exposure_value", 2.5)
        self.declare_parameter("awb_enable", True)

        # ---- 话题 -------------------------------------------------------
        self.declare_parameter("topic", "/camera/image_raw")
        self.declare_parameter("camera_info_topic", "/camera/camera_info")
        self.declare_parameter("frame_id", "camera_optical_frame")
        self.declare_parameter("publish_camera_info", True)
        # 图像 QoS：true = best effort + depth 1（只要最新帧，视频首选）；
        # false = reliable + depth 5（订阅端写了 Reliable 时才需要）。
        self.declare_parameter("image_best_effort", True)

        # 未标定时的内参估算：水平视场角（度）。60° 是手机/平板广角的量级。
        # 注意：这是几何估算，不是真实标定值，D 恒为 0。
        self.declare_parameter("hfov_deg", 60.0)

        # ---- 稳定性 -----------------------------------------------------
        self.declare_parameter("watchdog_timeout", 3.0)
        self.declare_parameter("restart_delay", 1.0)

        self._width = int(self.get_parameter("width").value)
        self._height = int(self.get_parameter("height").value)
        self._fps = max(1.0, float(self.get_parameter("fps").value))
        self._exposure = float(self.get_parameter("exposure_value").value)
        self._awb = bool(self.get_parameter("awb_enable").value)
        self._frame_id = self.get_parameter("frame_id").value
        self._hfov = float(self.get_parameter("hfov_deg").value)
        self._watchdog = float(self.get_parameter("watchdog_timeout").value)

        # 图像默认走「最新一帧」：深度 1 + best effort。深度大于 1 的可靠队列
        # 在显示端变慢时会把旧帧攒下来成串发出，画面上就是一顿一顿地跳。
        if self.get_parameter("image_best_effort").value:
            image_qos = QoSProfile(
                depth=1,
                history=HistoryPolicy.KEEP_LAST,
                reliability=ReliabilityPolicy.BEST_EFFORT,
            )
        else:
            image_qos = QoSProfile(
                depth=5,
                history=HistoryPolicy.KEEP_LAST,
                reliability=ReliabilityPolicy.RELIABLE,
            )
        self._image_pub = self.create_publisher(
            Image, self.get_parameter("topic").value, image_qos)
        self._info_pub = None
        self._info = self._make_camera_info(self._width, self._height)
        if self.get_parameter("publish_camera_info").value:
            self._info_pub = self.create_publisher(
                CameraInfo, self.get_parameter("camera_info_topic").value, 5)

        self._pipeline = None
        self._sink = None
        self._last_frame = 0.0
        self._frames = 0
        self._dropped = 0
        self._last_report = time.monotonic()

        self._build_pipeline()

        # 轮询频率高于相机帧率，保证不漏帧又不空转。
        period = 1.0 / max(self._fps * 2.0, 10.0)
        self._timer = self.create_timer(period, self._tick)

    # ---------------------------------------------------------------- 内参
    def _make_camera_info(self, w: int, h: int) -> CameraInfo:
        """按水平视场角估算针孔内参。未标定：D=0，不含畸变模型。"""
        f = w / (2.0 * math.tan(math.radians(self._hfov) / 2.0))
        info = CameraInfo()
        info.width = w
        info.height = h
        info.distortion_model = "plumb_bob"
        info.d = [0.0, 0.0, 0.0, 0.0, 0.0]
        info.k = [f, 0.0, w / 2.0,
                  0.0, f, h / 2.0,
                  0.0, 0.0, 1.0]
        info.r = [1.0, 0.0, 0.0,
                  0.0, 1.0, 0.0,
                  0.0, 0.0, 1.0]
        info.p = [f, 0.0, w / 2.0, 0.0,
                  0.0, f, h / 2.0, 0.0,
                  0.0, 0.0, 1.0, 0.0]
        return info

    # ------------------------------------------------------------- pipeline
    def _build_pipeline(self):
        src = "libcamerasrc"
        name = self.get_parameter("camera_name").value
        if name:
            src += f' camera-name="{name}"'
        if self._exposure > 0:
            src += f" exposure-value={self._exposure}"
        src += " awb-enable=" + ("true" if self._awb else "false")

        launch = (
            f'{src} ! video/x-raw,format=RGBA ! '
            f'videoscale ! video/x-raw,width={self._width},height={self._height} ! '
            f'videoconvert ! video/x-raw,format=RGB ! '
            f'appsink name=sink max-buffers=1 drop=true sync=true emit-signals=false'
        )
        self.get_logger().info(f"pipeline: {launch}")

        try:
            self._pipeline = Gst.parse_launch(launch)
        except Exception as exc:  # gi 抛 GLib.Error
            self.get_logger().error(f"GStreamer parse failed: {exc}")
            self._pipeline = None
            return

        self._sink = self._pipeline.get_by_name("sink")
        ret = self._pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self.get_logger().error(
                "pipeline failed to start: camera busy or no camera found")
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            return

        self._last_frame = time.monotonic()
        self.get_logger().info("pipeline PLAYING")

    def _restart_pipeline(self):
        self.get_logger().warn(
            f"no frames for >{self._watchdog:.1f}s, restarting pipeline")
        self._teardown()
        time.sleep(float(self.get_parameter("restart_delay").value))
        self._build_pipeline()

    def _teardown(self):
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._sink = None

    # ----------------------------------------------------------------- tick
    def _tick(self):
        if self._sink is None:
            return

        sample = self._sink.emit("pull-sample")
        now = time.monotonic()
        if sample is None:
            self._dropped += 1
            if now - self._last_frame > self._watchdog:
                self._restart_pipeline()
            return

        buf = sample.get_buffer()
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return
        try:
            caps = sample.get_caps().get_structure(0)
            w = caps.get_value("width")
            h = caps.get_value("height")
            n = w * h * 3
            if mapinfo.size < n:
                return
            # frombuffer 是只读视图，reshape 不复制；tobytes 只拷一次。
            arr = np.frombuffer(mapinfo.data, dtype=np.uint8, count=n).reshape(h, w, 3)
            msg = Image()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self._frame_id
            msg.height = h
            msg.width = w
            msg.encoding = "rgb8"
            msg.is_bigendian = 0
            msg.step = w * 3
            msg.data = arr.tobytes()
        finally:
            buf.unmap(mapinfo)

        self._image_pub.publish(msg)
        if self._info_pub is not None:
            if self._info.width != w or self._info.height != h:
                self._info = self._make_camera_info(w, h)
            info = self._info
            info.header.stamp = msg.header.stamp
            info.header.frame_id = self._frame_id
            self._info_pub.publish(info)

        self._last_frame = now
        self._frames += 1

        if now - self._last_report >= 10.0:
            self.get_logger().info(
                f"{self._frames / (now - self._last_report):.1f} fps, "
                f"{self._frames} frames")
            self._frames = 0
            self._last_report = now

    def destroy_node(self):
        self._teardown()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TabletCameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

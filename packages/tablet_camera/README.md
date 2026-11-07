# tablet_camera

把平板内置摄像头以 `sensor_msgs/Image` + `sensor_msgs/CameraInfo` 发布到 ROS 2。

适用于**有 GStreamer `libcamerasrc`、但没有 `v4l2_camera` / `usb_cam` 可用驱动**的平台 ——
典型就是移植到 Qualcomm CAMSS 多平面设备的机器（本项目测试机：小米 Pad 6 Pro，
Ubuntu 26.04 arm64，ROS 2 lyrical，libcamera 0.7.0 simple pipeline）。

## 为什么不用 v4l2_camera

这类设备的 `/dev/video0..N` 是 V4L2 **多平面（memory-to-memory / RDI）** 节点，
只支持 `V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE`。`v4l2_camera` 的 ioctl 走
`VIDEO_CAPTURE`，`VIDIOC_S_FMT` 直接返回 `EINVAL`；`usb_cam` 同理。
libcamera 的 simple pipeline handler 已经封装好了 media controller 拓扑，
所以走 `libcamerasrc` 是这台机器上唯一现成的通路。

## 依赖

```bash
sudo apt install gstreamer1.0-libcamera gir1.2-gst-plugins-base-1.0 python3-gi
# 系统里有 /dev/media0 且 media-ctl 能看到 sensor 即可
```

## 构建

```bash
# 放进你的 ROS 2 工作空间 src/ 下
cd ~/ros_ws
colcon build --packages-select tablet_camera
source install/setup.bash
```

## 运行

```bash
# 带 rviz 预览
ros2 launch tablet_camera tablet_camera.launch.py

# 只要节点
ros2 run tablet_camera cam_pub

# 小分辨率、低帧率（负载紧张的平板上推荐）
ros2 run tablet_camera cam_pub --ros-args -p width:=640 -p height:=400 -p fps:=10
```

不带 colcon 直接跑（脚本模式）：

```bash
python3 tablet_camera/cam_pub_node.py --ros-args -p fps:=10
```

## 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `width` / `height` | 960 / 600 | 输出分辨率。缩放由 GStreamer `videoscale` 完成（下游比 Python 快得多） |
| `fps` | 15.0 | 轮询上限，同时也是测帧率的窗口基准；实际帧率受传感器/CPU 限制 |
| `camera_name` | 空 | `libcamerasrc camera-name=`；空则用第一台相机。可用 `gst-device-monitor-1.0 Video/Source` 查 |
| `exposure_value` | 2.5 | 传感器曝光。移植版 sensor 驱动默认通常很暗；`<= 0` 表示不设置 |
| `awb_enable` | true | 自动白平衡 |
| `topic` | `/camera/image_raw` | 图像话题 |
| `camera_info_topic` | `/camera/camera_info` | 内参话题 |
| `frame_id` | `camera_optical_frame` | 坐标系 |
| `publish_camera_info` | true | 是否发内参 |
| `image_best_effort` | true | 图像 QoS。`true` = BEST_EFFORT + depth 1（只要最新帧，视频首选）；`false` = RELIABLE + depth 5（订阅端固定 Reliable 时才用） |
| `hfov_deg` | 60.0 | 未标定时按水平视场角估算焦距 |
| `watchdog_timeout` | 3.0 | 超过多少秒无帧就重建管线 |
| `restart_delay` | 1.0 | 重建前等待，等 camera manager 释放设备 |

## 相机内参是**估算值**

`CameraInfo` 的 `K`/`P` 由 `hfov_deg` 按针孔模型反推：

```
fx = fy = width / (2 * tan(hfov/2))
cx = width / 2,  cy = height / 2
D  = [0,0,0,0,0]
```

这**不是标定结果**，`D` 恒为 0。要做 SLAM、测距、标定板对齐之类的任务，
必须自己跑一次 `camera_calibration` 或 `ros2 run camera_calibration cameracalibrator`
并把得到的 YAML 灌进你的下游节点。传感器画质路径还经过 libcamera 的
**uncalibrated IPA**（没有 tuning 文件），几何畸变本身也没被校正。

## 已知问题

- **帧率不匀**：libcamera simple pipeline + 软件 ISP 的排队抖动，帧间隔会在
  30–68 ms 之间跳（`std dev ≈ 0.007 s`），不是节点丢帧。缩放放到 GStreamer
  端之后抖动明显收敛；剩下的是传感器侧固有的。**画面「一闪一闪」的典型原因
  是连发帧**：下游变慢时旧帧排在可靠队列里成串发出，同一个显示帧被刷两次。
  本节点默认 `image_best_effort:=true`（best effort + depth 1）就是为了
  避免这件事；rviz 的 Frame Rate 也建议压到 10。
- **管线会静默停帧**：libcamera 在长时间运行后可能不再产帧。旧版脚本的
  裸 `while True: pull-sample()` 会因此空转吃满一个核。本节点用
  `watchdog_timeout` 重建管线，并把轮询放进 rclpy timer。
- **只有一颗 sensor**：设备树里只有后置 `s5kjn1`。前置摄像头在当前内核
  移植中**没有驱动、没有设备树节点、没有供电 regulator**，应用层无法启用，
  需要在 `s5kjn1` 之外新增 sensor 驱动 + CCI/CSIPHY 节点 + 上电序列。
- **libcamerasrc 没有 `num-buffers`**：限制帧数要写在 sink 上。

## 授权

Apache-2.0。

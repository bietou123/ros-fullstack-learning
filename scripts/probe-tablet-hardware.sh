#!/usr/bin/env bash
# 平板真机硬件探测（只读，不安装、不改配置）
set +e
echo "=== SYSTEM ==="
hostname; uname -a; cat /etc/os-release | grep -E "^(NAME|VERSION)"; uptime -p
echo "=== ROS ==="
ls /opt/ros 2>/dev/null; . /opt/ros/*/setup.bash 2>/dev/null; rosversion -d 2>/dev/null || echo "no rosversion"; command -v ros2 || echo "no ros2"
echo "=== VIDEO ==="
command -v v4l2-ctl >/dev/null && v4l2-ctl --list-devices 2>&1 | head -20 || echo "no v4l2-ctl"
ls -l /dev/video* 2>/dev/null || echo "no /dev/video*"
echo "=== IMU / IIO ==="
ls /sys/bus/iio/devices/ 2>/dev/null || echo "no iio"
for d in /sys/bus/iio/devices/iio:device*; do [ -e "$d/name" ] && echo "$(basename $d): $(cat $d/name 2>/dev/null)"; done
echo "=== SERIAL / USB ==="
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "no ttyUSB/ttyACM"
command -v lsusb >/dev/null && lsusb 2>&1 | head -20 || echo "no lsusb"
echo "=== NET ==="
ip -brief addr 2>/dev/null | head -10
echo "=== CAN ==="
ip -details link show type can 2>/dev/null | head -20 || echo "no can interface"
lsmod 2>/dev/null | grep -i can | head -10
echo "=== DISK / MEM ==="
df -h / | tail -1; free -h | head -2
echo "=== DOCKER ==="
command -v docker >/dev/null && docker --version 2>&1 || echo "no docker"
echo "PROBE_DONE"

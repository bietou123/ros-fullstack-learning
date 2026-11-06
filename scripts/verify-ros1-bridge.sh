#!/usr/bin/env bash
# Verify ros1_bridge with ROS 1 Noetic and ROS 2 Foxy in one container.
# The official ros:foxy-ros1-bridge image ships both distributions, so this
# exercises the same dynamic_bridge binary the course describes without
# requiring a real dual-ROS workstation.
set -euo pipefail

IMG="${ROS1_BRIDGE_IMAGE:-ros:foxy-ros1-bridge}"
NAME="rl-bridge-$$"
ROS1_SETUP="${ROS1_SETUP:-/opt/ros/noetic/setup.bash}"
ROS2_SETUP="${ROS2_SETUP:-/opt/ros/foxy/setup.bash}"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" "$IMG" sleep infinity >/dev/null

echo "ROS distros in image:"
docker exec "$NAME" bash -lc 'ls /opt/ros/'

docker exec "$NAME" bash -lc "test -f $ROS1_SETUP && test -f $ROS2_SETUP" || {
  echo "FAIL: expected $ROS1_SETUP and $ROS2_SETUP"; exit 1; }

docker exec -d "$NAME" bash -lc "source $ROS1_SETUP && roscore >/tmp/roscore.log 2>&1"

for i in $(seq 1 30); do
  if docker exec "$NAME" bash -lc "source $ROS1_SETUP && timeout 3 rosparam list 2>/dev/null | head -1" | grep -q .; then
    echo "ROSCORE_OK iter=$i"
    break
  fi
  sleep 1
done

docker exec -d "$NAME" bash -lc "source $ROS1_SETUP && source $ROS2_SETUP && ros2 run ros1_bridge dynamic_bridge --bridge-all-topics >/tmp/bridge.log 2>&1"
sleep 4

# ROS 1 -> ROS 2. Start the ROS 2 subscriber BEFORE the ROS 1 publisher so a
# discovery race cannot decide the result (Foxy's `ros2 topic echo` has no
# --once, so run it under timeout and poll the captured output).
docker exec -d "$NAME" bash -lc "source $ROS2_SETUP && PYTHONUNBUFFERED=1 timeout 30 ros2 topic echo /chatter std_msgs/msg/String >/tmp/echo1.log 2>&1"
sleep 3
docker exec -d "$NAME" bash -lc "source $ROS1_SETUP && rostopic pub -r 2 /chatter std_msgs/String 'data: from_ros1' >/tmp/pub1.log 2>&1"
for i in $(seq 1 20); do
  if docker exec "$NAME" bash -lc 'grep -q from_ros1 /tmp/echo1.log 2>/dev/null'; then
    echo "ROS2_GOT_ROS1_MSG iter=$i"
    break
  fi
  sleep 1
done
echo "ROS2 topic list:"; docker exec "$NAME" bash -lc "source $ROS2_SETUP && timeout 10 ros2 topic list -t" 2>&1 || true
echo "ROS2_FROM_ROS1:"; docker exec "$NAME" bash -lc 'cat /tmp/echo1.log' 2>&1 || true
echo "PUB1_LOG:"; docker exec "$NAME" bash -lc 'cat /tmp/pub1.log' 2>&1 || true

# ROS 2 -> ROS 1
docker exec -d "$NAME" bash -lc "source $ROS2_SETUP && ros2 topic pub -r 2 /chatter2 std_msgs/String '{data: from_ros2}' >/tmp/pub2.log 2>&1"
sleep 4
ROS1_FROM_ROS2="$(docker exec "$NAME" bash -lc "source $ROS1_SETUP && timeout 15 rostopic echo -n1 /chatter2" 2>&1 || true)"
echo "ROS1_FROM_ROS2:"; echo "$ROS1_FROM_ROS2"

echo "BRIDGE_LOG:"; docker exec "$NAME" bash -lc 'tail -n 15 /tmp/bridge.log' || true

fail=0
docker exec "$NAME" bash -lc 'grep -q from_ros1 /tmp/echo1.log' || { echo "FAIL: ROS1->ROS2 message not received"; fail=1; }
echo "$ROS1_FROM_ROS2" | grep -q "from_ros2" || { echo "FAIL: ROS2->ROS1 message not received"; fail=1; }
[ "$fail" -eq 0 ] && echo "ROS1_BRIDGE_OK" || exit 1

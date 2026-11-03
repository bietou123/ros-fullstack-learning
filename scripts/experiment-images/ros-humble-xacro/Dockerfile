FROM ros:humble-ros-base

# ros-base 不包含 xacro；S3-02 / S3-06 实验需要它
RUN apt-get update \
 && apt-get install -y --no-install-recommends ros-humble-xacro \
 && rm -rf /var/lib/apt/lists/*

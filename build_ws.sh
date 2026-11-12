#!/bin/bash -l
# Run INSIDE the container:  distrobox enter noetic -- bash ~/catkin_ws/env/build_ws.sh
# Installs rosdep dependencies and builds the workspace, skipping packages that
# need hardware/SDKs we don't have yet (ZED SDK, Robotiq).
set -e
cd ~/catkin_ws

sudo apt-get update
rosdep install --from-paths src --ignore-src -r -y \
    --skip-keys="zed_ros zed_nodelets zed_wrapper" || true

catkin config --init --extend /opt/ros/noetic -DCMAKE_BUILD_TYPE=Release
# Re-enable these when the ZED SDK / grippers are set up:
catkin config --blacklist zed_ros zed_nodelets zed_wrapper \
    $(ls -d src/robotiq/*/ | xargs -n1 basename)
catkin build

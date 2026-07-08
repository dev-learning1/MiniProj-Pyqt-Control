#!/bin/bash
# Nav2 + PyQt 대시보드를 한 번에 띄우는 편의 스크립트.
#
#   ./run.sh                       # 기본값으로 실행 (map: maps/last_class_map_modi.yaml)
#   ./run.sh map:=/path/other.yaml # 다른 맵 사용
#   ./run.sh use_rviz:=true        # RViz도 같이 띄우기
#
# 이 스크립트가 하는 일:
#   1. ROS2 humble + turtlebot3_ws 환경 source
#   2. TURTLEBOT3_MODEL이 안 정해져 있으면 burger로 기본 설정
#   3. Nav2 + 대시보드 launch 실행 (인자는 그대로 전달)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source /opt/ros/humble/setup.bash
source ~/turtlebot3_ws/install/setup.bash

: "${TURTLEBOT3_MODEL:=burger}"
export TURTLEBOT3_MODEL

exec ros2 launch "${SCRIPT_DIR}/launch/dashboard_bringup.launch.py" "$@"

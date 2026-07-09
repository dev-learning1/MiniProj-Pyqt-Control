#!/usr/bin/env python3
"""터틀봇3 대시보드 실행 진입점.

실행 전 ROS2 환경을 source 해야 합니다:
    source /opt/ros/humble/setup.bash
    source ~/turtlebot3_ws/install/setup.bash
    export TURTLEBOT3_MODEL=burger
    python3 main.py
"""
import sys

from PyQt5.QtWidgets import QApplication

from dashboard.main_window import MainWindow
from dashboard import theme


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.APP_STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

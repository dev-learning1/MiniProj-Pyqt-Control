"""터틀봇3 대시보드 메인 윈도우."""
import math
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QMainWindow, QTabWidget, QLabel, QWidget, QVBoxLayout

from dashboard.ros_bridge import RosBridge, RosThread
from dashboard.widgets.status_panel import StatusPanel
from dashboard.widgets.control_panel import ControlPanel
from dashboard.widgets.log_panel import LogPanel
from dashboard.widgets.nav_panel import NavPanel
from dashboard.widgets.map_panel import MapPanel
from dashboard.widgets.ssh_panel import SshPanel

LOW_BATTERY_THRESHOLD = 0.2
OBSTACLE_WARN_DISTANCE_M = 0.3

LINK_NAME_KO = {
    'odom': 'Odometry',
    'battery_state': '배터리',
    'scan': 'LiDAR',
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        model = os.environ.get("TURTLEBOT3_MODEL", "알 수 없음")
        self.setWindowTitle(f"TurtleBot3 Dashboard ({model})")
        self.resize(900, 650)

        self.bridge = RosBridge()
        self.ros_thread = RosThread(self.bridge)

        self.status_panel = StatusPanel()
        self.control_panel = ControlPanel()
        self.map_panel = MapPanel()
        self.nav_panel = NavPanel()
        self.log_panel = LogPanel()
        self.ssh_panel = SshPanel()

        tabs = QTabWidget()
        tabs.addTab(self.status_panel, "로봇 상태")
        tabs.addTab(self.control_panel, "동작 컨트롤")
        tabs.addTab(self.map_panel, "맵 / 웨이포인트 생성")
        tabs.addTab(self.nav_panel, "웨이포인트 주행")
        tabs.addTab(self.log_panel, "이벤트 로그")

        self.header_label = QLabel("ROS2 노드 초기화 중...")
        self.header_label.setStyleSheet("padding: 6px; font-weight: bold;")

        central = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.ssh_panel)
        layout.addWidget(self.header_label)
        layout.addWidget(tabs)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._battery_low_notified = False
        self._obstacle_notified = False
        self._link_status = {key: 'down' for key in LINK_NAME_KO}

        self._connect_signals()

        self.ros_thread.node_ready.connect(self._on_node_ready)
        self.ros_thread.start()

        self.log_panel.add_event("INFO", "대시보드를 시작했습니다.")

    def _connect_signals(self):
        self.bridge.battery_updated.connect(self._on_battery)
        self.bridge.odom_updated.connect(self.status_panel.set_odom)
        self.bridge.scan_updated.connect(self._on_scan)
        self.bridge.link_state_changed.connect(self._on_link_state_changed)
        self.bridge.log_event.connect(self.log_panel.add_event)
        self.bridge.nav_status_changed.connect(self.nav_panel.set_status)
        self.bridge.nav_feedback.connect(self._on_nav_feedback)
        self.bridge.waypoint_progress.connect(self._on_waypoint_progress)

        self.control_panel.velocity_requested.connect(self._on_velocity_requested)
        self.control_panel.log_requested.connect(self.log_panel.add_event)

        self.nav_panel.navigate_requested.connect(self._on_navigate_requested)
        self.nav_panel.follow_requested.connect(self._on_follow_requested)
        self.nav_panel.cancel_requested.connect(self._on_cancel_requested)
        self.nav_panel.log_requested.connect(self.log_panel.add_event)

        self.map_panel.log_requested.connect(self.log_panel.add_event)
        self.map_panel.saved_to.connect(self.nav_panel.load_from_path)
        self.map_panel.initial_pose_requested.connect(self._on_initial_pose_requested)

        self.ssh_panel.log_requested.connect(self.log_panel.add_event)

    def _on_node_ready(self):
        self._update_header()

    def _update_header(self):
        model = os.environ.get("TURTLEBOT3_MODEL", "알 수 없음")
        domain_id = os.environ.get("ROS_DOMAIN_ID", "0")
        down = [LINK_NAME_KO[k] for k, state in self._link_status.items() if state == 'down']
        unstable = [LINK_NAME_KO[k] for k, state in self._link_status.items() if state == 'unstable']
        if not down and not unstable:
            state_text = "모든 토픽 정상 수신 중"
        else:
            parts = []
            if down:
                parts.append(f"연결 끊김: {', '.join(down)}")
            if unstable:
                parts.append(f"연결 이상: {', '.join(unstable)}")
            state_text = " / ".join(parts)
        self.header_label.setText(
            f"모델: {model}  |  ROS_DOMAIN_ID: {domain_id}  |  {state_text}"
        )

    def _on_battery(self, percentage: float, voltage: float):
        self.status_panel.set_battery(percentage, voltage)
        if percentage <= LOW_BATTERY_THRESHOLD:
            if not self._battery_low_notified:
                self._battery_low_notified = True
                self.log_panel.add_event(
                    "WARN", f"배터리 잔량이 낮습니다: {percentage * 100:.0f}%"
                )
        else:
            self._battery_low_notified = False

    def _on_scan(self, min_range: float):
        self.status_panel.set_scan_min(min_range)
        if not math.isinf(min_range) and min_range < OBSTACLE_WARN_DISTANCE_M:
            if not self._obstacle_notified:
                self._obstacle_notified = True
                self.log_panel.add_event(
                    "WARN", f"장애물이 가까이 있습니다: {min_range:.2f} m"
                )
        else:
            self._obstacle_notified = False

    _LINK_STATE_LOG = {
        'up': ("INFO", "연결됨"),
        'unstable': ("WARN", "연결 불안정 (수신 지연)"),
        'down': ("ERROR", "연결 끊김"),
    }

    def _on_link_state_changed(self, key: str, state: str):
        self.status_panel.set_link_state(key, state)
        self._link_status[key] = state
        self._update_header()
        name = LINK_NAME_KO.get(key, key)
        level, text = self._LINK_STATE_LOG.get(state, ("ERROR", state))
        self.log_panel.add_event(level, f"{name} {text}")

    def _on_velocity_requested(self, linear: float, angular: float):
        node = self.ros_thread.node
        if node is not None:
            node.send_velocity(linear, angular)

    def _on_navigate_requested(self, x: float, y: float, yaw: float, frame_id: str):
        node = self.ros_thread.node
        if node is not None:
            node.navigate_to_pose(x, y, yaw, frame_id)

    def _on_follow_requested(self, poses: list, frame_id: str):
        node = self.ros_thread.node
        if node is not None:
            node.follow_waypoints(poses, frame_id)

    def _on_cancel_requested(self):
        node = self.ros_thread.node
        if node is not None:
            node.cancel_current_goal()

    def _on_initial_pose_requested(self, x: float, y: float, yaw: float, frame_id: str):
        node = self.ros_thread.node
        if node is not None:
            node.publish_initial_pose(x, y, yaw, frame_id)

    def _on_nav_feedback(self, distance_remaining: float):
        self.nav_panel.set_status(f"목적지까지 남은 거리: {distance_remaining:.2f} m")

    def _on_waypoint_progress(self, current: int, total: int):
        self.nav_panel.set_status(f"경로 주행 중 ({current}/{total})")

    def closeEvent(self, event):
        node = self.ros_thread.node
        if node is not None:
            node.stop_robot()
        self.ros_thread.stop()
        # 로컬 SSH 작업 스레드만 정리 — 로봇의 원격 bringup은 그대로 계속 실행됨
        self.ssh_panel.wait_for_pending_ssh()
        super().closeEvent(event)

"""로봇 상태 모니터링 패널."""
import math

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QGroupBox, QLabel, QProgressBar, QVBoxLayout, QFormLayout
)

OBSTACLE_WARN_DISTANCE_M = 0.3


def _link_label(name: str) -> QLabel:
    label = QLabel(name)
    label.setStyleSheet("color: white; background-color: #888; padding: 2px 8px; border-radius: 4px;")
    return label


class StatusPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.link_labels = {
            'odom': _link_label('ODOM'),
            'battery_state': _link_label('BATTERY'),
            'scan': _link_label('LIDAR'),
        }

        link_box = QGroupBox("연결 상태")
        link_layout = QGridLayout()
        for i, (key, label) in enumerate(self.link_labels.items()):
            link_layout.addWidget(label, 0, i)
        link_box.setLayout(link_layout)

        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setFormat("%p%")
        self.battery_voltage_label = QLabel("- V")
        self._battery_pct_display = None

        battery_box = QGroupBox("배터리")
        battery_layout = QVBoxLayout()
        battery_layout.addWidget(self.battery_bar)
        battery_layout.addWidget(self.battery_voltage_label)
        battery_box.setLayout(battery_layout)

        self.pose_x_label = QLabel("0.00 m")
        self.pose_y_label = QLabel("0.00 m")
        self.pose_yaw_label = QLabel("0.0 °")
        self.lin_vel_label = QLabel("0.00 m/s")
        self.ang_vel_label = QLabel("0.00 rad/s")

        pose_box = QGroupBox("위치 / 속도 (odom)")
        pose_layout = QFormLayout()
        pose_layout.addRow("X:", self.pose_x_label)
        pose_layout.addRow("Y:", self.pose_y_label)
        pose_layout.addRow("Yaw:", self.pose_yaw_label)
        pose_layout.addRow("선속도:", self.lin_vel_label)
        pose_layout.addRow("각속도:", self.ang_vel_label)
        pose_box.setLayout(pose_layout)

        self.lidar_min_label = QLabel("- m")
        self.lidar_min_label.setStyleSheet("font-weight: bold;")

        lidar_box = QGroupBox("LiDAR 최소 거리")
        lidar_layout = QVBoxLayout()
        lidar_layout.addWidget(self.lidar_min_label)
        lidar_box.setLayout(lidar_layout)

        root = QGridLayout()
        root.addWidget(link_box, 0, 0, 1, 2)
        root.addWidget(battery_box, 1, 0)
        root.addWidget(lidar_box, 1, 1)
        root.addWidget(pose_box, 2, 0, 1, 2)
        root.setRowStretch(3, 1)
        self.setLayout(root)

    _LINK_STATE_COLOR = {
        'up': "#2e7d32",       # 정상 수신 중: 초록
        'unstable': "#c62828",  # 연결됐지만 수신 지연/불안정: 빨강
        'down': "#888888",      # 연결 끊김: 회색
    }

    def set_link_state(self, key: str, state: str):
        label = self.link_labels.get(key)
        if label is None:
            return
        color = self._LINK_STATE_COLOR.get(state, self._LINK_STATE_COLOR['down'])
        label.setStyleSheet(
            f"color: white; background-color: {color}; padding: 2px 8px; border-radius: 4px;"
        )

    # 정수 경계(예: 81.5%) 근처에서 값이 미세하게 오르내리면 round()가 그때마다
    # 다른 정수를 내놓아 표시가 떨린다. 이미 표시 중인 값에서 이 폭 이상
    # 벗어나야만 표시를 갱신하는 히스테리시스를 둬서 막는다.
    _BATTERY_PCT_HYSTERESIS = 0.75

    def set_battery(self, percentage: float, voltage: float):
        raw_pct = max(0.0, min(100.0, percentage * 100))
        if (
            self._battery_pct_display is None
            or abs(raw_pct - self._battery_pct_display) >= 0.5 + self._BATTERY_PCT_HYSTERESIS
        ):
            self._battery_pct_display = round(raw_pct)
        pct = self._battery_pct_display
        self.battery_bar.setValue(pct)
        if pct <= 15:
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: #c62828; }")
        elif pct <= 30:
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: #f9a825; }")
        else:
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: #2e7d32; }")
        self.battery_voltage_label.setText(f"{voltage:.2f} V")

    def set_odom(self, x: float, y: float, yaw: float, lin_vel: float, ang_vel: float):
        self.pose_x_label.setText(f"{x:.2f} m")
        self.pose_y_label.setText(f"{y:.2f} m")
        self.pose_yaw_label.setText(f"{math.degrees(yaw):.1f} °")
        self.lin_vel_label.setText(f"{lin_vel:.2f} m/s")
        self.ang_vel_label.setText(f"{ang_vel:.2f} rad/s")

    def set_scan_min(self, min_range: float):
        if math.isinf(min_range):
            self.lidar_min_label.setText("- m")
            self.lidar_min_label.setStyleSheet("font-weight: bold;")
            return
        self.lidar_min_label.setText(f"{min_range:.2f} m")
        if min_range < OBSTACLE_WARN_DISTANCE_M:
            self.lidar_min_label.setStyleSheet("font-weight: bold; color: #c62828;")
        else:
            self.lidar_min_label.setStyleSheet("font-weight: bold; color: #2e7d32;")

"""로봇 상태 모니터링 패널.

항상 화면 상단에 고정 노출되는 패널이라, 카드(QGroupBox)형 레이아웃 대신
얇은 두 줄짜리 바(bar) 형태로 최소한의 공간만 차지하도록 구성한다.
"""
import math

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QFrame

from dashboard import theme

OBSTACLE_WARN_DISTANCE_M = 0.3


def _link_label(name: str) -> QLabel:
    label = QLabel(name)
    label.setStyleSheet(theme.pill_qss(theme.GRAY_BG, theme.GRAY_TEXT))
    return label


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {theme.TEXT_SECONDARY}; font-weight: 600; font-size: 8pt;"
    )
    return label


def _mono_label(text: str, color: str = theme.TEXT_PRIMARY) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(theme.mono_label_qss(color) + "font-size: 9pt;")
    return label


def _fmt_zero_safe(value: float, decimals: int) -> str:
    """반올림 결과가 0이면 부호를 지운다.

    로봇이 정지 상태여도 센서 노이즈로 값이 0 근처에서 미세하게 +/-를
    오가면, round() 결과가 -0.0이 되어 "-0.00"과 "0.00"이 번갈아 표시되며
    떨려 보인다. 반올림 후 0이면 음수 0을 양수 0으로 정규화해 막는다.
    """
    rounded = round(value, decimals)
    if rounded == 0:
        rounded = 0.0
    return f"{rounded:.{decimals}f}"


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setStyleSheet(f"color: {theme.BORDER};")
    return line


class StatusPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet(
            f"StatusPanel {{ background-color: {theme.BG_SURFACE}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 8px; }}"
        )

        self.link_labels = {
            'odom': _link_label('ODOM'),
            'battery_state': _link_label('BATTERY'),
            'scan': _link_label('LIDAR'),
        }

        links_row = QHBoxLayout()
        links_row.setSpacing(6)
        for label in self.link_labels.values():
            links_row.addWidget(label)

        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setFormat("%p%")
        self.battery_bar.setFixedWidth(120)
        self.battery_bar.setFixedHeight(16)
        self.battery_voltage_label = _mono_label("- V")
        self._battery_pct_display = None

        battery_row = QHBoxLayout()
        battery_row.setSpacing(6)
        battery_row.addWidget(_caption("배터리"))
        battery_row.addWidget(self.battery_bar)
        battery_row.addWidget(self.battery_voltage_label)

        self.lidar_min_label = _mono_label("- m")

        lidar_row = QHBoxLayout()
        lidar_row.setSpacing(6)
        lidar_row.addWidget(_caption("LiDAR"))
        lidar_row.addWidget(self.lidar_min_label)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        top_row.addLayout(links_row)
        top_row.addWidget(_divider())
        top_row.addLayout(battery_row)
        top_row.addWidget(_divider())
        top_row.addLayout(lidar_row)
        top_row.addStretch(1)

        self.pose_x_label = _mono_label("0.00 m")
        self.pose_y_label = _mono_label("0.00 m")
        self.pose_yaw_label = _mono_label("0.0 °")
        self.lin_vel_label = _mono_label("0.00 m/s")
        self.ang_vel_label = _mono_label("0.00 rad/s")

        pose_row = QHBoxLayout()
        pose_row.setSpacing(12)
        for caption, value_label in (
            ("X", self.pose_x_label),
            ("Y", self.pose_y_label),
            ("Yaw", self.pose_yaw_label),
            ("선속도", self.lin_vel_label),
            ("각속도", self.ang_vel_label),
        ):
            pair = QHBoxLayout()
            pair.setSpacing(4)
            pair.addWidget(_caption(caption))
            pair.addWidget(value_label)
            pose_row.addLayout(pair)
        pose_row.addStretch(1)

        root = QVBoxLayout()
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)
        root.addLayout(top_row)
        root.addLayout(pose_row)
        self.setLayout(root)

    _LINK_STATE_COLOR = {
        'up': (theme.GREEN_BG, theme.GREEN_TEXT),        # 정상 수신 중
        'unstable': (theme.RED_BG, theme.RED_TEXT),        # 연결됐지만 수신 지연/불안정
        'down': (theme.GRAY_BG, theme.GRAY_TEXT),          # 연결 끊김
    }

    def set_link_state(self, key: str, state: str):
        label = self.link_labels.get(key)
        if label is None:
            return
        bg, text = self._LINK_STATE_COLOR.get(state, self._LINK_STATE_COLOR['down'])
        label.setStyleSheet(theme.pill_qss(bg, text))

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
            fill = theme.RED_TEXT
        elif pct <= 30:
            fill = theme.AMBER_TEXT
        else:
            fill = theme.GREEN_TEXT
        self.battery_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {fill}; }}")
        self.battery_voltage_label.setText(f"{voltage:.2f} V")

    def set_odom(self, x: float, y: float, yaw: float, lin_vel: float, ang_vel: float):
        self.pose_x_label.setText(f"{_fmt_zero_safe(x, 2)} m")
        self.pose_y_label.setText(f"{_fmt_zero_safe(y, 2)} m")
        self.pose_yaw_label.setText(f"{_fmt_zero_safe(math.degrees(yaw), 1)} °")
        self.lin_vel_label.setText(f"{_fmt_zero_safe(lin_vel, 2)} m/s")
        self.ang_vel_label.setText(f"{_fmt_zero_safe(ang_vel, 2)} rad/s")

    def set_scan_min(self, min_range: float):
        if math.isinf(min_range):
            self.lidar_min_label.setText("- m")
            self.lidar_min_label.setStyleSheet(theme.mono_label_qss() + "font-size: 9pt;")
            return
        self.lidar_min_label.setText(f"{min_range:.2f} m")
        color = theme.RED_TEXT if min_range < OBSTACLE_WARN_DISTANCE_M else theme.GREEN_TEXT
        self.lidar_min_label.setStyleSheet(theme.mono_label_qss(color) + "font-size: 9pt;")

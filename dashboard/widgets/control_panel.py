"""로봇 동작 컨트롤 패널: 버�온/키보드(WASD, 방향키)로 cmd_vel 전송."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QSlider, QSizePolicy, QScrollArea
)

from dashboard import theme

DEFAULT_MAX_LINEAR = 0.22   # m/s, turtlebot3 burger 기준
DEFAULT_MAX_ANGULAR = 2.84  # rad/s, turtlebot3 burger 기준


def _dir_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setMinimumSize(70, 50)
    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return btn


class ControlPanel(QWidget):
    velocity_requested = pyqtSignal(float, float)  # linear, angular
    log_requested = pyqtSignal(str, str)           # level, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

        self._linear = 0.0
        self._angular = 0.0
        self.max_linear = DEFAULT_MAX_LINEAR
        self.max_angular = DEFAULT_MAX_ANGULAR

        hint = QLabel("방향 버튼 클릭(누르고 있기) 또는 이 패널에 포커스 후 방향키/W A S D 로 조작하세요.")
        hint.setWordWrap(True)

        self.btn_forward = _dir_button("▲\n전진")
        self.btn_backward = _dir_button("▼\n후진")
        self.btn_left = _dir_button("◀\n좌회전")
        self.btn_right = _dir_button("▶\n우회전")
        self.btn_stop = QPushButton("정지")
        self.btn_stop.setMinimumHeight(50)

        pad = QGridLayout()
        pad.addWidget(self.btn_forward, 0, 1)
        pad.addWidget(self.btn_left, 1, 0)
        pad.addWidget(self.btn_stop, 1, 1)
        pad.addWidget(self.btn_right, 1, 2)
        pad.addWidget(self.btn_backward, 2, 1)
        pad_box = QGroupBox("이동")
        pad_box.setLayout(pad)

        self.linear_slider = QSlider(Qt.Horizontal)
        self.linear_slider.setRange(10, 100)
        self.linear_slider.setValue(60)
        self.linear_speed_label = QLabel()

        self.angular_slider = QSlider(Qt.Horizontal)
        self.angular_slider.setRange(10, 100)
        self.angular_slider.setValue(60)
        self.angular_speed_label = QLabel()

        speed_layout = QVBoxLayout()
        speed_layout.addWidget(QLabel("선속도 한계"))
        row1 = QHBoxLayout()
        row1.addWidget(self.linear_slider)
        row1.addWidget(self.linear_speed_label)
        speed_layout.addLayout(row1)
        speed_layout.addWidget(QLabel("각속도 한계"))
        row2 = QHBoxLayout()
        row2.addWidget(self.angular_slider)
        row2.addWidget(self.angular_speed_label)
        speed_layout.addLayout(row2)
        speed_box = QGroupBox("속도 설정 (%)")
        speed_box.setLayout(speed_layout)

        self.btn_emergency = QPushButton("비상 정지")
        self.btn_emergency.setMinimumHeight(60)
        self.btn_emergency.setStyleSheet(
            f"background-color: {theme.DANGER_SOLID}; color: white; "
            "font-weight: 700; font-size: 16px; border-radius: 8px;"
        )

        root = QVBoxLayout()
        root.addWidget(hint)
        root.addWidget(pad_box)
        root.addWidget(speed_box)
        root.addWidget(self.btn_emergency)
        root.addStretch(1)

        content = QWidget()
        content.setLayout(root)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)

        self._update_speed_labels()

        self.linear_slider.valueChanged.connect(self._update_speed_labels)
        self.angular_slider.valueChanged.connect(self._update_speed_labels)

        self.btn_forward.pressed.connect(lambda: self._set_linear(1))
        self.btn_forward.released.connect(lambda: self._set_linear(0))
        self.btn_backward.pressed.connect(lambda: self._set_linear(-1))
        self.btn_backward.released.connect(lambda: self._set_linear(0))
        self.btn_left.pressed.connect(lambda: self._set_angular(1))
        self.btn_left.released.connect(lambda: self._set_angular(0))
        self.btn_right.pressed.connect(lambda: self._set_angular(-1))
        self.btn_right.released.connect(lambda: self._set_angular(0))
        self.btn_stop.clicked.connect(self._stop)
        self.btn_emergency.clicked.connect(self._emergency_stop)

    def _update_speed_labels(self):
        self.linear_speed_label.setText(f"{self.linear_slider.value()}%  "
                                         f"({self._current_max_linear():.2f} m/s)")
        self.angular_speed_label.setText(f"{self.angular_slider.value()}%  "
                                          f"({self._current_max_angular():.2f} rad/s)")

    def _current_max_linear(self) -> float:
        return self.max_linear * (self.linear_slider.value() / 100.0)

    def _current_max_angular(self) -> float:
        return self.max_angular * (self.angular_slider.value() / 100.0)

    def _set_linear(self, direction: int):
        self._linear = direction * self._current_max_linear()
        self._publish()

    def _set_angular(self, direction: int):
        self._angular = direction * self._current_max_angular()
        self._publish()

    def _publish(self):
        self.velocity_requested.emit(self._linear, self._angular)

    def _stop(self):
        self._linear = 0.0
        self._angular = 0.0
        self._publish()

    def _emergency_stop(self):
        self._stop()
        self.log_requested.emit("WARN", "비상 정지가 실행되었습니다.")

    # --- 키보드 조작 (방향키 / WASD) ---
    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_W):
            self._set_linear(1)
        elif key in (Qt.Key_Down, Qt.Key_S):
            self._set_linear(-1)
        elif key in (Qt.Key_Left, Qt.Key_A):
            self._set_angular(1)
        elif key in (Qt.Key_Right, Qt.Key_D):
            self._set_angular(-1)
        elif key == Qt.Key_Space:
            self._stop()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_W, Qt.Key_Down, Qt.Key_S):
            self._set_linear(0)
        elif key in (Qt.Key_Left, Qt.Key_A, Qt.Key_Right, Qt.Key_D):
            self._set_angular(0)
        else:
            super().keyReleaseEvent(event)

"""대시보드에서 로봇에 SSH로 접속해 bringup을 원격 실행하는 패널."""
import os

import paramiko
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QGroupBox, QLabel, QLineEdit, QPushButton
)

# 원격에서 bringup이 이미 떠 있는지 확인하는 패턴.
# 같은 로봇에서 bringup이 중복 실행되면 모터/라이다가 겹쳐 충돌할 수 있어,
# 이미 떠 있으면(다른 팀원 또는 이전 세션) 새로 띄우지 않는다.
# 패턴 첫 글자를 문자 클래스로 감싸("t" -> "[t]") pgrep -f가 이 명령 자신을
# 실행하는 셸(커맨드라인에 이 패턴 문자열이 그대로 들어있음)을 오탐하지 않게 한다.
_CHECK_CMD = 'pgrep -f "[t]urtlebot3_bringup.*robot.launch.py" >/dev/null 2>&1; echo $?'

# setsid + nohup + stdin/stdout/stderr 분리로 SSH 세션이 끊기거나
# 대시보드를 꺼도 원격 bringup 프로세스가 같이 죽지 않도록 한다.
#
# exec_command로 실행되는 셸은 로그인/인터랙티브 셸이 아니라 ~/.bashrc를 읽지
# 않는다. turtlebot3_bringup은 LDS_MODEL 등을 .bashrc의 export에 의존하므로,
# 여기서 필요한 환경변수를 직접 export해줘야 한다(안 그러면 KeyError로 조용히
# launch가 실패하는데, pgrep 오탐과 겹치면 "이미 실행 중"으로만 보이고 아무
# 로그도 안 남는 것처럼 보일 수 있다).
_LAUNCH_CMD_TMPL = (
    "setsid nohup bash -c '"
    "source /opt/ros/humble/setup.bash; "
    "[ -f ~/turtlebot3_ws/install/setup.bash ] && source ~/turtlebot3_ws/install/setup.bash; "
    "export TURTLEBOT3_MODEL={model}; "
    "export LDS_MODEL={lds_model}; "
    "export ROS_DOMAIN_ID={domain_id}; "
    "exec ros2 launch turtlebot3_bringup robot.launch.py"
    "' > $HOME/bringup_dashboard.log 2>&1 < /dev/null &\n"
    "disown"
)

# 음성 안내 노드(tb3_voice_notifier)가 이미 떠 있는지 확인하는 패턴.
# _CHECK_CMD와 마찬가지로 첫 글자를 문자 클래스로 감싸 자기 자신을 오탐하지 않게 한다.
_VOICE_CHECK_CMD = 'pgrep -f "[v]oice_notifier" >/dev/null 2>&1; echo $?'

# run_voice.sh와 동일한 방식으로 음성 안내 노드를 백그라운드 실행.
# bringup과 같은 ROS_DOMAIN_ID로 띄워야 서로 같은 DDS 그래프에서 보인다
# (안 그러면 기본값 도메인 0으로 떠서 bringup/대시보드와 서로 못 본다).
_VOICE_LAUNCH_CMD_TMPL = (
    "setsid nohup bash -c '"
    "source /opt/ros/humble/setup.bash; "
    "source ~/ros2_ws/install/setup.bash; "
    "export ROS_DOMAIN_ID={domain_id}; "
    "exec ros2 run tb3_voice voice_notifier"
    "' > $HOME/voice_dashboard.log 2>&1 < /dev/null &\n"
    "disown"
)

# bringup을 새로 띄울 때마다 "로봇 동작이 가능합니다" 안내.
# ~/tb3_voice/tools/announce_system_ready.py가 get_subscription_count()로
# voice_notifier 구독을 직접 확인한 뒤(ros2 daemon과 무관, `ros2 topic pub`
# 보다 안정적) 발행하고, publish() 직후 바로 종료하지 않고 잠깐 더 spin해서
# reliable QoS 전송이 실제로 끝날 시간을 준다(안 그러면 매칭 직후 첫 메시지가
# 유실될 수 있었다).
_SYSTEM_READY_ANNOUNCE_CMD_TMPL = (
    "setsid nohup bash -c '"
    "source /opt/ros/humble/setup.bash; "
    "source ~/ros2_ws/install/setup.bash; "
    "export ROS_DOMAIN_ID={domain_id}; "
    "python3 ~/tb3_voice/tools/announce_system_ready.py"
    "' > $HOME/voice_announce.log 2>&1 < /dev/null &\n"
    "disown"
)


def _resolve_ssh_target(host_input: str):
    """~/.ssh/config에 등록된 Host 별칭이면 실제 hostname/user/port로 풀어준다."""
    hostname, username, port = host_input, os.environ.get('USER', 'root'), 22
    config_path = os.path.expanduser('~/.ssh/config')
    if os.path.exists(config_path):
        ssh_config = paramiko.SSHConfig()
        with open(config_path) as f:
            ssh_config.parse(f)
        resolved = ssh_config.lookup(host_input)
        hostname = resolved.get('hostname', hostname)
        username = resolved.get('user', username)
        port = int(resolved.get('port', port))
    return hostname, username, port


class SshBringupWorker(QThread):
    progress = pyqtSignal(str)
    finished_result = pyqtSignal(bool, str)  # success, message

    def __init__(self, host_input: str, password: str, parent=None):
        super().__init__(parent)
        self._host_input = host_input
        self._password = password

    def run(self):
        hostname, username, port = _resolve_ssh_target(self._host_input)

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.progress.emit(f"{username}@{hostname}에 접속 중...")
            client.connect(
                hostname=hostname, port=port, username=username,
                password=self._password, timeout=8,
                look_for_keys=False, allow_agent=False,
            )
        except paramiko.AuthenticationException:
            self.finished_result.emit(False, "인증 실패: 비밀번호를 확인하세요.")
            return
        except Exception as exc:
            self.finished_result.emit(False, f"SSH 접속 실패: {exc}")
            return

        try:
            self.progress.emit("연결됨. bringup 상태 확인 중...")
            _stdin, stdout, _stderr = client.exec_command(_CHECK_CMD, timeout=8)
            bringup_already_running = stdout.read().decode().strip() == '0'

            # bringup/음성 노드 모두 같은 도메인에 떠야 서로/대시보드와 보인다.
            domain_id = os.environ.get('ROS_DOMAIN_ID', '50')

            if bringup_already_running:
                message = "로봇에 bringup이 이미 실행 중입니다 (새로 띄우지 않음)."
            else:
                self.progress.emit("bringup이 꺼져 있어 로봇에서 새로 실행합니다...")
                model = os.environ.get('TURTLEBOT3_MODEL', 'burger')
                lds_model = os.environ.get('LDS_MODEL', 'LDS-03')
                launch_cmd = _LAUNCH_CMD_TMPL.format(
                    model=model, lds_model=lds_model, domain_id=domain_id
                )
                client.exec_command(launch_cmd, timeout=8)
                message = "로봇에서 bringup을 새로 실행했습니다."

            self.progress.emit("음성 안내 노드 상태 확인 중...")
            _stdin, stdout, _stderr = client.exec_command(_VOICE_CHECK_CMD, timeout=8)
            voice_already_running = stdout.read().decode().strip() == '0'

            if not voice_already_running:
                self.progress.emit("음성 안내 노드를 새로 실행합니다...")
                client.exec_command(
                    _VOICE_LAUNCH_CMD_TMPL.format(domain_id=domain_id), timeout=8
                )

            if not bringup_already_running:
                # bringup을 이번에 새로 띄운 경우 매번 "로봇 동작이 가능합니다" 안내.
                # (voice_notifier 자체는 상시 프로세스로 두고 재시작하지 않아도 됨)
                client.exec_command(
                    _SYSTEM_READY_ANNOUNCE_CMD_TMPL.format(domain_id=domain_id), timeout=8
                )

            self.finished_result.emit(True, message)
        except Exception as exc:
            self.finished_result.emit(False, f"원격 명령 실행 실패: {exc}")
        finally:
            client.close()


class SshPanel(QWidget):
    log_requested = pyqtSignal(str, str)  # level, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: SshBringupWorker | None = None

        self.host_edit = QLineEdit("aurix")
        self.host_edit.setMaximumWidth(140)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setMaximumWidth(140)
        self.password_edit.returnPressed.connect(self._on_connect_clicked)

        self.connect_btn = QPushButton("연결 && Bringup 실행")
        self.connect_btn.clicked.connect(self._on_connect_clicked)

        self.status_label = QLabel("아직 연결 안 됨")
        self.status_label.setStyleSheet("color: #888;")

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Host:"))
        layout.addWidget(self.host_edit)
        layout.addWidget(QLabel("Password:"))
        layout.addWidget(self.password_edit)
        layout.addWidget(self.connect_btn)
        layout.addWidget(self.status_label, 1)

        box = QGroupBox("로봇 연결 (SSH Bringup)")
        box.setLayout(layout)

        outer = QHBoxLayout()
        outer.addWidget(box)
        outer.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer)

    def _on_connect_clicked(self):
        if self._worker is not None and self._worker.isRunning():
            return
        host_input = self.host_edit.text().strip()
        password = self.password_edit.text()
        if not host_input:
            self.status_label.setText("Host를 입력하세요.")
            return

        self.connect_btn.setEnabled(False)
        self._set_status("연결 시도 중...", "#888")

        self._worker = SshBringupWorker(host_input, password, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_result.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, message: str):
        self._set_status(message, "#888")
        self.log_requested.emit("INFO", f"[SSH] {message}")

    def _on_finished(self, success: bool, message: str):
        self._set_status(message, "#2e7d32" if success else "#c62828")
        self.log_requested.emit("INFO" if success else "ERROR", f"[SSH] {message}")
        self.connect_btn.setEnabled(True)
        self.password_edit.clear()

    def _set_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def wait_for_pending_ssh(self):
        """대시보드 종료 시 로컬 SSH 작업 스레드만 정리한다.

        로봇 쪽 원격 bringup 프로세스는 setsid+nohup+disown으로 이미
        이 스레드/대시보드와 분리되어 있으므로 여기서 건드리지 않는다.
        대시보드를 꺼도 로봇의 bringup은 계속 실행 상태로 남아야 하며,
        끄는 것은 사용자가 로봇에 직접 접속해 수동으로 한다.
        """
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)

# TurtleBot3 PyQt5 Dashboard

터틀봇3의 상태 모니터링, 동작 컨트롤, 이벤트 로그를 확인할 수 있는 PyQt5 대시보드입니다.

## 구성

- `main.py` : 실행 진입점
- `dashboard/ros_bridge.py` : rclpy 노드 (백그라운드 QThread에서 spin) — `/odom`, `/battery_state`, `/scan` 구독, `/cmd_vel` 발행
- `dashboard/main_window.py` : 메인 윈도우, 탭 구성 및 시그널 연결
- `dashboard/widgets/status_panel.py` : 연결 상태 / 배터리 / 위치·속도 / LiDAR 최소 거리
- `dashboard/widgets/control_panel.py` : 방향 버튼 + 키보드(방향키, WASD) 조작, 속도 슬라이더, 비상 정지
- `dashboard/widgets/log_panel.py` : 이벤트 로그 (연결 변화, 저배터리·장애물 경고, 사용자 조작 기록), 저장 기능
- `dashboard/waypoints.py` : waypoint/trajectory YAML 로더 및 저장
- `dashboard/map_loader.py` : nav2 map_server YAML+PGM 로더, 픽셀<->world 좌표 변환
- `dashboard/widgets/nav_panel.py` : 웨이포인트 주행 탭 — YAML 로드, waypoint/trajectory 콤보박스, 주행/중지 버튼
- `dashboard/widgets/map_panel.py` : 맵/웨이포인트 생성 탭 — 맵 표시, 클릭+드래그로 waypoint 생성, trajectory 구성, YAML 저장
- `dashboard/widgets/ssh_panel.py` : 상단 SSH 연결 패널 — 로봇 host/비밀번호 입력 후 접속하면 원격 bringup을 자동 확인/실행
- Nav2 액션 클라이언트는 `dashboard/ros_bridge.py`의 `TurtlebotNode`에 포함 (`/navigate_to_pose`, `/follow_waypoints`)
- `launch/dashboard_bringup.launch.py` : Nav2 + 대시보드를 한 번에 띄우는 launch 파일
- `run.sh` : ROS2 환경 source + launch까지 한 번에 하는 편의 스크립트

## 실행 방법

### 방법 A — Nav2 주행까지 한 번에 (권장)

터틀봇3 bringup(`ros2 launch turtlebot3_bringup robot.launch.py`)이 이미 켜져 있는 상태에서 (아직 안 켜져 있다면 대시보드가 뜬 뒤 상단 SSH 패널로 원격 실행할 수 있습니다 — 아래 [로봇 원격 Bringup (SSH)](#로봇-원격-bringup-ssh) 참고):

```bash
cd ~/class_project/pyqt_ws
./run.sh
```

기본값으로 `maps/last_class_map_modi.yaml`을 사용해 Nav2를 띄우고, 몇 초 뒤 대시보드도 자동으로 열립니다. RViz는 대시보드에 초기 위치 설정 기능이 있어 기본적으로 띄우지 않습니다.

인자를 바꾸고 싶으면 그대로 뒤에 붙이면 됩니다:

```bash
./run.sh map:=/path/to/other_map.yaml   # 다른 맵 사용
./run.sh use_rviz:=true                 # RViz도 같이 띄우기
./run.sh use_dashboard:=false           # Nav2만 띄우고 대시보드는 따로 실행
```

`TURTLEBOT3_MODEL`을 미리 export해뒀다면 그 값을 쓰고, 안 해뒀다면 `burger`가 기본값입니다.

`run.sh`는 `ros2 launch launch/dashboard_bringup.launch.py`를 호출하는 얇은 래퍼라서, ROS2 환경이 이미 source된 터미널이라면 launch 파일을 직접 실행해도 됩니다:

```bash
ros2 launch launch/dashboard_bringup.launch.py map:=maps/last_class_map_modi.yaml
```

### 방법 B — 대시보드만 실행 (Nav2는 별도로 이미 떠 있는 경우)

```bash
source /opt/ros/humble/setup.bash
source ~/turtlebot3_ws/install/setup.bash
export TURTLEBOT3_MODEL=burger   # 사용 모델에 맞게 설정

cd ~/class_project/pyqt_ws
python3 main.py
```

터틀봇3(실물 또는 Gazebo 시뮬레이션)가 켜져 있지 않으면 "로봇 상태" 탭의 연결 표시가 회색(연결 끊김)으로 표시되고, "이벤트 로그" 탭에 연결 끊김 기록이 남습니다. 이는 정상 동작입니다. (연결은 됐지만 수신이 불안정할 때는 빨간색으로 표시됩니다.)

시뮬레이션으로 테스트하려면 별도 터미널에서:

```bash
source /opt/ros/humble/setup.bash
source ~/turtlebot3_ws/install/setup.bash
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_gazebo empty_world.launch.py
```

> 참고: Gazebo 시뮬레이션은 `/battery_state`를 발행하지 않을 수 있습니다 (실물 로봇의 `turtlebot3_node`에서만 발행). 이 경우 배터리 표시는 "연결 끊김" 상태로 유지됩니다.

## 로봇 원격 Bringup (SSH)

대시보드 상단에 SSH 연결 패널이 있어, 로봇에 미리 SSH로 접속해서 bringup을 직접 켤 필요 없이 대시보드에서 바로 실행할 수 있습니다.

1. **Host**에 SSH 접속 대상을 입력합니다 (기본값 `aurix`). `~/.ssh/config`에 등록된 Host 별칭이면 자동으로 실제 hostname/사용자명을 읽어옵니다 — 터미널에서 `ssh aurix`로 접속되면 그대로 `aurix`만 입력하면 됩니다.
2. **Username**은 비워두면 `~/.ssh/config`에 등록된 계정(없으면 이 대시보드를 실행 중인 내 PC의 로그인 계정명)을 그대로 씁니다. **다른 로봇처럼 SSH 계정명이 내 PC 계정명과 다르면 여기에 직접 입력해야 합니다** — 안 그러면 비밀번호가 맞아도 계정명이 달라 인증에 실패합니다.
3. **Password**에 로봇 SSH 비밀번호를 입력합니다 (키 인증이 이미 설정되어 있다면 빈 값이어도 될 수 있으나, 이 패널은 비밀번호 인증 전용입니다).
4. "연결 & Bringup 실행"을 누르면:
   - 로봇에 SSH로 접속해 bringup(`turtlebot3_bringup robot.launch.py`)이 이미 떠 있는지 확인합니다.
   - **이미 떠 있으면**: 새로 띄우지 않고 넘어갑니다. 같은 로봇에서 bringup이 중복 실행되면 모터/라이다가 충돌할 수 있어, 여러 팀원이 각자 대시보드에서 접속해도 안전하도록 하는 안전장치입니다.
   - **꺼져 있으면**: 로봇에서 원격으로 새로 실행합니다. 이 프로세스는 대시보드/SSH 세션과 완전히 분리되어 실행되므로, 대시보드를 꺼도 로봇의 bringup은 계속 켜져 있습니다. **끄는 것은 사용자가 로봇에 직접 접속해 수동으로 해야 합니다.**
5. 진행 상황과 결과는 패널의 상태 문구와 "이벤트 로그" 탭에 함께 남습니다.

로봇 쪽 ROS2 환경이 `/opt/ros/humble/setup.bash` 및 (있다면) `~/turtlebot3_ws/install/setup.bash`와 다른 경로라면 `dashboard/widgets/ssh_panel.py`의 `_LAUNCH_CMD_TMPL`을 실제 경로에 맞게 수정하세요. 원격 bringup이 실패하면 로봇에서 `cat ~/bringup_dashboard.log`로 원인을 확인할 수 있습니다.

## 조작

- 동작 컨트롤 탭에서 방향 버튼을 누르고 있으면 이동하고, 떼면 정지합니다.
- 컨트롤 패널을 클릭해 포커스를 준 뒤 방향키 또는 W/A/S/D 키로도 조작할 수 있습니다.
- 슬라이더로 최대 선속도/각속도(퍼센트)를 조절할 수 있습니다.
- "비상 정지" 버튼은 즉시 속도를 0으로 만들고 이벤트 로그에 경고를 남깁니다.

## 맵에서 waypoint / trajectory 생성

"맵 / 웨이포인트 생성" 탭에서 nav2 map_server 형식의 맵(`.yaml` + `.pgm`/`.png`)을 불러와 waypoint를 만들 수 있습니다.

- 기본 경로는 `maps/last_class_map_modi.yaml`이며, 있으면 자동으로 불러옵니다. 다른 맵은 "찾아보기..."로 선택하세요.
- 상단 "클릭 동작 모드"에서 두 가지 중 하나를 고릅니다:
  - **Waypoint 생성** (기본값): 아래 설명대로 waypoint를 만듭니다.
  - **초기 위치 설정 (2D Pose Estimate)**: 맵 위에서 클릭 후 드래그하면 그 위치/방향이 `/initialpose`로 발행되어 AMCL의 초기 위치로 설정됩니다 (RViz의 "2D Pose Estimate"와 동일한 기능). 초록색 화살표로 표시됩니다.
- 맵 위를 **클릭만** 하면 그 자리에 yaw=0인 waypoint가 생성됩니다.
- 맵 위를 **클릭한 채로 드래그**하면 드래그 방향이 yaw(로봇이 바라볼 방향)로 지정됩니다.
- 클릭/드래그를 놓으면 이름을 입력하는 창이 뜨고, 확인하면 오른쪽 "생성된 Waypoint" 목록과 지도 위 마커(점 + 화살표)에 추가됩니다.
- 오른쪽 "Trajectory 만들기"에서 waypoint를 순서대로 콤보박스로 골라 "경로에 추가"하고, 이름을 지어 "Trajectory로 저장"하면 순서 있는 경로가 만들어집니다.
- "기존 waypoint 파일 불러오기(병합)"으로 이전에 저장한 YAML을 불러와 이어서 편집할 수 있습니다.
- "다른 이름으로 저장..."을 누르면 매번 저장 경로를 직접 지정합니다. 저장하면 "웨이포인트 주행" 탭이 해당 파일을 자동으로 다시 불러와 바로 사용할 수 있습니다.
- 맵 origin에 회전(theta)이 있는 경우 좌표 변환이 정확하지 않을 수 있다는 경고가 이벤트 로그에 남습니다 (회전 없는 맵 기준으로 구현됨).

## 웨이포인트 / 트래젝토리 주행

"웨이포인트 주행" 탭은 `config/waypoints.example.yaml`과 같은 형식의 YAML 파일을 읽습니다.

```yaml
frame_id: map
waypoints:
  wp1: {x: 1.0, y: 0.5, yaw: 0.0}
  wp2: {x: 2.0, y: 1.0, yaw: 1.57}
trajectories:
  loop1: [wp1, wp2]
```

- 기본 경로는 `config/waypoints.yaml`이며, 있으면 앱 시작 시 자동으로 불러옵니다. 실제 waypoint 파일을 이 이름으로 `config/` 폴더에 넣거나, "찾아보기..." 버튼으로 다른 파일을 선택하세요.
- waypoint를 선택하고 "단일 목적지 주행"을 누르면 Nav2 `/navigate_to_pose` 액션으로 목표를 보냅니다.
- trajectory를 선택하고 "경로 주행"을 누르면 순서대로 waypoint 좌표 배열을 만들어 Nav2 `/follow_waypoints` 액션으로 보냅니다.
- "중지" 버튼은 진행 중인 목표(단일/경로 모두)를 취소합니다.
- 주행 상태(목적지까지 거리, 경로 진행률, 성공/취소/실패 결과)는 화면 라벨과 이벤트 로그 탭에 함께 기록됩니다.
- Nav2(`bringup`/`navigation2` launch)가 실행되어 있지 않으면 액션 서버를 찾지 못했다는 에러가 이벤트 로그에 남습니다.

## 의존성

- ROS2 Humble, rclpy, nav2_msgs (시스템에 이미 설치되어 있음)
- PyQt5 (`/usr/lib/python3/dist-packages/PyQt5`, 시스템에 이미 설치되어 있음)
- PyYAML, Pillow(PIL) (시스템에 이미 설치되어 있음)
- paramiko (SSH bringup 패널에서 사용, 시스템에 이미 설치되어 있음: `python3-paramiko`)

별도 pip 설치가 필요하지 않습니다.

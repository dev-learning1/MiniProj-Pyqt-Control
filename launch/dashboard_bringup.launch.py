# Nav2(turtlebot3_navigation2 기반)와 PyQt 대시보드를 한 번에 띄우는 launch 파일.
#
# 사용 예:
#   ros2 launch launch/dashboard_bringup.launch.py \
#     map:=/home/hj/class_project/pyqt_ws/maps/last_class_map_modi.yaml
#
# TURTLEBOT3_MODEL 환경변수는 실행 전 export 되어 있어야 한다 (예: burger).
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

TURTLEBOT3_MODEL = os.environ.get('TURTLEBOT3_MODEL', 'burger')
ROS_DISTRO = os.environ.get('ROS_DISTRO', 'humble')

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
DEFAULT_MAP = os.path.join(PROJECT_ROOT, 'maps', 'last_class_map_modi.yaml')
DASHBOARD_MAIN = os.path.join(PROJECT_ROOT, 'main.py')


def generate_launch_description():
    map_yaml = LaunchConfiguration('map')
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('use_rviz')
    use_dashboard = LaunchConfiguration('use_dashboard')

    param_file_name = TURTLEBOT3_MODEL + '.yaml'
    if ROS_DISTRO == 'humble':
        param_dir = os.path.join(
            get_package_share_directory('turtlebot3_navigation2'), 'param', ROS_DISTRO, param_file_name
        )
    else:
        param_dir = os.path.join(
            get_package_share_directory('turtlebot3_navigation2'), 'param', param_file_name
        )

    nav2_launch_file_dir = os.path.join(get_package_share_directory('nav2_bringup'), 'launch')
    rviz_config_dir = os.path.join(
        get_package_share_directory('turtlebot3_navigation2'), 'rviz', 'tb3_navigation2.rviz'
    )

    return LaunchDescription([
        DeclareLaunchArgument('map', default_value=DEFAULT_MAP,
                               description='불러올 occupancy map YAML 경로'),
        DeclareLaunchArgument('use_sim_time', default_value='false',
                               description='Gazebo 시뮬레이션이면 true'),
        DeclareLaunchArgument('use_rviz', default_value='false',
                               description='RViz도 같이 띄울지 여부 (대시보드에 초기 위치 설정 기능이 있어 기본 false)'),
        DeclareLaunchArgument('use_dashboard', default_value='true',
                               description='PyQt 대시보드를 자동으로 같이 띄울지 여부'),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([nav2_launch_file_dir, '/bringup_launch.py']),
            launch_arguments={
                'map': map_yaml,
                'use_sim_time': use_sim_time,
                'params_file': param_dir,
            }.items(),
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', rviz_config_dir],
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen',
            condition=IfCondition(use_rviz),
        ),

        # Nav2가 완전히 뜨기 전에 대시보드가 먼저 열려도 동작에는 문제 없다
        # (액션 서버가 아직 없으면 버튼 클릭 시 이벤트 로그에 에러가 남고,
        #  Nav2가 뜬 뒤 다시 누르면 정상 동작한다). 다만 화면이 바로 나오도록
        # 약간의 지연만 둔다.
        TimerAction(
            period=2.0,
            actions=[
                ExecuteProcess(
                    cmd=['python3', DASHBOARD_MAIN],
                    cwd=PROJECT_ROOT,
                    output='screen',
                    condition=IfCondition(use_dashboard),
                ),
            ],
        ),
    ])

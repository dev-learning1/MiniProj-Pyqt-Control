"""이벤트 로그 패널: 연결 상태 변화, 경고, 사용자 조작 등을 시간순으로 기록."""
import os
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QFileDialog
)

LEVEL_COLORS = {
    "INFO": QColor("#1565c0"),
    "WARN": QColor("#f9a825"),
    "ERROR": QColor("#c62828"),
}

DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["시간", "레벨", "메시지"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        btn_clear = QPushButton("로그 지우기")
        btn_save = QPushButton("파일로 저장")
        btn_clear.clicked.connect(self.clear)
        btn_save.clicked.connect(self._save_to_file)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(btn_clear)
        btn_row.addWidget(btn_save)

        root = QVBoxLayout()
        root.addWidget(self.table)
        root.addLayout(btn_row)
        self.setLayout(root)

    def add_event(self, level: str, message: str):
        row = self.table.rowCount()
        self.table.insertRow(row)

        ts = datetime.now().strftime("%H:%M:%S")
        time_item = QTableWidgetItem(ts)
        level_item = QTableWidgetItem(level)
        msg_item = QTableWidgetItem(message)

        color = LEVEL_COLORS.get(level, QColor("#333333"))
        for item in (time_item, level_item, msg_item):
            item.setForeground(color)

        self.table.setItem(row, 0, time_item)
        self.table.setItem(row, 1, level_item)
        self.table.setItem(row, 2, msg_item)
        self.table.scrollToBottom()

    def clear(self):
        self.table.setRowCount(0)

    def _save_to_file(self):
        os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
        default_name = os.path.join(
            DEFAULT_LOG_DIR, f"event_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        path, _ = QFileDialog.getSaveFileName(self, "로그 저장", default_name, "Text Files (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for row in range(self.table.rowCount()):
                ts = self.table.item(row, 0).text()
                level = self.table.item(row, 1).text()
                msg = self.table.item(row, 2).text()
                f.write(f"[{ts}] {level}: {msg}\n")
        self.add_event("INFO", f"로그를 저장했습니다: {path}")

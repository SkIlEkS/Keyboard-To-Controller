import ctypes
import json
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QStandardPaths, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    import vgamepad as vg
except ImportError:
    vg = None

try:
    from pynput import keyboard
except ImportError:
    keyboard = None


ANALOG_CONTROLS = {"LT", "RT"}
TOGGLE_BINDINGS = "Toggle bindings"
CONTROLS = [
    "A", "B", "X", "Y", "LB", "RB", "LT", "RT",
    "View", "Menu", "L3", "R3",
    "D-pad Up", "D-pad Down", "D-pad Left", "D-pad Right",
    "Left Stick Up", "Left Stick Down", "Left Stick Left", "Left Stick Right",
    "Right Stick Up", "Right Stick Down", "Right Stick Left", "Right Stick Right",
    TOGGLE_BINDINGS,
]

BUTTONS = {
    "A": "XUSB_GAMEPAD_A",
    "B": "XUSB_GAMEPAD_B",
    "X": "XUSB_GAMEPAD_X",
    "Y": "XUSB_GAMEPAD_Y",
    "LB": "XUSB_GAMEPAD_LEFT_SHOULDER",
    "RB": "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "View": "XUSB_GAMEPAD_BACK",
    "Menu": "XUSB_GAMEPAD_START",
    "L3": "XUSB_GAMEPAD_LEFT_THUMB",
    "R3": "XUSB_GAMEPAD_RIGHT_THUMB",
    "D-pad Up": "XUSB_GAMEPAD_DPAD_UP",
    "D-pad Down": "XUSB_GAMEPAD_DPAD_DOWN",
    "D-pad Left": "XUSB_GAMEPAD_DPAD_LEFT",
    "D-pad Right": "XUSB_GAMEPAD_DPAD_RIGHT",
}


@dataclass
class Binding:
    key: str
    control: str
    value: int = 100


def normalized_key(key):
    if isinstance(key, keyboard.Key):
        names = {
            keyboard.Key.space: "Space",
            keyboard.Key.enter: "Enter",
            keyboard.Key.tab: "Tab",
            keyboard.Key.esc: "Esc",
            keyboard.Key.backspace: "Backspace",
            keyboard.Key.delete: "Delete",
            keyboard.Key.up: "Up",
            keyboard.Key.down: "Down",
            keyboard.Key.left: "Left",
            keyboard.Key.right: "Right",
            keyboard.Key.shift: "Shift",
            keyboard.Key.shift_r: "Shift",
            keyboard.Key.ctrl: "Ctrl",
            keyboard.Key.ctrl_r: "Ctrl",
            keyboard.Key.alt: "Alt",
            keyboard.Key.alt_r: "Alt",
        }
        return names.get(key, str(key).replace("Key.", "").title())
    char = getattr(key, "char", None)
    if char:
        return char.upper() if len(char) == 1 else char
    return str(key).replace("Key.", "").title()


def key_id(key):
    return key.lower() if len(key) == 1 else key.casefold()


class KeyCaptureDialog(QDialog):
    def __init__(self, parent=None, current_key=""):
        super().__init__(parent)
        self.setWindowTitle("Bind a key")
        self.setModal(True)
        self.captured_key = current_key
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        self.prompt = QLabel("Press a key to bind")
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt.setMinimumHeight(80)
        self.prompt.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.prompt)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_prompt()
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if self.isVisible() and event.type() == QEvent.Type.KeyPress:
            self.capture_key_event(event)
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _update_prompt(self):
        self.prompt.setText(
            f"Press a key to bind\n\n{self.captured_key or 'Waiting for input…'}"
        )

    def keyPressEvent(self, event):
        self.capture_key_event(event)

    def capture_key_event(self, event):
        special_keys = {
            Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down",
            Qt.Key.Key_Left: "Left",
            Qt.Key.Key_Right: "Right",
            Qt.Key.Key_Space: "Space",
            Qt.Key.Key_Return: "Enter",
            Qt.Key.Key_Enter: "Enter",
            Qt.Key.Key_Tab: "Tab",
            Qt.Key.Key_Escape: "Esc",
            Qt.Key.Key_Backspace: "Backspace",
            Qt.Key.Key_Delete: "Delete",
        }
        key = special_keys.get(event.key())
        if not key:
            modifiers = event.modifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                key = "Ctrl"
            elif modifiers & Qt.KeyboardModifier.AltModifier:
                key = "Alt"
            elif modifiers & Qt.KeyboardModifier.ShiftModifier:
                key = "Shift"
            else:
                key = event.text().upper() if event.text() and event.text().isprintable() else ""
        if key:
            self.captured_key = key
            self._update_prompt()


class BindingDialog(QDialog):
    def __init__(self, parent=None, binding=None):
        super().__init__(parent)
        self.setWindowTitle("Edit binding" if binding else "Add binding")
        self.setMinimumWidth(340)
        self.key = binding.key if binding else ""
        self.value = binding.value if binding else 100
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Keyboard key"))
        key_row = QHBoxLayout()
        self.key_label = QLabel(self.key or "Unassigned")
        self.key_label.setObjectName("keyValue")
        capture = QPushButton("Press key…")
        capture.clicked.connect(self.capture_key)
        key_row.addWidget(self.key_label, 1)
        key_row.addWidget(capture)
        layout.addLayout(key_row)

        layout.addWidget(QLabel("Controller output"))
        self.control = QComboBox()
        self.control.addItems(CONTROLS)
        if binding:
            self.control.setCurrentText(binding.control)
        layout.addWidget(self.control)

        self.value_title = QLabel()
        layout.addWidget(self.value_title)
        self.value_slider = QSlider(Qt.Orientation.Horizontal)
        self.value_slider.setRange(1, 100)
        self.value_slider.setValue(self.value)
        self.value_slider.valueChanged.connect(self.update_value_label)
        layout.addWidget(self.value_slider)
        self.control.currentTextChanged.connect(self.update_value_visibility)
        self.update_value_visibility()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def capture_key(self):
        dialog = KeyCaptureDialog(self, self.key)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.captured_key:
            self.key = dialog.captured_key
            self.key_label.setText(self.key)

    def update_value_label(self, value):
        self.value_title.setText(f"Output strength  ·  {value}%")

    def update_value_visibility(self):
        is_analog = self.control.currentText() in ANALOG_CONTROLS
        self.value_title.setVisible(is_analog)
        self.value_slider.setVisible(is_analog)
        self.update_value_label(self.value_slider.value())

    def validate_and_accept(self):
        if not self.key:
            QMessageBox.warning(self, "Key required", "Capture a keyboard key first.")
            return
        self.accept()

    def get_binding(self):
        return Binding(self.key, self.control.currentText(), self.value_slider.value())


class MapperWindow(QMainWindow):
    activity_changed = Signal(str)
    bindings_state_changed = Signal(bool)
    output_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Keyboard To Controller")
        self.app_icon = Path(__file__).resolve().parent / "gamepad-icon-wide.png"
        self.app_icon_tray = Path(__file__).resolve().parent / "gamepad-icon.png"
        if self.app_icon.is_file():
            icon = QIcon(str(self.app_icon))
            self.setWindowIcon(icon)
            QApplication.instance().setWindowIcon(icon)
        self.resize(1060, 680)
        self.bindings = []
        self.held_keys = set()
        self.bindings_enabled = True
        self.state_lock = threading.RLock()
        self.output_lock = threading.Lock()
        self.gamepad = None
        self.listener = None
        self.config_path = Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
        ) / "bindings.json"

        self.output_error.connect(self.show_output_error)
        self.bindings_state_changed.connect(self.update_bindings_button)
        self.build_ui()
        self.activity_changed.connect(self.active_label.setText)
        self.config_error = self.load_bindings()
        self.refresh_table()
        self.setup_tray()
        self.initialize_backend()

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            self.tray_unavailable = True
            return

        self.tray_unavailable = False
        icon = QIcon(str(self.app_icon_tray)) if self.app_icon_tray.is_file() else self.windowIcon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Keyboard To Controller")
        menu = QMenu(self)
        show_action = QAction("Open Keyboard To Controller", self)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def quit_app(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
        if self.gamepad is not None:
            try:
                with self.output_lock:
                    self.gamepad.reset()
                    self.gamepad.update()
            except Exception as error:
                self.output_error.emit(str(error))
        if self.tray_icon is not None:
            self.tray_icon.hide()
        QApplication.instance().quit()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)

        right = QFrame()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(22, 22, 22, 22)
        right_layout.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        page_title = QLabel("Keyboard bindings")
        page_title.setObjectName("pageTitle")
        page_title.setStyleSheet("background-color: transparent;")
        subtitle = QLabel("Map your keys to Xbox controller inputs. Higher rows have priority.")
        subtitle.setObjectName("muted")
        subtitle.setStyleSheet("background-color: transparent;")
        heading.addWidget(page_title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.toggle_button = QPushButton("Disable bindings")
        self.toggle_button.setObjectName("toggle")
        self.toggle_button.clicked.connect(self.toggle_bindings)
        header.addWidget(self.toggle_button)
        add_button = QPushButton("+  Add binding")
        add_button.setObjectName("primary")
        add_button.clicked.connect(self.add_binding)
        header.addWidget(add_button)
        right_layout.addLayout(header)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["PRIORITY", "KEY", "CONTROLLER OUTPUT", "VALUE"])
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.Stretch)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(250)
        right_layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.edit_button = QPushButton("Edit selected")
        self.remove_button = QPushButton("Remove")
        self.edit_button.clicked.connect(self.edit_binding)
        self.remove_button.clicked.connect(self.remove_binding)
        self.move_up_button = QPushButton("Move up")
        self.move_down_button = QPushButton("Move down")
        self.move_up_button.clicked.connect(lambda: self.move_binding(-1))
        self.move_down_button.clicked.connect(lambda: self.move_binding(1))
        actions.addWidget(self.edit_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.move_up_button)
        actions.addWidget(self.move_down_button)
        actions.addStretch()
        right_layout.addLayout(actions)

        self.status_label = QLabel("Starting controller…")
        self.status_label.setObjectName("status")
        right_layout.addWidget(self.status_label)
        self.active_label = QLabel("Press a bound key to preview its output")
        self.active_label.setObjectName("muted")
        self.active_label.setWordWrap(True)
        self.active_label.setStyleSheet("background-color: transparent;")
        right_layout.addWidget(self.active_label)
        root.addWidget(right, 1)

        self.setStyleSheet("""
            QWidget { background: #11151d; color: #e9edf4; font-family: 'Segoe UI'; font-size: 13px; }
            QFrame#panel { background: #191f29; border: 1px solid #29313e; border-radius: 14px; }
            QLabel#pageTitle { font-size: 23px; font-weight: 700; }
            QLabel#sectionTitle { color: #98a5b7; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
            QLabel#muted { color: #8d99aa; }
            QLabel#status { color: #9caabd; padding: 10px 12px; background: #202834; border-radius: 8px; }
            QLabel#keyValue { color: #78d6b0; font-weight: 700; padding: 8px; background: #202834; border-radius: 6px; }
            QPushButton { background: #252e3b; border: 1px solid #343f4e; border-radius: 7px; padding: 9px 13px; }
            QPushButton:hover { background: #303a49; }
            QPushButton#primary { background: #78d6b0; color: #102019; border: none; font-weight: 700; }
            QPushButton#primary:hover { background: #91e2c0; }
            QPushButton#toggle { color: #78d6b0; }
            QPushButton#toggle:hover { background: #283d3a; }
            QTableWidget { background: #151b24; border: 1px solid #29313e; border-radius: 8px; alternate-background-color: #191f29; }
            QTableWidget::item { padding: 10px; border: none; }
            QTableWidget::item:selected { background: #283d3a; color: #e9edf4; outline: none; border: none; }
            QTableWidget::item:focus { outline: none; border: none; }
            QHeaderView::section { background: #202834; color: #8d99aa; border: none; padding: 10px; font-size: 10px; font-weight: 700; }
            QComboBox, QSlider { background: #202834; border: 1px solid #343f4e; border-radius: 6px; padding: 8px; }
            QComboBox QAbstractItemView { background: #202834; selection-background-color: #35483f; }
            QSlider::groove:horizontal { height: 5px; background: #343f4e; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #78d6b0; border-radius: 2px; }
            QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #78d6b0; border-radius: 7px; }
        """)

    def initialize_backend(self):
        listener_error = None
        if keyboard is None:
            listener_error = "Keyboard listener unavailable: install requirements.txt."
        else:
            try:
                self.listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
                self.listener.start()
            except Exception as error:
                listener_error = f"Keyboard listener unavailable: {error}"

        if vg is None:
            self.status_label.setText(
                self.with_config_notice(
                    f"Virtual controller unavailable: install requirements.txt. {listener_error or ''}"
                )
            )
            return
        try:
            self.gamepad = vg.VX360Gamepad()
        except Exception as error:
            self.status_label.setText(
                self.with_config_notice(
                    f"Controller unavailable: {error} {listener_error or ''}"
                )
            )
            return
        if listener_error:
            self.status_label.setText(
                self.with_config_notice(f"Controller connected · {listener_error}")
            )
        else:
            self.status_label.setText(
                self.with_config_notice("Ready  ·  Xbox 360 virtual controller connected")
            )

    def with_config_notice(self, status):
        if self.tray_unavailable:
            status = f"{status} · System tray unavailable; closing exits"
        if self.config_error:
            return f"{status} · {self.config_error}"
        return status

    def load_bindings(self):
        if not self.config_path.exists():
            return None
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("the bindings file must contain a list")
            loaded = []
            used_keys = set()
            for entry in data:
                if not isinstance(entry, dict):
                    raise ValueError("a binding entry is not an object")
                binding = Binding(**entry)
                if (
                    not isinstance(binding.key, str)
                    or not binding.key
                    or binding.control not in CONTROLS
                    or isinstance(binding.value, bool)
                    or not isinstance(binding.value, int)
                    or not 1 <= binding.value <= 100
                ):
                    raise ValueError("a binding entry contains invalid values")
                normalized = key_id(binding.key)
                if normalized in used_keys:
                    raise ValueError(f"the key {binding.key} is assigned more than once")
                used_keys.add(normalized)
                loaded.append(binding)
            self.bindings = loaded
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            return f"Could not load saved bindings: {error}"
        return None

    def persist_bindings(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.config_path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps([vars(binding) for binding in self.bindings], indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(self.config_path)
            self.config_error = None
        except OSError as error:
            self.status_label.setText(f"Bindings changed but could not be saved: {error}")

    def add_binding(self):
        dialog = BindingDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.save_binding(dialog.get_binding())

    def edit_binding(self):
        index = self.selected_index()
        if index is None:
            return
        dialog = BindingDialog(self, self.bindings[index])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.save_binding(dialog.get_binding(), index)

    def remove_binding(self):
        index = self.selected_index()
        if index is not None:
            with self.state_lock:
                self.bindings.pop(index)
            self.refresh_table()
            self.persist_bindings()
            self.apply_controller_state()

    def move_binding(self, offset):
        index = self.selected_index()
        if index is None:
            return
        new_index = index + offset
        if not 0 <= new_index < len(self.bindings):
            return
        with self.state_lock:
            self.bindings[index], self.bindings[new_index] = (
                self.bindings[new_index],
                self.bindings[index],
            )
        self.refresh_table()
        self.table.selectRow(new_index)
        self.persist_bindings()
        self.apply_controller_state()

    def toggle_bindings(self):
        with self.state_lock:
            self.bindings_enabled = not self.bindings_enabled
            enabled = self.bindings_enabled
        self.bindings_state_changed.emit(enabled)
        self.apply_controller_state()

    def set_bindings_enabled(self, enabled):
        with self.state_lock:
            if self.bindings_enabled == enabled:
                return
            self.bindings_enabled = enabled
        self.bindings_state_changed.emit(enabled)
        self.apply_controller_state()

    def update_bindings_button(self, enabled):
        self.toggle_button.setText("Disable bindings" if enabled else "Enable bindings")

    def selected_index(self):
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def save_binding(self, binding, replace_index=None):
        conflict = None
        with self.state_lock:
            for index, existing in enumerate(self.bindings):
                if index != replace_index and key_id(existing.key) == key_id(binding.key):
                    conflict = existing
                    break
            if conflict is None:
                if replace_index is None:
                    self.bindings.append(binding)
                else:
                    self.bindings[replace_index] = binding
        if conflict:
            QMessageBox.warning(
                self, "Key already assigned",
                f"{conflict.key} is already assigned to {conflict.control}.",
            )
            return
        self.refresh_table()
        self.persist_bindings()
        self.apply_controller_state()

    def refresh_table(self):
        self.table.setRowCount(len(self.bindings))
        for row, binding in enumerate(self.bindings):
            value = f"{binding.value}%" if binding.control in ANALOG_CONTROLS else "—"
            for column, text in enumerate((str(row + 1), binding.key, binding.control, value)):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row, column, item)

    def on_key_press(self, key):
        normalized = normalized_key(key)
        normalized_id = key_id(normalized)
        state_changed = None
        with self.state_lock:
            is_new_press = normalized_id not in self.held_keys
            self.held_keys.add(normalized_id)
            if is_new_press and any(
                key_id(binding.key) == normalized_id and binding.control == TOGGLE_BINDINGS
                for binding in self.bindings
            ):
                self.bindings_enabled = not self.bindings_enabled
                state_changed = self.bindings_enabled
        if state_changed is not None:
            self.bindings_state_changed.emit(state_changed)
        self.apply_controller_state()

    def on_key_release(self, key):
        normalized = normalized_key(key)
        with self.state_lock:
            self.held_keys.discard(key_id(normalized))
        self.apply_controller_state()

    def apply_controller_state(self):
        with self.state_lock:
            bindings_enabled = self.bindings_enabled
            pressed_bindings = [b for b in self.bindings if key_id(b.key) in self.held_keys]
            pressed_active = [
                binding for binding in pressed_bindings
                if bindings_enabled and binding.control != TOGGLE_BINDINGS
            ]
            active = []
            active_controls = set()
            for binding in pressed_active:
                if binding.control not in active_controls:
                    active.append(binding)
                    active_controls.add(binding.control)
            toggle_pressed = any(b.control == TOGGLE_BINDINGS for b in pressed_bindings)

        details = [
            f"{b.control} {b.value}%" if b.control in ANALOG_CONTROLS else b.control
            for b in active
        ]
        if not bindings_enabled:
            activity_text = "Bindings are disabled"
        elif toggle_pressed:
            activity_text = "Bindings are enabled"
        elif active:
            activity_text = f"Active: {', '.join(b.key for b in active)}  →  {', '.join(details)}"
        else:
            activity_text = "Press a bound key to preview its output"
        self.activity_changed.emit(activity_text)
        if self.gamepad is None:
            return
        try:
            with self.output_lock:
                self.gamepad.reset()
                for binding in active:
                    control = binding.control
                    if control in BUTTONS:
                        button = getattr(vg.XUSB_BUTTON, BUTTONS[control])
                        self.gamepad.press_button(button=button)
                left_trigger = max((b.value for b in active if b.control == "LT"), default=0)
                right_trigger = max((b.value for b in active if b.control == "RT"), default=0)
                if left_trigger:
                    self.gamepad.left_trigger(value=round(left_trigger * 255 / 100))
                if right_trigger:
                    self.gamepad.right_trigger(value=round(right_trigger * 255 / 100))
                if any(b.control.startswith("Left Stick ") for b in active):
                    x, y = self.stick_values(active, "Left Stick")
                    self.gamepad.left_joystick(x_value=x, y_value=y)
                if any(b.control.startswith("Right Stick ") for b in active):
                    x, y = self.stick_values(active, "Right Stick")
                    self.gamepad.right_joystick(x_value=x, y_value=y)
                self.gamepad.update()
        except Exception as error:
            self.output_error.emit(str(error))

    @staticmethod
    def stick_values(active, prefix):
        controls = {binding.control for binding in active}
        x = 0
        y = 0
        if f"{prefix} Left" in controls:
            x -= 32767
        if f"{prefix} Right" in controls:
            x += 32767
        if f"{prefix} Up" in controls:
            y += 32767
        if f"{prefix} Down" in controls:
            y -= 32767
        return max(-32768, min(32767, x)), max(-32768, min(32767, y))

    def show_output_error(self, message):
        self.status_label.setText(f"Controller output error: {message}")

    def closeEvent(self, event):
        if self.tray_icon is not None and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
            return
        self.quit_app()
        event.accept()


def main():
    if os.name == "nt":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Keypad.KeyboardToController"
        )
    app = QApplication(sys.argv)
    app.setOrganizationName("Keypad")
    app.setApplicationName("Keyboard To Controller")
    app.setQuitOnLastWindowClosed(False)
    icon_path = Path(__file__).resolve().parent / "gamepad-icon-wide.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MapperWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

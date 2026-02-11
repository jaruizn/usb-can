import sys
import argparse
import time
import json
from datetime import datetime
import serial.tools.list_ports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTableWidget, QTableWidgetItem, QLineEdit, QPushButton, 
                             QLabel, QComboBox, QHeaderView, QStatusBar, QListWidget, QListWidgetItem, 
                             QMenu, QFileDialog, QMenuBar)
from PyQt6.QtGui import QFont, QColor, QPalette, QAction, QKeySequence
from canusb_backend import CANUSBBackend, CANFrame

class Filter:
    """Represents a filtering rule for CAN frames."""
    def __init__(self, ftype, value, logic):
        self.ftype = ftype    # "ID" or "Data"
        self.value = value.lower()
        self.logic = logic    # "Include" or "Exclude"

    def matches(self, id_text, data_text):
        """Check if the given ID and Data strings match the filter pattern."""
        target = id_text.lower() if self.ftype == "ID" else data_text.lower()
        match = self.value in target
        if self.logic == "Include":
            return match
        else: # Exclude
            return not match

    def __str__(self):
        return f"{self.logic} {self.ftype}: {self.value}"

class CANMonitor(QMainWindow):
    """
    Main GUI Window for the CANUSB Monitor for Linux.
    Features real-time data display, advanced filtering, and export capabilities.
    """
    # Signal to pass received CAN frames from the backend thread to the main UI thread
    frame_received_signal = pyqtSignal(CANFrame)

    def __init__(self, port=None, baudrate=2000000, can_speed=500000):
        super().__init__()
        self.backend = None
        self.port = port
        self.baudrate = baudrate
        self.can_speed = can_speed
        self.filters = []
        
        self.setWindowTitle("CANUSB Monitor for Linux - Advanced Filtering")
        self.resize(1100, 600)
        
        # Connect signal for thread-safe UI updates
        self.frame_received_signal.connect(self._do_add_frame)
        
        self.init_menu()
        self.init_ui()
        self.apply_dark_theme()
        self.refresh_ports()
        
        # Pre-select port if provided via CLI
        if self.port:
            index = self.port_combo.findText(self.port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            else:
                self.port_combo.insertItem(0, self.port)
                self.port_combo.setCurrentIndex(0)

    def init_menu(self):
        """Initialize the top menu bar."""
        menubar = self.menuBar()
        project_menu = menubar.addMenu("Project")

        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.load_project)
        project_menu.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_project)
        project_menu.addAction(save_action)

    def init_ui(self):
        """Set up all UI widgets and layouts."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- Left side: Table and Main Controls ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        main_layout.addWidget(left_widget, 70)

        # Controls Row
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(200)
        ctrl_layout.addWidget(self.port_combo)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        ctrl_layout.addWidget(self.refresh_btn)
        
        self.speed_combo = QComboBox()
        speeds = [1000000, 800000, 500000, 400000, 250000, 125000, 100000, 50000, 20000, 10000]
        for s in speeds:
            self.speed_combo.addItem(f"{s//1000}k", s)
        self.speed_combo.setCurrentText("500k")
        ctrl_layout.addWidget(QLabel("CAN Speed:"))
        ctrl_layout.addWidget(self.speed_combo)
        
        self.start_btn = QPushButton("Open")
        self.start_btn.clicked.connect(self.toggle_monitoring)
        self.start_btn.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        ctrl_layout.addWidget(self.start_btn)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_table)
        ctrl_layout.addWidget(self.clear_btn)
        
        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self.export_data)
        self.export_btn.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
        ctrl_layout.addWidget(self.export_btn)
        
        left_layout.addLayout(ctrl_layout)

        # Main Data Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Timestamp", "ID (Hex)", "DLC", "Data (Hex)", "Data (Dec)"])
        
        # Configure automatic and interactive column resizing
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 130) # Timestamp
        self.table.setColumnWidth(1, 60)  # ID
        self.table.setColumnWidth(2, 40)  # DLC
        self.table.setColumnWidth(3, 180) # Data (Hex)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch) # Data (Dec)
        
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.setStyleSheet("QTableWidget::item { color: white; padding: 1px; }")
        left_layout.addWidget(self.table)

        # --- Right side: Filtering Sidebar ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        main_layout.addWidget(right_widget, 30)

        right_layout.addWidget(QLabel("Advanced Filters"))
        
        # Add Filter Interface
        add_filter_layout = QVBoxLayout()
        self.filter_type = QComboBox()
        self.filter_type.addItems(["ID", "Data"])
        add_filter_layout.addWidget(QLabel("Type:"))
        add_filter_layout.addWidget(self.filter_type)

        self.filter_value = QLineEdit()
        self.filter_value.setPlaceholderText("Value (Hex)")
        add_filter_layout.addWidget(QLabel("Value:"))
        add_filter_layout.addWidget(self.filter_value)

        self.filter_logic = QComboBox()
        self.filter_logic.addItems(["Include", "Exclude"])
        add_filter_layout.addWidget(QLabel("Logic:"))
        add_filter_layout.addWidget(self.filter_logic)

        self.add_filter_btn = QPushButton("Add Filter")
        self.add_filter_btn.clicked.connect(self.add_filter)
        self.add_filter_btn.setStyleSheet("background-color: #3498db; color: white;")
        add_filter_layout.addWidget(self.add_filter_btn)
        
        right_layout.addLayout(add_filter_layout)

        # Active filters list
        self.filter_list = QListWidget()
        right_layout.addWidget(self.filter_list)

        self.remove_filter_btn = QPushButton("Remove Selected Filter")
        self.remove_filter_btn.clicked.connect(self.remove_filter)
        right_layout.addWidget(self.remove_filter_btn)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def apply_dark_theme(self):
        """Configure a modern dark theme for the application."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(20, 20, 20))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(50, 50, 50))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
        self.setPalette(palette)
        
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #ffffff; font-size: 11px; }
            QLabel { color: #ffffff; font-weight: bold; }
            QTableWidget { gridline-color: #444; background-color: #141414; alternate-background-color: #333; color: white; }
            QHeaderView::section { background-color: #333; color: #ffffff; padding: 2px; border: 1px solid #444; }
            QLineEdit { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444; padding: 2px; border-radius: 2px; }
            QPushButton { background-color: #3c3c3c; color: #ffffff; border: 1px solid #555; padding: 2px 8px; border-radius: 2px; }
            QPushButton:hover { background-color: #4c4c4c; }
            QComboBox { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444; padding: 2px; }
            QStatusBar { background-color: #1e1e1e; color: #aaa; }
            QListWidget { background-color: #2b2b2b; color: white; border: 1px solid #444; }
        """)

    def add_filter(self):
        """Add a new filtering rule to the list."""
        val = self.filter_value.text().strip()
        if not val:
            return
        new_filter = Filter(self.filter_type.currentText(), val, self.filter_logic.currentText())
        self.filters.append(new_filter)
        self.filter_list.addItem(str(new_filter))
        self.filter_value.clear()
        self.apply_filters_to_all()

    def remove_filter(self):
        """Remove the currently selected filter rule."""
        row = self.filter_list.currentRow()
        if row >= 0:
            self.filter_list.takeItem(row)
            self.filters.pop(row)
            self.apply_filters_to_all()

    def apply_filters_to_all(self):
        """Re-scan all rows in the table and apply filtering logic."""
        for i in range(self.table.rowCount()):
            self.apply_row_filter(i)

    def apply_row_filter(self, row):
        """Determine if a single row should be hidden based on active filters."""
        id_text = self.table.item(row, 1).text()
        data_hex = self.table.item(row, 3).text()
        
        show = True
        include_filters = [f for f in self.filters if f.logic == "Include"]
        exclude_filters = [f for f in self.filters if f.logic == "Exclude"]

        # OR logic for multiple Include filters
        if include_filters:
            show = any(f.matches(id_text, data_hex) for f in include_filters)
        
        # AND logic for multiple Exclude filters
        if show and exclude_filters:
            if any(f.matches(id_text, data_hex) == False for f in exclude_filters):
                show = False
        
        self.table.setRowHidden(row, not show)

    def refresh_ports(self):
        """Update the list of available serial ports."""
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.port_combo.addItem(f"{p.device} ({p.description})", p.device)
        
        if current_port:
            index = self.port_combo.findText(current_port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)

    def toggle_monitoring(self):
        """Open or close the serial connection based on current state."""
        if self.backend and self.backend.running:
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def start_monitoring(self):
        """Initialize the backend and start receiving data."""
        port = self.port_combo.currentData() or self.port_combo.currentText()
        if not port:
            self.status_bar.showMessage("No port selected!")
            return
        speed = self.speed_combo.currentData()
        self.backend = CANUSBBackend(port, self.baudrate, speed)
        if self.backend.connect():
            self.backend.add_callback(self.add_frame_to_table)
            self.start_btn.setText("Close")
            self.start_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 5px 15px;")
            self.status_bar.showMessage(f"Connected to {port}")
        else:
            self.status_bar.showMessage(f"Failed to connect to {port}")

    def stop_monitoring(self):
        """Stop data reception and clean up backend."""
        if self.backend:
            self.backend.disconnect()
            self.backend = None
            self.start_btn.setText("Open")
            self.start_btn.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 5px 15px;")
            self.status_bar.showMessage("Disconnected")

    def add_frame_to_table(self, frame: CANFrame):
        """Backend callback: schedules a UI update for a new CAN frame."""
        self.frame_received_signal.emit(frame)

    def _do_add_frame(self, frame: CANFrame):
        """Actual UI update: adds a new row to the table (called on main thread)."""
        try:
            # Smart Scroll Logic: only scroll if we were already at the bottom
            scrollbar = self.table.verticalScrollBar()
            is_at_bottom = scrollbar.value() >= (scrollbar.maximum() - 10)

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 18)
            
            data_hex = " ".join(f"{b:02X}" for b in frame.data)
            data_dec = " ".join(f"{b:3d}" for b in frame.data)
            
            # Format timestamp as HH:MM:SS.mmm
            ts_str = datetime.fromtimestamp(frame.timestamp).strftime("%H:%M:%S.%f")[:-3]
            
            self.table.setItem(row, 0, QTableWidgetItem(ts_str))
            self.table.setItem(row, 1, QTableWidgetItem(f"0x{frame.id:03X}"))
            self.table.setItem(row, 2, QTableWidgetItem(str(frame.dlc)))
            self.table.setItem(row, 3, QTableWidgetItem(data_hex))
            self.table.setItem(row, 4, QTableWidgetItem(data_dec))
            
            # Formatting and monospaced font for data columns
            mono_font = QFont("Monospace")
            mono_font.setStyleHint(QFont.StyleHint.Monospace)
            mono_font.setPointSize(9)

            for col in range(5):
                item = self.table.item(row, col)
                if item:
                    item.setForeground(Qt.GlobalColor.white)
                    if col in [1, 3, 4]: # ID, Hex, Dec columns
                        item.setFont(mono_font)

            self.apply_row_filter(row)
            
            if is_at_bottom:
                self.table.scrollToBottom()
        except Exception:
            pass

    def clear_table(self):
        """Clear all entries from the data table."""
        self.table.setRowCount(0)

    def export_data(self):
        """Export all visible rows to a text or CSV file."""
        if self.table.rowCount() == 0:
            self.status_bar.showMessage("Nothing to export!")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export CAN Data", "can_data_export.txt", "Text Files (*.txt);;CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                # Write Header
                headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
                if file_path.endswith('.csv'):
                    f.write(",".join(headers) + "\n")
                else:
                    f.write("\t".join(headers) + "\n")
                
                # Write Visible Rows
                export_count = 0
                for row in range(self.table.rowCount()):
                    if not self.table.isRowHidden(row):
                        row_data = []
                        for col in range(self.table.columnCount()):
                            item = self.table.item(row, col)
                            row_data.append(item.text() if item else "")
                        
                        if file_path.endswith('.csv'):
                            f.write(",".join(row_data) + "\n")
                        else:
                            f.write("\t".join(row_data) + "\n")
                        export_count += 1
                
            self.status_bar.showMessage(f"Exported {export_count} rows to {file_path}")
        except Exception as e:
            self.status_bar.showMessage(f"Export failed: {e}")

    def show_context_menu(self, pos):
        """Display context menu on right-click to copy cell value or add to filter."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            # If nothing selected, try to get item at position
            item = self.table.itemAt(pos)
            if not item:
                return
            selected_items = [item]
            
        menu = QMenu()
        copy_action = menu.addAction("Copy")
        
        add_filter_action = None
        # Only show "Add to filter" if exactly one cell is selected
        if len(selected_items) == 1:
            item = selected_items[0]
            col = item.column()
            if col in [1, 3, 4]: # ID or Data columns
                menu.addSeparator()
                add_filter_action = menu.addAction("Add to filter")
        
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        
        if action == copy_action:
            self.copy_to_clipboard(selected_items)
        elif action == add_filter_action:
            item = selected_items[0]
            text = item.text()
            col = item.column()
            if col == 1: # ID column
                self.filter_type.setCurrentText("ID")
                clean_text = text.replace("0x", "")
                self.filter_value.setText(clean_text)
            elif col in [3, 4]: # Data columns
                self.filter_type.setCurrentText("Data")
                self.filter_value.setText(text)

    def copy_to_clipboard(self, items):
        """Copy selected items to clipboard in a tabular format."""
        if not items:
            return
            
        # Sort items by row and then column
        items.sort(key=lambda x: (x.row(), x.column()))
        
        rows = {}
        for item in items:
            r = item.row()
            if r not in rows:
                rows[r] = []
            rows[r].append(item.text())
            
        text = "\n".join(["\t".join(r_data) for r_data in rows.values()])
        QApplication.clipboard().setText(text)
        self.status_bar.showMessage(f"Copied {len(items)} items to clipboard")

    def save_project(self):
        """Save filter configurations to a JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "filters.json", "Project Files (*.json);;All Files (*)"
        )
        if not file_path:
            return
            
        project_data = {
            "filters": [
                {"type": f.ftype, "value": f.value, "logic": f.logic}
                for f in self.filters
            ]
        }
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=4)
            self.status_bar.showMessage(f"Project saved to {file_path}")
        except Exception as e:
            self.status_bar.showMessage(f"Save failed: {e}")

    def load_project(self):
        """Load filter configurations from a JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Project Files (*.json);;All Files (*)"
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
            
            # Clear current filters
            self.filters = []
            self.filter_list.clear()
            
            # Load new filters
            for f_data in project_data.get("filters", []):
                new_filter = Filter(f_data["type"], f_data["value"], f_data["logic"])
                self.filters.append(new_filter)
                self.filter_list.addItem(str(new_filter))
            
            self.apply_filters_to_all()
            self.status_bar.showMessage(f"Project loaded from {file_path}")
        except Exception as e:
            self.status_bar.showMessage(f"Load failed: {e}")

def main():
    """Main Entry Point: parse arguments and launch GUI."""
    parser = argparse.ArgumentParser(description="CANUSB Monitor for Linux Application")
    parser.add_argument("-d", "--device", help="TTY Device (e.g. /dev/ttyUSB0)")
    parser.add_argument("-s", "--speed", type=int, default=500000, help="CAN Bus Speed in bps")
    parser.add_argument("-b", "--baudrate", type=int, default=2000000, help="Serial TTY Baudrate")
    
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    window = CANMonitor(port=args.device, baudrate=args.baudrate, can_speed=args.speed)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

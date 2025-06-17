import os
import argparse
import logging
from typing import Optional

from instrumentserver import setupLogging, logger, QtWidgets
from instrumentserver.log import LogWidget
from instrumentserver.client import QtClient
from instrumentserver.client.application import InstrumentClientMainWindow
from instrumentserver.gui.instruments import ParameterManagerGui
from instrumentserver.init_client import DeviceInitializer


setupLogging(addStreamHandler=True,
             logFile=os.path.abspath('instrumentclient.log'))
log = logger()
log.setLevel(logging.DEBUG)


class DeviceStatusDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device Status")
        self.setModal(True)
        
        layout = QtWidgets.QVBoxLayout()
        
        # Device list
        self.device_list = QtWidgets.QListWidget()
        layout.addWidget(self.device_list)
        
        # Status label
        self.status_label = QtWidgets.QLabel()
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.close_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.resize(400, 300)

    def refresh_devices(self):
        self.device_list.clear()
        devices = self.parent().device_manager.list_devices()
        for name, device in devices.items():
            self.device_list.addItem(f"{name}: {device.__class__.__name__}")
        self.status_label.setText(f"Found {len(devices)} device(s)")


def setup_log(win: InstrumentClientMainWindow):
    w = LogWidget()
    win.addWidget(w, 'Log', visible=False)


def setup_pm(win: InstrumentClientMainWindow):
    pm = win.client.find_or_create_instrument(
        'pm',
        'instrumentserver.params.ParameterManager',
    )
    w = ParameterManagerGui(pm)
    win.addWidget(w, name="PM: "+pm.name)


def setup_device_menu(win: InstrumentClientMainWindow):
    # Create menu bar if it doesn't exist
    if not win.menuBar():
        win.setMenuBar(QtWidgets.QMenuBar())
    
    # Create Devices menu
    devices_menu = win.menuBar().addMenu("Devices")
    
    # Initialize Devices action
    init_action = QtWidgets.QAction("Initialize Devices", win)
    init_action.triggered.connect(lambda: initialize_devices(win))
    devices_menu.addAction(init_action)
    
    # Show Device Status action
    status_action = QtWidgets.QAction("Show Device Status", win)
    status_action.triggered.connect(lambda: show_device_status(win))
    devices_menu.addAction(status_action)


def initialize_devices(win: InstrumentClientMainWindow):
    config_file = QtWidgets.QFileDialog.getOpenFileName(
        win,
        "Select Device Configuration",
        os.path.join(os.path.dirname(__file__), "config"),
        "JSON Files (*.json)"
    )[0]
    
    if config_file:
        try:
            # Initialize device manager if it doesn't exist
            if not hasattr(win, 'device_manager'):
                win.device_manager = DeviceInitializer(config_file)
            else:
                # Reinitialize with new config
                win.device_manager.close_all()
                win.device_manager = DeviceInitializer(config_file)
            
            # Show success message
            QtWidgets.QMessageBox.information(
                win,
                "Success",
                f"Successfully initialized devices from {config_file}"
            )
            
            # Show device status
            show_device_status(win)
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                win,
                "Error",
                f"Failed to initialize devices: {str(e)}"
            )


def show_device_status(win: InstrumentClientMainWindow):
    if not hasattr(win, 'device_manager'):
        QtWidgets.QMessageBox.warning(
            win,
            "Warning",
            "No devices have been initialized yet."
        )
        return
    
    dialog = DeviceStatusDialog(win)
    dialog.refresh_devices()
    dialog.exec_()


def main():
    app = QtWidgets.QApplication([])
    cli = QtClient()
    mainwindow = InstrumentClientMainWindow(cli)

    setup_pm(mainwindow)
    setup_log(mainwindow)
    setup_device_menu(mainwindow)

    mainwindow.show()
    return app.exec_()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Client options')
    args = parser.parse_args()
    main()





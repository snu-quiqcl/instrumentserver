import html
import importlib
import logging
import os
import time
import json
from typing import Union, Optional, Any, Dict

from instrumentserver.client import QtClient
from instrumentserver.log import LogLevels, LogWidget, log
from instrumentserver.init_client import DeviceInitializer

from .core import (
    StationServer,
    InstrumentModuleBluePrint, ParameterBluePrint
)
from .. import QtCore, QtWidgets, QtGui, Client
from ..gui.misc import DetachableTabWidget, BaseDialog
from ..gui.parameters import AnyInputForMethod
from ..gui.instruments import GenericInstrument
from ..config import GUIFIELD

logger = logging.getLogger(__name__)


# TODO: parameter file location should be optionally configurable
# TODO: add an option to save one file per station component
# TODO: allow for user shutdown of the server.
# TODO: use the safeword approach to configure the server on the fly
#   allowing users to shut down, etc, set other internal properties of
#   of the server object.
# TODO: add a monitor that refreshes the station now and then and pings the server
# TODO: the station info should be collapsable (tree?) and searchable.


class StationList(QtWidgets.QTreeWidget):
    """A widget that displays all objects in a qcodes station."""

    cols = ['Name', 'Type']

    #: Signal(str) -- emitted when a parameter or Instrument is selected.
    #: Argument is the name of the selected instrument
    componentSelected = QtCore.Signal(str)

    #: Signal(str) -- emitted when the user requested closing an instrument
    #: Argument is the name of the instrument that should be closed
    closeRequested = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(len(self.cols))
        self.setHeaderLabels(self.cols)
        self.setSortingEnabled(True)
        self.clear()

        self.deleteAction = QtWidgets.QAction("Close Instrument")
        self.deleteAction.setShortcuts(['Del', 'backspace'])
        # you need to add the action to the widget so that it can detect the shortcut
        self.addAction(self.deleteAction)

        self.contextMenu = QtWidgets.QMenu(self)
        self.contextMenu.addAction(self.deleteAction)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        self.customContextMenuRequested.connect(lambda x: self.contextMenu.exec_(self.mapToGlobal(x)))
        self.deleteAction.triggered.connect(self.onDeleteAction)
        self.itemSelectionChanged.connect(self._processSelection)

    def addInstrument(self, bp: InstrumentModuleBluePrint):
        lst = [bp.name, f"{bp.instrument_module_class.split('.')[-1]}"]
        self.addTopLevelItem(QtWidgets.QTreeWidgetItem(lst))
        self.resizeColumnToContents(0)

    def removeObject(self, name: str):
        items = self.findItems(name, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)
        if len(items) > 0:
            item = items[0]
            idx = self.indexOfTopLevelItem(item)
            self.takeTopLevelItem(idx)
            del item

    def _processSelection(self):
        items = self.selectedItems()
        if len(items) == 0:
            return
        item = items[0]
        self.componentSelected.emit(item.text(0))

    @QtCore.Slot()
    def onDeleteAction(self):
        # need to check if widget has focus because of the keyboard shortcuts
        if self.hasFocus():
            items = self.selectedItems()
            for item in items:
                msgBox = QtWidgets.QMessageBox()
                msgBox.setWindowTitle("Confirm Close Instrument")
                msgBox.setText(f'Are you sure you want to close instrument "{item.text(0)}"')
                msgBox.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
                msgBox.setDefaultButton(QtWidgets.QMessageBox.No)
                ret = msgBox.exec()
                if ret == QtWidgets.QMessageBox.Yes:
                    self.closeRequested.emit(item.text(0))


class StationObjectInfo(QtWidgets.QTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)

    @QtCore.Slot(object)
    def setObject(self, bp: InstrumentModuleBluePrint):
        self.setHtml(bluePrintToHtml(bp))


class ServerStatus(QtWidgets.QWidget):
    """A widget that shows the status of the instrument server."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QtWidgets.QVBoxLayout(self)

        # At the top: a status label, and a button for emitting a test message
        self.addressLabel = QtWidgets.QLabel()
        self.testButton = QtWidgets.QPushButton('Send test message')
        self.statusLayout = QtWidgets.QHBoxLayout()
        self.statusLayout.addWidget(self.addressLabel, 1)
        self.statusLayout.addWidget(self.testButton, 0)
        self.testButton.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                  QtWidgets.QSizePolicy.Minimum)
        )

        self.layout.addLayout(self.statusLayout)

        # next row: a window for displaying the incoming messages.
        self.layout.addWidget(QtWidgets.QLabel('Messages:'))
        self.messages = QtWidgets.QTextEdit()
        self.messages.setReadOnly(True)
        self.layout.addWidget(self.messages)

    @QtCore.Slot(str)
    def setListeningAddress(self, addr: str):
        self.addressLabel.setText(f"Listening on: {addr}")

    @QtCore.Slot(str, str)
    def addMessageAndReply(self, message: str, reply: str):
        tstr = time.strftime("%Y-%m-%d %H:%M:%S")
        self.messages.setTextColor(QtGui.QColor('black'))
        self.messages.append(f"[{tstr}]")
        self.messages.setTextColor(QtGui.QColor('blue'))
        self.messages.append(f"Server received: {message}")
        self.messages.setTextColor(QtGui.QColor('green'))
        self.messages.append(f"Server replied: {reply}")


class CreateInstrumentDialog(BaseDialog):
    """
    Dialog asking the user for instrument type, instrument name and any args and kwargs for its creation.
    You can pass any of the 3 fields to it to have those filled before the dialog appears.

    :param insType: Optional, The path to the instrument
    :param insName: Optional, The name of the instrument
    :param kwargsStr: Optional, String with te args and kwargs separated by commas.
    """
    createInstrument = QtCore.Signal(str, str, tuple)

    def __init__(self, insType: Optional[str] = None, insName: Optional[str] = None, kwargsStr: Optional[str] = None,
                 parent=None, flags=(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowCloseButtonHint),):
        super().__init__(parent, flags)

        tittleText = 'Create New Instrument'
        self.setWindowTitle(tittleText)
        layout = QtWidgets.QVBoxLayout(self)

        formLayout = QtWidgets.QFormLayout()
        self.typeEdit = QtWidgets.QLineEdit()
        if insType is not None:
            self.typeEdit.setText(insType)
        self.nameEdit = QtWidgets.QLineEdit()
        if insName is not None:
            self.nameEdit.setText(insName)
        self.argsEdit = AnyInputForMethod()
        if kwargsStr is not None:
            self.argsEdit.input.setText(kwargsStr)
        self.argsEdit.doEval.hide()

        formLayout.addRow(QtWidgets.QLabel('Instrument Type:'), self.typeEdit)
        formLayout.addRow(QtWidgets.QLabel('Instrument Name:'), self.nameEdit)
        formLayout.addRow(QtWidgets.QLabel('Args and Kwargs:'), self.argsEdit)

        layout.addLayout(formLayout)

        self.acceptButton = QtWidgets.QPushButton("Create")
        self.acceptButton.setDefault(True)
        buttonSizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self.acceptButton.setSizePolicy(buttonSizePolicy)
        layout.addWidget(self.acceptButton)
        layout.setAlignment(self.acceptButton, QtCore.Qt.AlignCenter)

        self.acceptButton.clicked.connect(self.onAcceptButton)

    @QtCore.Slot()
    def onAcceptButton(self):
        insType = self.typeEdit.text()
        insName = self.nameEdit.text()
        # Args is not a normal line edit, value evaluates the args and kwargs already
        args = tuple(self.argsEdit.value())
        self.createInstrument.emit(insType, insName, args)


@QtCore.Slot(str)
def onExceptionDialog(exception: str):
    """
    Opens a dialog displaying an exception.

    :param exception: The text the dialog will show
    """
    dialog = BaseDialog()
    dialog.setWindowTitle("Instrument Creation Error")
    layout = QtWidgets.QVBoxLayout(dialog)

    exceptionRaisedLabel = QtWidgets.QLabel(f"Exception Raised:")
    exceptionLabel = QtWidgets.QLabel(exception)

    accept = QtWidgets.QPushButton("Accept")

    layout.addWidget(exceptionRaisedLabel)
    layout.setAlignment(exceptionRaisedLabel, QtCore.Qt.AlignCenter)
    layout.addWidget(exceptionLabel)
    layout.setAlignment(exceptionLabel, QtCore.Qt.AlignCenter)
    layout.addWidget(accept)
    layout.setAlignment(accept, QtCore.Qt.AlignCenter)

    accept.clicked.connect(dialog.accept)
    dialog.exec_()


class PossibleInstrumentDisplayItem(QtWidgets.QTreeWidgetItem):
    """
    Items used in the PossibleInstrumentDisplay. Need to have a custom one to store extra info.
    """
    def __init__(self, text, fullInsType, configName=None, lineEdit=None, *args, **kwargs):
        super().__init__(text, *args, **kwargs)
        self.configName = configName
        self.lineEdit = lineEdit
        self.fullInsType = fullInsType


class PossibleInstrumentsDisplay(QtWidgets.QTreeWidget):
    """
    Widget that lists pre-set (either in the config or that the user adds programmatically) instruments to instantiate
    in the server.

    In it you can change the name of the new instances of instruments but the arguments are already pre-set either in
    the config or are the original args and kwargs passed when the instrument was created.
    """

    #: Signal(str, str, str) -- emitted when the one of the create buttons of the items gets pressed
    #: Arguments are in order:
    #   The name of the instrument in the config,
    #   the type of the instrument,
    #   the name in the line edit indicating what the actual name in the station should be.
    createButtonPressed = QtCore.Signal(str, str, str)

    #: Signal(str, str, str) -- emitted when the create instrument based on this instrument is triggered
    #: Arguments are in order:
    #   The name of the instrument in the config,
    #   the type of the instrument,
    #   the name in the line edit indicating what the actual name in the station should be.
    basedInstrumentRequested = QtCore.Signal(str, str, str)

    cols = ["Instrument Type & Preset", "Instrument Name", "Create Instrument"]

    def __init__(self, guiConfig: Optional[dict] = None, *args):
        super().__init__(*args)

        self.setColumnCount(len(self.cols))
        self.setHeaderLabels(self.cols)

        self.basedInstrumentAction = QtWidgets.QAction(f'Create instrument based on this')
        self.basedInstrumentAction.setShortcut('N')
        # you need to add the action to the widget so that it can detect the shortcut
        self.addAction(self.basedInstrumentAction)

        # No shortcut for this delete since qt doesn't like having multiple shortcuts on the same key
        self.deletePossibleInstrumentAction = QtWidgets.QAction("Delete")

        self.contextMenu = QtWidgets.QMenu(self)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.contextMenu.addAction(self.basedInstrumentAction)
        self.contextMenu.addSeparator()
        self.contextMenu.addAction(self.deletePossibleInstrumentAction)
        self.customContextMenuRequested.connect(lambda x: self.contextMenu.exec_(self.mapToGlobal(x)))

        self.basedInstrumentAction.triggered.connect(self.onBasedInstrumentAction)
        self.deletePossibleInstrumentAction.triggered.connect(self.onRemoveInstrumentFromTree)

        self.config = {}
        if guiConfig is not None:
            self.loadConfig(guiConfig)
            self.config = guiConfig

        self.expandAll()

    def loadConfig(self, config: dict):
        for key, value in config.items():
            # In the config, the name of the instrument and the config name are the same.
            self.addInstrumentToTree(value['type'], key, key)

        self.resizeColumnToContents(0)
        self.resizeColumnToContents(1)

    def addInstrumentToTree(self, fullInsType: str = 'InstrumentType', insName: str = 'MyInstrument', configName: Optional[str]=None):
        """
        Each type is grouped together under a parent item of that type. If that parent item does not exist yet it
        creates it
        """
        insType = fullInsType.split('.')[-1]
        items = self.findItems(insType, QtCore.Qt.MatchExactly | QtCore.Qt.MatchExactly, 0)

        # Only add the instrument to the tree if there are no other instruments of the same type already
        if len(items) == 0:
            parent = PossibleInstrumentDisplayItem(text=[insType, '', ''], fullInsType=fullInsType,)
            self.addTopLevelItem(parent)
            self.expand(self.indexFromItem(parent, 0))
        else:
            parent = items[0]

        if configName is None and insName in self.config:
            configName = insName

        lst = [configName, insName, 'create']
        lineEdit = QtWidgets.QLineEdit()
        lineEdit.returnPressed.connect(lambda: createButton.clicked.emit())
        lineEdit.setText(insName)
        item = PossibleInstrumentDisplayItem(lst, fullInsType=fullInsType, configName=configName, lineEdit=lineEdit)
        parent.addChild(item)

        createButton = QtWidgets.QPushButton("Create")
        self.setItemWidget(item, 1, lineEdit)
        self.setItemWidget(item, 2, createButton)

        createButton.clicked.connect(lambda: self.createButtonPressed.emit(configName, fullInsType, lineEdit.text()))

    def onBasedInstrumentAction(self):
        items = self.selectedItems()
        for item in items:
            insName = None
            if item.lineEdit is not None:
                insName = item.lineEdit.text()
            self.basedInstrumentRequested.emit(item.configName, item.fullInsType, insName)

    @QtCore.Slot()
    def onRemoveInstrumentFromTree(self):
        """
        Removes both the potential instrument from the widget and the presets from the config dictionary.
        """
        items = self.selectedItems()
        for item in items:
            if item.childCount() == 0:
                parent = item.parent()
                if item.configName is not None and item.configName in self.config:
                    del self.config[item.configName]
                parent.removeChild(item)
                if parent.childCount() == 0:
                    self.takeTopLevelItem((self.indexOfTopLevelItem(parent)))
            else:
                for i in range(item.childCount()):
                    child = item.child(i)
                    if child.configName in self.config:
                        del self.config[child.configName]
                self.takeTopLevelItem(self.indexOfTopLevelItem(item))


class InstrumentsCreator(QtWidgets.QWidget):
    """
    Widget that is able to instantiate new instruments in the instrumentserver.

    :param cli: client used to communicate with the server.
    :param guiConfig: The initial config of the station. This is used to know what instruments to add as potential
        display and keep track of new instruments being created to store their args and kwargs in case the user want to
        instantiate them again. Note that even though we pass the gui config around, it is the same object,
        meaning that when the main window updates the config, all of the
        configs get updated too.
    :param stationServer: The station server. We just need to connect to some of the signals that it sends
    """
    #: Signal()-- emitted when the InstrumentCreator creates a new signal. Used to close the creation instrument widget.
    newInstrumentCreated = QtCore.Signal()

    #: Signal() -- emitted when the creator tried to create a new instrument but failed.
    #: Arguments -- The str message of the error/reason as to why it could not create the instrument
    newInstrumentFailed = QtCore.Signal(object)

    def __init__(self, cli: Client, guiConfig: dict, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.guiConfig = guiConfig
        self.cli = cli

        self.possibleInstrumentDisplay = PossibleInstrumentsDisplay(guiConfig)

        self.createNewButton = QtWidgets.QPushButton("Create New Instrument")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.possibleInstrumentDisplay)
        layout.addWidget(self.createNewButton, 0)

        self.createNewButton.clicked.connect(lambda:  self.onCreateNewInstrumentClicked(None, None, None))
        self.possibleInstrumentDisplay.createButtonPressed.connect(self.onPossibleInstrumentDisplayClicked)
        self.possibleInstrumentDisplay.basedInstrumentRequested.connect(self.onCreateNewInstrumentClicked)
        self.newInstrumentFailed.connect(onExceptionDialog)

        self.setSizePolicy(QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum))

    @QtCore.Slot(str, str, str)
    def onCreateNewInstrumentClicked(self, configName: Optional[str] = None,
                                     insType: Optional[str] = None,
                                     insName: Optional[str] = None):
        # go through all the possible arguments in the config and write them in kwarg form
        kwargsStr = None
        if configName is not None and configName in self.guiConfig:
            conf = self.guiConfig[configName]
            kwargsStr = ''
            if 'address' in conf:
                kwargsStr = kwargsStr + 'address=' + str(conf['address'])
            if 'init' in conf:
                for k, v in conf['init'].items():
                    kwargsStr = kwargsStr + ',' + str(k) + '=' + str(v)
            # If there is no address argument the first item will be a comma making the creation crash
            if len(kwargsStr) > 0 and kwargsStr[0] == ',':
                kwargsStr = kwargsStr[1:]

        dialog = CreateInstrumentDialog(insType=insType, insName=insName, kwargsStr=kwargsStr, parent=self)
        dialog.createInstrument.connect(self.onDialogNewInstrument)
        self.newInstrumentCreated.connect(dialog.accept)
        dialog.exec_()

    @QtCore.Slot(str, str, tuple)
    def onDialogNewInstrument(self, insType, insName, argsKwargs):
        args, kwargs = argsKwargs

        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        self.createNewInstrument(insType, insName, *args, **kwargs)

    @QtCore.Slot(str, str, str)
    def onPossibleInstrumentDisplayClicked(self, configName, insType, insName):
        """
        Creates new instrument based on a possible instrument. Only creates it if it can find the configName in the
        config.
        """
        if configName in self.guiConfig:

            if insName in self.cli.list_instruments():
                self.newInstrumentFailed.emit(f'Instrument with name "{insName}" already exists')
                return

            # In the qcodes station config, the call the kwargs of the instrument 'init'
            kwargs = dict() if 'init' not in self.guiConfig[configName] else dict(self.guiConfig[configName]['init'])
            args = [] if 'args' not in self.guiConfig[configName] else self.guiConfig[configName]['args']

            if 'address' in self.guiConfig[configName]:
                kwargs['address'] = self.guiConfig[configName]['address']

            self.createNewInstrument(insType, insName, *args, **kwargs)

        else:
            self.newInstrumentFailed.emit("you cannot create instruments that are not in the config from here yet")

    def createNewInstrument(self, insType, insName, *args, **kwargs):
        if insName in self.cli.list_instruments():
            self.newInstrumentFailed.emit(f'Instrument "{insName}" already exists.')
            return
        try:
            self.cli.find_or_create_instrument(name=insName, instrument_class=insType, *args, **kwargs)
            self.newInstrumentCreated.emit()
        except Exception as e:
            self.newInstrumentFailed.emit(str(e))


class DeviceStatusDialog(BaseDialog):
    """Dialog showing the status of initialized devices."""
    
    def __init__(self, device_manager: DeviceInitializer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device Status")
        self.device_manager = device_manager
        
        layout = QtWidgets.QVBoxLayout(self)
        
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
        
        self.resize(400, 300)
        self.refresh_devices()
    
    def refresh_devices(self):
        self.device_list.clear()
        devices = self.device_manager.list_devices()
        for name, device in devices.items():
            self.device_list.addItem(f"{name}: {device.__class__.__name__}")
        self.status_label.setText(f"Found {len(devices)} device(s)")


class ServerGui(QtWidgets.QMainWindow):
    """Main window of the qcodes station server."""
    
    serverPortSet = QtCore.Signal(int)
    
    def __init__(self, startServer: Optional[bool] = True,
                 guiConfig: Optional[dict] = None,
                 **serverKwargs: Any):
        super().__init__()
        
        # Initialize device manager
        self.device_manager = None
        
        self._paramValuesFile = os.path.abspath(os.path.join('.', 'parameters.json'))
        self._bluePrints = {}
        self._serverKwargs = serverKwargs
        if guiConfig is None:
            self._guiConfig = {}
        else:
            self._guiConfig = guiConfig

        self.stationServer = None
        self.stationServerThread = None

        self.instrumentTabsOpen = {}

        self.setWindowTitle('Instrument server')

        # A test client, just a simple helper object.
        self.client = EmbeddedClient(raise_exceptions=False, timeout=5000000)
        self.client.recv_timeout = 10_000

        # Central widget is simply a tab container.
        self.tabs = DetachableTabWidget(self)
        self.tabs.onTabClosed.connect(self.onTabDeleted)

        self.setCentralWidget(self.tabs)

        self.stationList = StationList()
        self.stationObjInfo = StationObjectInfo()
        self.instrumentCreator = InstrumentsCreator(self.client, self._guiConfig)
        self.stationList.componentSelected.connect(self.displayComponentInfo)
        self.stationList.itemDoubleClicked.connect(self.addInstrumentToGui)
        self.stationList.closeRequested.connect(self.closeInstrument)

        stationWidgets = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        stationWidgets.addWidget(self.stationList)
        stationWidgets.addWidget(self.stationObjInfo)
        stationWidgets.setSizes([300, 500])

        instrumentsWidgets = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        instrumentsWidgets.addWidget(stationWidgets)
        instrumentsWidgets.addWidget(self.instrumentCreator)

        self.tabs.addUnclosableTab(instrumentsWidgets, 'Station')
        self.tabs.addUnclosableTab(LogWidget(level=logging.INFO), 'Log')

        self.serverStatus = ServerStatus()
        self.tabs.addUnclosableTab(self.serverStatus, 'Server')

        # Toolbar.
        self.toolBar = self.addToolBar('Tools')
        self.toolBar.setIconSize(QtCore.QSize(16, 16))

        # Station tools.
        self.toolBar.addWidget(QtWidgets.QLabel('Station:'))
        self.refreshStationAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/refresh.svg"), 'Refresh', self)
        self.refreshStationAction.triggered.connect(self.refreshStationComponents)
        self.toolBar.addAction(self.refreshStationAction)

        # Parameter tools.
        self.toolBar.addSeparator()
        self.toolBar.addWidget(QtWidgets.QLabel('Params:'))

        self.loadParamsAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/load.svg"), 'Load from file', self)
        self.loadParamsAction.triggered.connect(self.loadParamsFromFile)
        self.toolBar.addAction(self.loadParamsAction)

        self.saveParamsAction = QtWidgets.QAction(
            QtGui.QIcon(":/icons/save.svg"), 'Save to file', self)
        self.saveParamsAction.triggered.connect(self.saveParamsToFile)
        self.toolBar.addAction(self.saveParamsAction)

        # Add Devices menu
        self.devices_menu = self.menuBar().addMenu("Devices")
        
        # Initialize Devices action
        init_action = QtWidgets.QAction("Initialize Devices", self)
        init_action.triggered.connect(self.initialize_devices)
        self.devices_menu.addAction(init_action)
        
        # Show Device Status action
        status_action = QtWidgets.QAction("Show Device Status", self)
        status_action.triggered.connect(self.show_device_status)
        self.devices_menu.addAction(status_action)

        self.serverStatus.testButton.clicked.connect(
            lambda x: self.client.ask("Ping server.")
        )

        if startServer:
            self.startServer()

        # self.refreshStationComponents()

        # development options: they must always be commented out
        # printSpaceAction = QtWidgets.QAction(QtGui.QIcon(":/icons/code.svg"), 'prints empty space', self)
        # printSpaceAction.triggered.connect(lambda x: print("\n \n \n \n"))
        # self.toolBar.addAction(printSpaceAction)

    def log(self, message, level=LogLevels.info):
        log(logger, message, level)

    def closeEvent(self, event):
        if hasattr(self, 'stationServerThread'):
            if self.stationServerThread.isRunning():
                self.client.ask(self.stationServer.SAFEWORD)
        if self.device_manager is not None:
            self.device_manager.close_all()
        event.accept()

    def startServer(self):
        """Start the instrument server in a separate thread."""
        self.stationServer = StationServer(**self._serverKwargs)
        self.stationServerThread = QtCore.QThread()
        self.stationServer.moveToThread(self.stationServerThread)
        self.stationServerThread.started.connect(self.stationServer.startServer)
        self.stationServer.finished.connect(lambda: self.log('ZMQ server closed.'))
        self.stationServer.finished.connect(self.stationServerThread.quit)
        self.stationServer.finished.connect(self.stationServer.deleteLater)

        # Connecting some additional things for messages.
        self.stationServer.serverStarted.connect(self.serverStatus.setListeningAddress)
        self.stationServer.serverStarted.connect(self.client.start)
        self.stationServer.serverStarted.connect(self.refreshStationComponents)
        self.stationServer.finished.connect(
            lambda: self.log('Server thread finished.', LogLevels.info)
        )
        self.stationServer.messageReceived.connect(self._messageReceived)
        self.stationServer.instrumentCreated.connect(self.addInstrumentToGui)
        self.stationServer.funcCalled.connect(self.onFuncCalled)

        self.stationServerThread.start()

    def getServerIfRunning(self):
        if self.stationServer is not None and self.stationServerThread.isRunning():
            return self.stationServer
        else:
            return None

    @QtCore.Slot(str, str)
    def _messageReceived(self, message: str, reply: str):
        maxLen = 80
        messageSummary = message[:maxLen]
        if len(message) > maxLen:
            messageSummary += " [...]"
        replySummary = reply[:maxLen]
        if len(reply) > maxLen:
            replySummary += " [...]"
        self.log(f"Server received: {message}", LogLevels.debug)
        self.log(f"Server replied: {reply}", LogLevels.debug)
        self.serverStatus.addMessageAndReply(messageSummary, replySummary)

    def addInstrumentToGui(self, instrumentBluePrint: InstrumentModuleBluePrint, insArgs, insKwargs):
        """
        Add an instrument to the station list.

        If the guiConfig does not have an instrument with that name, it adds it.
        """
        self.stationList.addInstrument(instrumentBluePrint)
        self._bluePrints[instrumentBluePrint.name] = instrumentBluePrint

        if instrumentBluePrint.name not in self._guiConfig:
            # add the gui config for opening generic GUI's and keep track of the config
            if insArgs is None or insArgs == []:
                self._guiConfig[instrumentBluePrint.name] = dict(gui=GUIFIELD,
                                                                 type=instrumentBluePrint.instrument_module_class,
                                                                 init=insKwargs)
            else:
                self._guiConfig[instrumentBluePrint.name] = dict(gui=GUIFIELD,
                                                                 type=instrumentBluePrint.instrument_module_class,
                                                                 args=insArgs,
                                                                 init=insKwargs)

            self.instrumentCreator.possibleInstrumentDisplay.addInstrumentToTree(
                instrumentBluePrint.instrument_module_class, instrumentBluePrint.name)

    def removeInstrumentFromGui(self, name: str):
        """Remove an instrument from the station list."""
        self.stationList.removeObject(name)
        del self._bluePrints[name]
        if name in self.instrumentTabsOpen:
            self.tabs.removeTab(self.tabs.indexOf(self.instrumentTabsOpen[name]))
            del self.instrumentTabsOpen[name]

    def refreshStationComponents(self):
        """Clear and re-populate the widget holding the station components, using
        the objects that are currently registered in the station."""
        self.stationList.clear()
        for ins in self.client.list_instruments():
            bp = self.client.getBluePrint(ins)
            self.stationList.addInstrument(bp)
            self._bluePrints[ins] = bp
        self.stationList.resizeColumnToContents(0)

    def loadParamsFromFile(self):
        """Load the values of all parameters present in the server's params json file
        to parameters registered in the station (incl those in instruments)."""

        logger.info(f"Loading parameters from file: "
                    f"{os.path.abspath(self._paramValuesFile)}")
        try:
            self.client.paramsFromFile(self._paramValuesFile)
        except Exception as e:
            logger.error(f"Loading failed. {type(e)}: {e.args}")

    def saveParamsToFile(self):
        """Save the values of all parameters registered in the station (incl
         those in instruments) to the server's param json file."""

        logger.info(f"Saving parameters to file: "
                  f"{os.path.abspath(self._paramValuesFile)}")
        try:
            self.client.paramsToFile(self._paramValuesFile)
        except Exception as e:
            logger.error(f"Saving failed. {type(e)}: {e.args}")

    @QtCore.Slot(str)
    def displayComponentInfo(self, name: Union[str, None]):
        if name is not None and name in self._bluePrints:
            bp = self._bluePrints[name]
        else:
            bp = None
        self.stationObjInfo.setObject(bp)

    @QtCore.Slot(str)
    def onTabDeleted(self, name: str) -> None:
        if name in self.instrumentTabsOpen:
            del self.instrumentTabsOpen[name]

    @QtCore.Slot(str, object, object, object)
    def onFuncCalled(self, n, args, kw, ret):
        if n == 'close_and_remove_instrument':
            for ins in args:
                self.removeInstrumentFromGui(ins)

    @QtCore.Slot(str)
    def closeInstrument(self, ins):
        if ins in self.client.list_instruments():
            self.client.close_instrument(ins)

    def initialize_devices(self):
        """Initialize devices from a configuration file."""
        default_config = os.path.join(os.path.dirname(__file__), "..", "config", "devices.json")
        
        # If default config exists, use it directly
        if os.path.exists(default_config):
            try:
                # Initialize device manager if it doesn't exist
                if self.device_manager is None:
                    self.device_manager = DeviceInitializer(default_config)
                else:
                    # Reinitialize with new config
                    self.device_manager.close_all()
                    self.device_manager = DeviceInitializer(default_config)
                
                # Show success message
                QtWidgets.QMessageBox.information(
                    self,
                    "Success",
                    f"Successfully initialized devices from {default_config}"
                )
                
                # Show device status
                self.show_device_status()
                return
                
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to initialize devices: {str(e)}"
                )
                return
        
        # If default config doesn't exist, show file dialog
        config_file = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Device Configuration",
            os.path.join(os.path.dirname(__file__), "..", "config"),
            "JSON Files (*.json)"
        )[0]
        
        if config_file:
            try:
                # Initialize device manager if it doesn't exist
                if self.device_manager is None:
                    self.device_manager = DeviceInitializer(config_file)
                else:
                    # Reinitialize with new config
                    self.device_manager.close_all()
                    self.device_manager = DeviceInitializer(config_file)
                
                # Show success message
                QtWidgets.QMessageBox.information(
                    self,
                    "Success",
                    f"Successfully initialized devices from {config_file}"
                )
                
                # Show device status
                self.show_device_status()
                
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to initialize devices: {str(e)}"
                )
    
    def show_device_status(self):
        """Show the device status dialog."""
        if self.device_manager is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Warning",
                "No devices have been initialized yet."
            )
            return
        
        dialog = DeviceStatusDialog(self.device_manager, self)
        dialog.exec_()

def startServerGuiApplication(guiConfig: Optional[Dict[str, Dict[str, Any]]] = None,
                              **serverKwargs: Any) -> "ServerGui":
    """Create a server gui window.
    """
    window = ServerGui(startServer=True, guiConfig=guiConfig, **serverKwargs)
    window.show()
    return window


class EmbeddedClient(QtClient):
    """A simple client we can use to communicate with the server object
    inside the server application."""

    @QtCore.Slot(str)
    def start(self, addr: str):
        self.addr = "tcp://localhost:" + addr.split(':')[-1]
        self.connect()

    @QtCore.Slot(str)
    def ask(self, msg: str):
        logger.debug(f"Test client sending request: {msg}")
        reply = super().ask(msg)
        logger.debug(f"Test client received reply: {reply}")
        return reply


def bluePrintToHtml(bp: Union[ParameterBluePrint, InstrumentModuleBluePrint]):
    header = f"""<html>
<head>
<style type="text/css">{bpHtmlStyle}</style>
</head>
<body>
    """

    footer = """
</body>
</html>
    """
    if isinstance(bp, ParameterBluePrint):
        return header + parameterToHtml(bp, headerLevel=1) + footer
    else:
        return header + instrumentToHtml(bp) + footer


def parameterToHtml(bp: ParameterBluePrint, headerLevel=None):
    setget = []
    setgetstr = ''
    if bp.gettable:
        setget.append('get')
    if bp.settable:
        setget.append('set')
    if len(setget) > 0:
        setgetstr = f"[{', '.join(setget)}]"

    ret = ""
    if headerLevel is not None:
        ret = f"""<div class="param_container">
<div class="object_name">{bp.name} {setgetstr}</div>"""

    ret += f"""
<ul>
    <li><b>Type:</b> {bp.parameter_class} ({bp.base_class})</li>
    <li><b>Unit:</b> {bp.unit}</li>"""
    # FIXME: We deleted the validator since there is no real easy way of deserializing them. It would be a good idea to
    #  have them here though
    # <li><b>Validator:</b> {html.escape(str(bp.vals))}</li>
    var = """<li><b>Doc:</b> {html.escape(str(bp.docstring))}</li>
</ul>
</div>
    """
    return ret + var


def instrumentToHtml(bp: InstrumentModuleBluePrint):
    ret = f"""<div class="instrument_container">
<div class='instrument_name'>{bp.name}</div>
<ul>
    <li><b>Type:</b> {bp.instrument_module_class} ({bp.base_class}) </li>
    <li><b>Doc:</b> {html.escape(str(bp.docstring))}</li>
</ul>
"""

    ret += """<div class='category_name'>Parameters</div>
<ul>
    """
    for pn in sorted(bp.parameters):
        pbp = bp.parameters[pn]
        ret += f"<li>{parameterToHtml(pbp, 2)}</li>"
    ret += "</ul>"

    ret += """<div class='category_name'>Methods</div>
<ul>
"""
    for mn in sorted(bp.methods):
        mbp = bp.methods[mn]
        ret += f"""
<li>
    <div class="method_container">
    <div class='object_name'>{mbp.name}</div>
    <ul>
        <li><b>Call signature:</b> {html.escape(str(mbp.call_signature_str))}</li>
        <li><b>Doc:</b> {html.escape(str(mbp.docstring))}</li>
    </ul>
    </div>
</li>"""
    ret += "</ul>"

    ret += """
    <div class='category_name'>Submodules</div>
    <ul>
    """
    for sn in sorted(bp.submodules):
        sbp = bp.submodules[sn]
        ret += "<li>" + instrumentToHtml(sbp) + "</li>"
    ret += """
    </ul>
    </div>
    """
    return ret


bpHtmlStyle = """
div.object_name, div.instrument_name, div.category_name { 
    font-weight: bold;
}

div.object_name, div.instrument_name {
    font-family: monospace;
    background: aquamarine;
}

div.instrument_name {
    margin-top: 10px;
    margin-bottom: 10px;
    color: white;
    background: darkblue;
    padding: 10px;
}

div.instrument_container {
    padding: 10px;
}
"""
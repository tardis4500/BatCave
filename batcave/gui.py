'Module to provide PyQt helper functions'
# pylint: disable=C0103

# Import standard modules
import sys
from enum import Enum
from pathlib import Path
from string import Template

# Import GUI framework and widgets
from PyQt5.QtCore import QEvent  # pylint: disable=E0611
from PyQt5.QtGui import QIcon  # pylint: disable=E0611
from PyQt5.QtWidgets import QDialog, QFileDialog, QMainWindow, QMessageBox  # pylint: disable=E0611

# Import internal modules
from . import version
from .lang import MsgStr, FROZEN, BATCAVE_HOME

_MESSAGE_TYPES = Enum('message_types', ('about', 'info', 'question', 'warning', 'error', 'results'))


class Title(MsgStr):
    'Simplified interface for handling MessageBox titles'
    _messages = {'about': 'About ' + version.__product__,
                 'info':  version.__product__ + ' Information',
                 'question': version.__product__ + ' Question',
                 'warning': version.__product__ + ' Warning',
                 'error': version.__product__ + ' ERROR',
                 'results': 'Search Results'}

    def __init__(self, **args):
        super().__init__(transform='title', **args)


class Brief(MsgStr):
    'Simplified interface for handling brief messages'
    _messages = {'about': version.get_version_info(version.VERSION_STYLES.oneline),
                 'info':  version.__product__ + ' Information',
                 'question': version.__product__ + ' Question',
                 'warning': version.__product__ + ' Warning',
                 'error': "I'm Sorry Dave, I Can't Do That",
                 'results': 'Search Results'}


class Message(MsgStr):
    'Simplified interface for handling messages'
    _messages = {'INTERNAL_ERROR': Template('INTERNAL ERROR: Unknown $what Action'),
                 'MISSING_INFO': Template('You must $how a $what')}


class HALValidator:
    'Class to support control validation'
    def __init__(self, callback, falseval, how, what):
        self.callback = callback
        self.falseval = falseval
        self.how = how
        self.what = what


class HALGUIOutput:
    'Class to manage output to a widget.'
    def __init__(self, widget):
        self.widget = widget

    def write(self, output):
        'Writes to the widget.'
        self.widget.append(output)


class HALBaseGUI:
    ''' The base class for the simplified GUI support
        This class cannot be used by itself but must be paired with another PyQt class '''

    def __init__(self, parent=None, title=None, icon=None):  # pylint: disable=W0613
        self.setupUi(self)  # pylint: disable=E1101
        self.validators = list()
        self._saved_output_streams = None
        if title:
            self.setWindowTitle(title)  # pylint: disable=E1101
        if icon:
            self.setWindowIcon(QIcon(str(find_image(icon))))  # pylint: disable=E1101

    def validate(self):
        'Runs the validators for the window'
        for validator in self.validators:
            if validator.callback() == validator.falseval:
                MessageBox(self, Message(how=validator.how, what=validator.what).MISSING_INFO, MessageBox.MESSAGE_TYPES.error).exec()
                return False
        return True

    def redirect_output(self, widget):
        'Redirects stdout and stderr to the specified widget'
        self._saved_output_streams = (sys.stdout, sys.stderr)
        sys.stdout = sys.stderr = HALGUIOutput(widget)

    def closeEvent(self, event):
        'Standard method'
        if event.type() == QEvent.Close:
            if self._saved_output_streams:
                (sys.stdout, sys.stderr) = self._saved_output_streams


class HALMainWindow(QMainWindow, HALBaseGUI):
    'Provides functionality for a main window'
    def __init__(self, parent=None, title=None, icon=None):
        super().__init__(parent, title=(title if title else version.get_version_info(version.VERSION_STYLES.brief)), icon=icon)
        self.actionAbout.triggered.connect(self.OnAbout)

    def OnAbout(self):
        'Shows the about box'
        MessageBox(self, version.get_version_info(version.VERSION_STYLES.aboutbox), MessageBox.MESSAGE_TYPES.about).exec()


class HALDialog(QDialog, HALBaseGUI):
    'Provides functionality for a dialog box window'
    def __init__(self, **args):
        super().__init__(**args)

    def accept(self):
        'Standard dialog method.'
        return self.validate()

    def onGetFile(self, file_filter=None):
        'Simplified file dialog method.'
        edit_control = getattr(self, self.sender().objectName().replace('btn', 'edt'))
        filepath = Path(QFileDialog.getOpenFileName(self, filter=file_filter)[0])
        if filepath:
            edit_control.setText(filepath)

    def onGetDirectory(self):
        'Simplified directory dialog method.'
        edit_control = getattr(self, self.sender().objectName().replace('btn', 'edt'))
        dirpath = Path(QFileDialog.getExistingDirectory(self))
        if dirpath:
            edit_control.setText(dirpath)


class MessageBox(QMessageBox):
    'Provides functionality for a simplified message box'
    MESSAGE_TYPES = _MESSAGE_TYPES
    _MESSAGE_ICONS = {_MESSAGE_TYPES.about: QMessageBox.Information,
                      _MESSAGE_TYPES.info: QMessageBox.Information,
                      _MESSAGE_TYPES.question: QMessageBox.Question,
                      _MESSAGE_TYPES.warning: QMessageBox.Warning,
                      _MESSAGE_TYPES.error: QMessageBox.Critical,
                      _MESSAGE_TYPES.results: QMessageBox.Information}

    def __init__(self, parent, message, msg_type=_MESSAGE_TYPES.info, detail=None, image=None):
        super().__init__(parent)
        if image:
            self.setWindowIcon(QIcon(find_image(image)))
        self.setWindowTitle(getattr(Title(), msg_type.name))
        self.setIcon(self._MESSAGE_ICONS[msg_type])
        self.setText(getattr(Brief(), msg_type.name))
        self.setInformativeText(message)
        self.adjustSize()
        if detail:
            self.setDetailedText(detail)


def find_image(name):
    'Locates the image based on whether the application has been frozen'
    image_dir = BATCAVE_HOME if FROZEN else (BATCAVE_HOME / 'img')
    return [f for f in image_dir.glob(name+'.*')][0]

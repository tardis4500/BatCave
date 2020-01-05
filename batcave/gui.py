"""This module provides a simplified interface to the PyQt5 module.


Attributes:
    _MESSAGE_TYPES (Enum): The message types supported by the MessageBox class.
"""

# pylint: disable=C0103

# Import standard modules
import sys
from enum import Enum
from pathlib import Path
from string import Template

# Import GUI framework and widgets
from PyQt5.QtCore import QEvent  # pylint: disable=import-error,no-name-in-module
from PyQt5.QtGui import QIcon  # pylint: disable=import-error,no-name-in-module
from PyQt5.QtWidgets import QDialog, QFileDialog, QMainWindow, QMessageBox  # pylint: disable=import-error,no-name-in-module

# Import internal modules
from . import __title__
from .lang import MsgStr, FROZEN, BATCAVE_HOME
from .version import get_version_info, VERSION_STYLES

_MESSAGE_TYPES = Enum('message_types', ('about', 'info', 'question', 'warning', 'error', 'results'))


class Title(MsgStr):
    """Class to extend the MsgStr class for handling MessageBox titles.

    Attributes:
        _messages: The different message types.
    """
    _messages = {'about': 'About ' + __title__,
                 'info':  __title__ + ' Information',
                 'question': __title__ + ' Question',
                 'warning': __title__ + ' Warning',
                 'error': __title__ + ' ERROR',
                 'results': 'Search Results'}

    def __init__(self, **args):
        """
        Args:
            args: The list of arguments to pass to the base class.
        """
        super().__init__(transform='title', **args)


class Brief(MsgStr):
    """Class to extend the MsgStr class for handling short window messages.

    Attributes:
        _messages: The different message types.
    """
    _messages = {'about': get_version_info(VERSION_STYLES.oneline),
                 'info':  __title__ + ' Information',
                 'question': __title__ + ' Question',
                 'warning': __title__ + ' Warning',
                 'error': "I'm Sorry Dave, I Can't Do That",
                 'results': 'Search Results'}


class Message(MsgStr):
    """Class to extend the MsgStr class for handling messages.

    Attributes:
        _messages: The different message types.
    """
    _messages = {'INTERNAL_ERROR': Template('INTERNAL ERROR: Unknown $what Action'),
                 'MISSING_INFO': Template('You must $how a $what')}


class BatCaveValidator:
    """Class to support control validation."""

    def __init__(self, callback, falseval, how, what):
        """
        Args:
            callback: The callback to use for validation.
            falseval: The value to indicate a false validation.
            how: The verb to use in the error message.
            what: The noun to use in the error message.

        Attributes:
            callback: The value of the callback argument.
            falseval: The value of the falseval argument.
            how: The value of the how argument.
            what: The value of the what argument.
        """
        self.callback = callback
        self.falseval = falseval
        self.how = how
        self.what = what


class BatCaveGUIOutput:
    """Class to manage output to a widget."""

    def __init__(self, widget):
        """
        Args:
            widget: The widget to which output will be sent.

        Attributes:
            widget: The value of the widget argument.
        """
        self.widget = widget

    def write(self, output):
        'Writes to the widget.'
        self.widget.append(output)


class BatCaveBaseGUI:
    """The base class for the simplified GUI support.

    This class cannot be used by itself but must be paired with another PyQt class.
    """

    def __init__(self, _unused_parent=None, title=None, icon=None):
        """
        Args:
            _unused_parent: The parent for this object.
            title (optional, default=None): The title for this object.
            icon (optional, default=None): The icon for this object.

        Attributes:
            validators: The list of widget validators.
            _saved_output_streams: The list of saved output streams.
        """
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
        sys.stdout = sys.stderr = BatCaveGUIOutput(widget)

    def closeEvent(self, event):
        'Standard method'
        if event.type() == QEvent.Close:
            if self._saved_output_streams:
                (sys.stdout, sys.stderr) = self._saved_output_streams


class BatCaveMainWindow(QMainWindow, BatCaveBaseGUI):
    """This class provides functionality for a main window."""

    def __init__(self, parent=None, title=None, icon=None):
        """
        Args:
            parent (optional, default=None): The parent for the window.
            title (optional, default=None): The title for the window.
            icon (optional, default=None): The icon for the window.
        """
        super().__init__(parent, title=(title if title else get_version_info(VERSION_STYLES.brief)), icon=icon)
        self.actionAbout.triggered.connect(self.OnAbout)

    def OnAbout(self):
        'Shows the about box'
        MessageBox(self, get_version_info(VERSION_STYLES.aboutbox), MessageBox.MESSAGE_TYPES.about).exec()


class BatCaveDialog(QDialog, BatCaveBaseGUI):
    """This class provides functionality for a dialog box window."""

    def __init__(self, **args):
        """
        Args:
            args: The list of arguments to pass to the base class.
        """
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
    """This class provides functionality for a simplified message box.

    Attributes:
        MESSAGE_TYPES: The supported message types.
        _MESSAGE_ICONS: The supported message box icons.
    """
    MESSAGE_TYPES = _MESSAGE_TYPES
    _MESSAGE_ICONS = {_MESSAGE_TYPES.about: QMessageBox.Information,
                      _MESSAGE_TYPES.info: QMessageBox.Information,
                      _MESSAGE_TYPES.question: QMessageBox.Question,
                      _MESSAGE_TYPES.warning: QMessageBox.Warning,
                      _MESSAGE_TYPES.error: QMessageBox.Critical,
                      _MESSAGE_TYPES.results: QMessageBox.Information}

    def __init__(self, parent, message, msg_type=_MESSAGE_TYPES.info, detail=None, image=None):
        """
        Args:
            parent: The parent for the message box.
            message: The message for the message box.
            msg_type (optional, default=_MESSAGE_TYPES.info): The message type to display in the message box.
            detail (optional, default=None): The detail information to put in the message box.
            image (optional, default=None): The image to display in the message box.
        """
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
    """Locates the image based on whether the application has been frozen.

    Arguments:
        name: The name of the image to locate.

    Returns:
        The image object.
    """
    image_dir = BATCAVE_HOME if FROZEN else (BATCAVE_HOME / 'img')
    return [f for f in image_dir.glob(name+'.*')][0]

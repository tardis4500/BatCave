"""This module provides a simplified interface to the PyQt5 module.


Attributes:
    MessageType (Enum): The message types supported by the MessageBox class.
"""

# pylint: disable=too-few-public-methods,invalid-name

# Import standard modules
import sys
from enum import Enum
from pathlib import Path
from string import Template
from typing import cast, Any, Callable, List, Optional, TextIO, Tuple, Union

# Import GUI framework and widgets
from PyQt5.QtCore import QEvent  # pylint: disable=no-name-in-module
from PyQt5.QtGui import QCloseEvent, QIcon, QImage  # pylint: disable=no-name-in-module
from PyQt5.QtWidgets import QDialog, QFileDialog, QMainWindow, QMessageBox, QWidget  # pylint: disable=no-name-in-module

# Import internal modules
from . import __title__
from .lang import MsgStr, FROZEN, BATCAVE_HOME
from .version import get_version_info, VersionStyle

MessageType = Enum('MessageType', ('about', 'info', 'question', 'warning', 'error', 'results'))


class Title(MsgStr):
    """Class to extend the MsgStr class for handling MessageBox titles.

    Attributes:
        _messages: The different message types.
    """
    _messages = {'about': 'About ' + __title__,
                 'info': __title__ + ' Information',
                 'question': __title__ + ' Question',
                 'warning': __title__ + ' Warning',
                 'error': __title__ + ' ERROR',
                 'results': 'Search Results'}

    def __init__(self, **kwargs):
        """
        Args:
            **kwargs (optional, default={}): The list of arguments to pass to the base class.
        """
        super().__init__(transform='title', **kwargs)


class Brief(MsgStr):
    """Class to extend the MsgStr class for handling short window messages.

    Attributes:
        _messages: The different message types.
    """
    _messages = {'about': get_version_info(VersionStyle.oneline),
                 'info': __title__ + ' Information',
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

    def __init__(self, callback: Callable, falseval: Any, how: str, what: str):
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

    def __init__(self, widget: QWidget, /):
        """
        Args:
            widget: The widget to which output will be sent.

        Attributes:
            widget: The value of the widget argument.
        """
        self.widget = widget

    def write(self, output: str, /) -> None:
        """Write to the widget.

        Args:
            output: The text to write to the widget.

        Returns:
            Nothing.
        """
        self.widget.append(output)


class BatCaveBaseGUI:
    """The base class for the simplified GUI support.

    This class cannot be used by itself but must be paired with another PyQt class.
    """

    def __init__(self, _unused_parent: Optional[QWidget] = None, title: str = '', icon: Optional[QIcon] = None):
        """
        Args:
            _unused_parent: The parent for this object.
            title (optional, default=''): The title for this object.
            icon (optional, default=None): The icon for this object.

        Attributes:
            validators: The list of widget validators.
            _saved_output_streams: The list of saved output streams.
        """
        self.setupUi(self)  # type: ignore[attr-defined]  # pylint: disable=no-member
        self.validators: List[Any] = list()
        self._saved_output_streams: Tuple = tuple()
        if title:
            self.setWindowTitle(title)  # type: ignore[attr-defined]  # pylint: disable=no-member
        if icon:
            self.setWindowIcon(QIcon(str(find_image(icon))))  # type: ignore[attr-defined,arg-type]  # type: ignore[attr-defined]  # pylint: disable=no-member

    def closeEvent(self, event: QCloseEvent, /) -> None:
        """Overload of standard Qt method called when the object is closed.

        Returns:
            Nothing.
        """
        if event.type() == QEvent.Close:
            if self._saved_output_streams:
                (sys.stdout, sys.stderr) = self._saved_output_streams  # pylint: disable=unbalanced-tuple-unpacking

    def redirect_output(self, widget: QWidget, /) -> None:
        """Redirect stdout and stderr to the specified widget.

        Returns:
            Nothing.
        """
        self._saved_output_streams = (sys.stdout, sys.stderr)
        sys.stdout = sys.stderr = cast(TextIO, BatCaveGUIOutput(widget))

    def validate(self) -> bool:
        """Run the validators for the object.

        Returns:
            True if all the validators are True, False otherwise.
        """
        for validator in self.validators:
            if validator.callback() == validator.falseval:
                MessageBox(self, Message(how=validator.how, what=validator.what).MISSING_INFO, MessageType.error).exec()
                return False
        return True


class BatCaveMainWindow(QMainWindow, BatCaveBaseGUI):
    """This class provides functionality for a main window."""

    def __init__(self, parent: Optional[QWidget] = None, title: str = '', icon: Optional[QIcon] = None):
        """
        Args:
            parent (optional, default=None): The parent for the window.
            title (optional, default=''): The title for the window.
            icon (optional, default=None): The icon for the window.
        """
        super().__init__(parent, title=(title if title else get_version_info(VersionStyle.brief)), icon=icon)  # type: ignore[call-arg]
        self.actionAbout.triggered.connect(self.OnAbout)

    def OnAbout(self) -> None:
        """Show the about box.

        Returns:
            Nothing.
        """
        MessageBox(self, get_version_info(VersionStyle.aboutbox), MessageType.about).exec()


class BatCaveDialog(QDialog, BatCaveBaseGUI):
    """This class provides functionality for a dialog box window."""
    def accept(self) -> bool:  # type: ignore[override]
        """Overload of standard Qt method called when the dialog is accepted.

        Returns:
            The result of the validate method.
        """
        return self.validate()

    def onGetDirectory(self) -> None:
        """Show a simplified directory dialog.

        Returns:
            Nothing.
        """
        edit_control = getattr(self, self.sender().objectName().replace('btn', 'edt'))
        if dirpath := Path(QFileDialog.getExistingDirectory(self)):
            edit_control.setText(dirpath)

    def onGetFile(self, file_filter: Optional[str] = None, /) -> None:
        """Show a simplified file dialog.

        Args:
            file_filter (optional, default=None): The file filter to pass to the standard Qt file dialog.

        Returns:
            Nothing.
        """
        edit_control = getattr(self, self.sender().objectName().replace('btn', 'edt'))
        if filepath := Path(QFileDialog.getOpenFileName(self, filter=str(file_filter))[0]):
            edit_control.setText(filepath)


class MessageBox(QMessageBox):
    """This class provides functionality for a simplified message box.

    Attributes:
        _MESSAGE_ICONS: The supported message box icons.
    """
    _MESSAGE_ICONS = {MessageType.about: QMessageBox.Information,
                      MessageType.info: QMessageBox.Information,
                      MessageType.question: QMessageBox.Question,
                      MessageType.warning: QMessageBox.Warning,
                      MessageType.error: QMessageBox.Critical,
                      MessageType.results: QMessageBox.Information}

    def __init__(self, parent: Union[QWidget, BatCaveBaseGUI], message: str, /, msg_type: MessageType = MessageType.info, *, detail: str = '', image: Optional[str] = None):
        """
        Args:
            parent: The parent for the message box.
            message: The message for the message box.
            msg_type (optional, default=MessageType.info): The message type to display in the message box.
            detail (optional, default=''): The detail information to put in the message box.
            image (optional, default=None): The image to display in the message box.
        """
        super().__init__(cast(QWidget, parent))
        if image:
            self.setWindowIcon(QIcon(find_image(image)))
        self.setWindowTitle(getattr(Title(), msg_type.name))
        self.setIcon(self._MESSAGE_ICONS[msg_type])
        self.setText(getattr(Brief(), msg_type.name))
        self.setInformativeText(message)
        self.adjustSize()
        if detail:
            self.setDetailedText(detail)


def find_image(name: str, /) -> QImage:
    """Locate the image based on whether the application has been frozen.

    Args:
        name: The name of the image to locate.

    Returns:
        The image object.
    """
    image_dir = BATCAVE_HOME if FROZEN else (BATCAVE_HOME / 'img')
    return cast(QImage, [f for f in image_dir.glob(name + '.*')][0])  # pylint: disable=unnecessary-comprehension

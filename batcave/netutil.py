"""This module provides utilities for working with network services."""

# Import standard modules
from smtplib import SMTP
from typing import Dict, Optional, Tuple, Callable

# Import third-party modules
from requests import get as url_get, PreparedRequest
from requests.auth import AuthBase

# Import internal modules
from .lang import DEFAULT_ENCODING, is_debug


def download(url: str, /, target: Optional[str] = None, *, auth: Optional[Tuple[str, str] | AuthBase | Callable[[PreparedRequest], PreparedRequest]] = None) -> None:
    """Download a file from a URL target.

    Args:
        url: The URL to download from.
        target (optional, default=None): The file to which to download.
            If None, the last part of the URL will be used.
        auth (optional, default=None): If not None, it must be a (username, password) tuple.

    Returns:
        Nothing.

    Raises:
        Uses the requests module raise_for_status() function to raise on download errors.
    """
    target = target if target is not None else url.split('/')[-1]
    response = url_get(url, auth=auth, timeout=60)
    response.raise_for_status()
    with open(target, 'wb', encoding=DEFAULT_ENCODING) as downloaded_file:
        downloaded_file.write(response.content)


def send_email(smtp_server: str, receiver: str, sender: str, subject: str, body: str, /,
               content_type: str = 'text/plain') -> Dict[str, Tuple[int, bytes]]:
    """Send an SMTP email message.

    Args:
        smtp_server: The SMTP server to send the email through.
        receiver: The email address to which to send.
        sender: The return address for the email.
        subject: The email message subject.
        body: The email message body.
        content_type (optional, default='text/plain'): The content type for the email.

    Returns:
        The result of the sendmail call.
    """
    full_message = f'From: {sender}\nTo: {receiver}\nSubject: {subject}\nContent-Type: {content_type}\n\n' + '\n'.join(body)
    server = SMTP(smtp_server)
    if is_debug('SMTP'):
        server.set_debuglevel(True)
    receiver_list = receiver.split(',') if isinstance(receiver, str) else [receiver]
    try:
        result = server.sendmail(sender, receiver_list, full_message)
    finally:
        server.quit()
    return result

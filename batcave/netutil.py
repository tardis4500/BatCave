"""This module provides utilities for working with network services."""

# Import standard modules
from smtplib import SMTP

# Import third-party modules
from requests import get as url_get

# Import internal modules
from .lang import is_debug


def download(url, target=None, auth=None):
    """Download a file from a URL target.

    Arguments:
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
    response = url_get(url, auth=auth)
    response.raise_for_status()
    open(target, 'wb').write(response.content)


def send_email(smtp_server, receiver, sender, subject, body, content_type='text/plain'):
    """Send an SMTP email message.

    Arguments:
        smtp_server: The SMTP server to send the email through.
        receiver: The email address to which to send.
        sender: The return address for the email.
        subject: The email message subject.
        body: The email message body.
        content_type (optional, default='text/plain'): The content type for the email.

    Returns:
        The result of the sendmail call.
    """
    fullmsg = f'From: {sender}\nTo: {receiver}\nSubject: {subject}\nContent-Type: {content_type}\n\n' + '\n'.join(body)
    server = SMTP(smtp_server)
    if is_debug('SMTP'):
        server.set_debuglevel(True)
    if isinstance(receiver, str):
        receiver = receiver.split(',')
    try:
        result = server.sendmail(sender, receiver, fullmsg)
    finally:
        server.quit()
    return result

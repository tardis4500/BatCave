'Module with some basic network support'
# Import standard modules
from smtplib import SMTP

# Import third-party modules
from requests import get as url_get

# Import internal modules
from .lang import is_debug


def download(url, target=None, username=None, password=None):
    'Download a file form a URL target'
    target = target if target is not None else url.split('/')[-1]
    response = url_get(url, auth=((username, password) if username else None))
    response.raise_for_status()
    open(target, 'wb').write(response.content)


def send_email(smtpserver, receiver, sender, subj, msg, content_type='text/plain'):
    'Send an SMTP email message'
    fullmsg = f'From: {sender}\nTo: {receiver}\nSubject: {subj}\nContent-Type: {content_type}\n\n' + '\n'.join(msg)
    server = SMTP(smtpserver)
    if is_debug('SMTP'):
        server.set_debuglevel(True)
    if isinstance(receiver, str):
        receiver = receiver.split(',')
    try:
        result = server.sendmail(sender, receiver, fullmsg)
    finally:
        server.quit()
    return result

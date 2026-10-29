"""Native Bot API JSON transport. Tokens, messages and raw URLs are never logged."""
import json
import http.client
import logging
import socket
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


def ipv4_preferred_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """Prefer IPv4 for this transport only, retaining an IPv6 fallback."""
    host, port = address
    addresses = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    addresses.sort(key=lambda item: item[0] != socket.AF_INET)
    last_error = None
    for family, socktype, proto, _, sockaddr in addresses:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as error:
            last_error = error
            if sock is not None:
                sock.close()
    if last_error is not None:
        raise last_error
    raise OSError('No addresses returned')


class IPv4HTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        self._create_connection = ipv4_preferred_connection
        super().connect()


class IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(IPv4HTTPSConnection, req, context=self._context)


class TelegramError(Exception):
    def __init__(self, code, description, retry_after=0):
        self.code, self.description, self.retry_after = code, description, retry_after
        super().__init__(f'Telegram API error {code}')


class Telegram:
    def __init__(self, token):
        self._base = 'https://api.telegram.org/bot'+token+'/'
        self._token = token
        self._opener = urllib.request.build_opener(IPv4HTTPSHandler())

    def call(self, method, **payload):
        request = urllib.request.Request(self._base+method, json.dumps(payload).encode(), {'Content-Type':'application/json'}, method='POST')
        for attempt in range(3):
            try:
                try:
                    with self._opener.open(request, timeout=45) as response:
                        data = json.load(response)
                except urllib.error.HTTPError as exc:
                    try:
                        data = json.loads(exc.read())
                    except (ValueError, OSError):
                        raise TelegramError(exc.code, 'HTTP response without JSON') from None
                if data.get('ok'):
                    return data['result']
                error = TelegramError(data.get('error_code',500), str(data.get('description','')).replace(self._token,'[REDACTED]'), data.get('parameters',{}).get('retry_after',0))
                if error.code == 429 and attempt < 2:
                    time.sleep(min(max(error.retry_after,1),60))
                    if error.retry_after > 60:
                        raise error
                    continue
                raise error
            except (urllib.error.URLError, TimeoutError, OSError):
                # Never blindly retry send* after an ambiguous network failure.
                raise TelegramError(0, 'Network error; delivery state may be unknown') from None
        raise TelegramError(429, 'Rate limit')


def strip_icons(value):
    if isinstance(value,list):
        return [strip_icons(x) for x in value]
    if isinstance(value,dict):
        if value.get('type')=='custom_emoji':
            return value.get('alternative_text','')
        return {k:strip_icons(v) for k,v in value.items() if k not in ('icon_custom_emoji_id','style')}
    return value

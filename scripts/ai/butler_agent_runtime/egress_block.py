from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import socket


class EgressBlockedError(RuntimeError):
    pass


def _raise_blocked(*args, **kwargs):
    raise EgressBlockedError('network_egress_blocked')


@contextmanager
def block_network_calls():
    import urllib.request
    patches: list[tuple[object, str, object]] = []
    try:
        patches.append((socket, 'socket', socket.socket))
        patches.append((socket, 'create_connection', socket.create_connection))
        socket.socket = _raise_blocked
        socket.create_connection = _raise_blocked

        try:
            import requests.sessions
            patches.append((requests.sessions.Session, 'request', requests.sessions.Session.request))
            requests.sessions.Session.request = _raise_blocked
        except Exception:
            pass

        try:
            import httpx
            patches.append((httpx.Client, 'request', httpx.Client.request))
            httpx.Client.request = _raise_blocked
        except Exception:
            pass

        patches.append((urllib.request, 'urlopen', urllib.request.urlopen))
        urllib.request.urlopen = _raise_blocked

        try:
            import websockets
            patches.append((websockets, 'connect', websockets.connect))
            websockets.connect = _raise_blocked
        except Exception:
            pass
        yield
    finally:
        for obj, attr, orig in patches:
            setattr(obj, attr, orig)


def block_egress(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with block_network_calls():
            return func(*args, **kwargs)
    return wrapper


def verify_no_egress() -> tuple[bool, str]:
    try:
        with block_network_calls():
            try:
                import urllib.request
                urllib.request.urlopen('http://example.com')
            except EgressBlockedError:
                return True, 'blocked'
    except Exception:
        return False, 'block_setup_failed'
    return False, 'block_failed'

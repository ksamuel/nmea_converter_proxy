import re
import inspect


def check_port(port, _used_ports=()):
    """ Check that a port is well formated and not already taken"""
    try:
        port = int(port)
        assert 1 <= port <= 65535
        if port in _used_ports:
            ValueError("Port '%s' is already in used" % port)
        return port
    except (ValueError, AssertionError):
        msg = 'Port must be a number between 1 and 65535 not "%s"'
        raise ValueError(msg % port)


def check_ipv4(ip):
    ip = ip.strip()
    if not re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', ip):
        raise ValueError('The IP must an IP V4 address in the form of X.X.X.X')
    return ip


def ensure_awaitable(callable_obj):

    if not inspect.isawaitable(callable_obj):

        if not callable(callable_obj):
            raise TypeError("callable must be an awaitable or a callable. "
                            "Did you try to call a non coroutine "
                            "by mistake?")

        # If a coroutine function is passed instead of a coroutine, call it
        # so everything is a coroutine.
        if inspect.iscoroutinefunction(callable_obj):
            callable_obj = callable_obj()

        # If a normal function is passed, wrap it as a coroutine.
        else:
            callable_obj = asyncio.coroutine(handler)()

    return callable_obj

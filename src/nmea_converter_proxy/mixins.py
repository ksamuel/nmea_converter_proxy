
import logging
import asyncio

log = logging.getLogger(__name__)


class AutoReconnectProtocolWrapper:
    """ Wrap a protocol to make it reconnect on connection lost """

    def __init__(self, wrapped, reconnect_callback):
        self.reconnect_callback = reconnect_callback
        self.wrapped = wrapped

    def __getattr__(self, value):
        return getattr(self.wrapped, value)

    def connection_lost(self, exc):
        self.wrapped.connection_lost(exc)
        self.reconnect_callback()


class AutoReconnectTCPClient:

    protocol_factory = None
    client_name = "TCP client"
    endpoint_name = None

    def __init__(self, ip, port, endpoint_name=None, client_name=None,
                 reconnection_timer=1, protocol_factory=None):

        self.transport = self.protocol = None

        self.protocol_factory = protocol_factory or self.protocol_factory

        if not self.protocol_factory:
            raise ValueError('You must pass a protocol factory')

        self.client_name = client_name or self.client_name

        self.ip = ip
        self.port = port
        self.reconnection_timer = 1

        endpoint_name = endpoint_name or self.endpoint_name
        if endpoint_name:
            self.endpoint_name = "%s (%s:%s)" % (endpoint_name, ip, port)
        else:
            self.endpoint_name = "%s:%s" % (ip, port)

    async def ensure_connection(self):

        if not self.transport or self.transport.is_closing():
            while True:
                try:
                    log.debug('New attempt to connect to %s' % self.endpoint_name)
                    coro = self.create_connection(self.ip, self.port)
                    self.transport, self.protocol = await coro
                    # next reconnection 1 seconde after next failure
                    self.reconnection_timer = 1
                    break
                except ConnectionError as e:
                    msg = 'Unable to connect to %s: %s'
                    log.error(msg % (self.endpoint_name, e))
                    self.transport = self.protocol = None
                    # max reconnection every 10 minutes
                    if self.reconnection_timer < 600:
                        # increase the time before the next reconnection by 50%
                        self.reconnection_timer += self.reconnection_timer / 2
                    msg = 'New reconnection in %s seconds'
                    log.debug(msg % self.reconnection_timer)
                    await asyncio.sleep(self.reconnection_timer)

    def connect(self):
        log.debug('Connecting to %s on %s:%s' % (self.endpoint_name, self.ip, self.port))
        asyncio.ensure_future(self.ensure_connection())

    async def create_connection(self, ip, port):
        def factory():
            return AutoReconnectProtocolWrapper(self.protocol_factory(),
                                                self.connect)
        loop = asyncio.get_event_loop()
        con = await loop.create_connection(factory, ip, port)
        log.debug('Connected to %s on %s:%s' % (self.endpoint_name, ip, port))
        return con

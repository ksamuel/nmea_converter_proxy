
import sys
import asyncio
import logging


from nmea_converter_proxy.clients import (AanderaaClient, OptiplexClient,
                                          GenericProxyClient)

log = logging.getLogger(__name__)


class ConcentratorServerProtocol(asyncio.Protocol):
    """ Wait for the concentrator to connect and send messages to it. """

    def __init__(self, server):
        self.server = server

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        log.info('Concentrator connected on %s:%s' % self.peername)
        self.transport = transport
        self.server.clients[self.peername] = self

    def data_received(self, data):
        log.debug('Concentrator responded: {!r}'.format(data.decode()))

    def connection_lost(self):
        self.server.clients.pop(self.peername, None)


class ConcentratorServer:

    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.clients = {}
        self._server = None
        self.address = "%s:%s" % (self.ip, self.port)
        self.name = "Concentrator server (%s)" % self.address

    def connect(self):
        log.info('Concentrator server connecting to %s' % self.address)
        loop = asyncio.get_event_loop()

        def factory():
            return ConcentratorServerProtocol(self)

        coro = loop.create_server(factory, self.ip, self.port)
        self._server = loop.run_until_complete(coro)
        return self._server

    def stop(self):
        log.info('Stopping %s' % self.name)
        self._server.close()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._server.wait_closed())
        log.info('%s stopped' % self.name)

    def send(self, message):
        """ Send the message to the server or log an error """
        clients = list(self.clients.values())
        if not clients:
            msg = ("Concentrator should be sending '{!r}' but no "
                   "clients are connected")
            log.debug(msg.format(message))
        for client in clients:
            if client.transport and not client.transport.is_closing():
                msg = "{}: Sending data to {}: '{!r}'"
                log.debug(msg.format(self.name, client.peername, message))
                client.transport.write(message)
            else:
                msg = '%s: could not send data to %s: not connected'
                log.error(msg % client.peername)
                self.clients.pop(client.peername, None)


def run_server(optiplex_port, aanderaa_port, concentrator_port, concentrator_ip,
               magnetic_declination, optiplex_ip, aanderaa_ip, additional_sensors):
    """ Start the event loop with the NMEA converter proxy running """

    concentrator_server = ConcentratorServer(concentrator_ip, concentrator_port)
    try:
        concentrator_server.connect()
    except OSError as e:
        log.error("Unable to start concentrator: %s" % e)
        sys.exit(1)

    if optiplex_port:
        optiplex_client = OptiplexClient(concentrator_server,
                                         optiplex_ip, optiplex_port)
        optiplex_client.connect()
    else:
        log.warning('Optiplex not configured')

    if aanderaa_port:
        aanderaa_client = AanderaaClient(concentrator_server,
                                         magnetic_declination,
                                         aanderaa_ip, aanderaa_port)
        aanderaa_client.connect()
    else:
        log.warning('Aanderaa not configured')

    loop = asyncio.get_event_loop()

    sensor_clients = []
    for name, config in additional_sensors.items():
        client = GenericProxyClient(name, concentrator_server, **config)
        sensor_clients.append(client.connect())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        concentrator_server.stop()
        loop.close()

import asyncio
import logging
import sys

from nmea_converter_proxy.parser import (parse_optiplex_message,
                                         parse_aanderaa_message)

log = logging.getLogger(__name__)


class AanderaaProtocol(asyncio.Protocol):
    """ Receive, parse, convert and forward the aanderaa messages"""

    def __init__(self, concentrator_client):
        self.client = concentrator_client

    def connection_made(self, transport):
        peername = 'Aanderaa %s:%s' % transport.get_extra_info('peername')
        log.info('Connection from {}'.format(peername))
        self.transport = transport
        self.peername = peername

    def data_received(self, data):
        log.debug('Data received from {}'.format(self.peername))
        try:
            parsed_data = parse_aanderaa_message(data)
            message = str(parsed_data)
            log.info(message)
        except ValueError:
            log.error("Unable to parse '{!r}' from {}".format(data, self.peername))
        else:
            self.client.send(message)


class OptiplexProtocol(asyncio.Protocol):
    """ Receive, parse, convert and forward the optiplex messages"""

    def __init__(self, concentrator_client):
        self.client = concentrator_client

    def connection_made(self, transport):
        peername = 'Optiplex %s:%s' % transport.get_extra_info('peername')
        log.info('Connection from {}'.format(peername))
        self.transport = transport
        self.peername = peername

    def data_received(self, data):
        log.debug('Data received from {}'.format(self.peername))
        try:
            parsed_data = parse_optiplex_message(data)
            message = str(parsed_data)
            log.info(message)
        except ValueError:
            log.error("Unable to parse '{!r}' from {}".format(data, self.peername))
        else:
            self.client.send(message)


class ConcentratorClientProtocol(asyncio.Protocol):
    """ Connect to the concentrator and forward NMEA messages to it """

    def __init__(self, on_connection_lost):
        self.on_connection_lost = on_connection_lost

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        log.info('Connected to concentrator on %s:%s' % peername)
        self.transport = transport

    def data_received(self, data):
        log.debug('Concentrator responded: {!r}'.format(data.decode()))

    def connection_lost(self, exc):
        log.warning('Connection to NMEA concentrator lost')
        self.on_connection_lost()


class ConcentratorClient:
    """ Wraps the protocol to deal with connection lost """

    def __init__(self, loop, ip, port):
        self.transport = None
        self.protocol = None
        self.ip = ip
        self.port = port
        self.reconnection_timer = 1
        self.loop = loop
        self.schedule_reconnection()

    def schedule_reconnection(self):
        log.debug('Scheduling reconnection to NMEA concentrator')
        self.transport = self.protocol = None
        asyncio.ensure_future(self.ensure_connection())

    async def ensure_connection(self):

        if not self.transport or not self.protocol:
            try:
                log.debug('New attempt to connect to NMEA concentrator')
                coro = self.connect(self.loop, self.ip, self.port)
                self.transport, self.protocol = await coro
                # next reconnection 1 seconde after next failure
                self.reconnection_timer = 1
            except ConnectionError as e:
                log.error('Unable to connect to the NMEA concentrator: %s' % e)

                # max reconnection every 10 minutes
                if self.reconnection_timer < 600:
                    # increase the time before the next reconnection by 50%
                    self.reconnection_timer += self.reconnection_timer / 2
                    msg = 'New reconnection in %s seconds'
                    log.debug(msg % self.reconnection_timer)

                self.loop.call_later(self.reconnection_timer,
                                     self.schedule_reconnection)


    async def connect(self, loop, ip, port):
        log.debug('Connecting to NMEA concentrator on %s:%s' % (ip, port))

        def factory():
            return ConcentratorClientProtocol(self.schedule_reconnection)
        coro = loop.create_connection(factory, ip, port)
        return (await coro)



    def send(self, message, encoding="ascii"):
        """ Send the message to the server or log an error """
        log.debug("Sending '%s' to concentrator" % message)
        if not self.transport:
            log.error('Could not send data to NMEA concentrator: not connected')
        else:
            self.transport.write(message.encode(encoding))


class FakeConcentratorProtocol(asyncio.Protocol):
    """ Echo server for end to end tests """

    def connection_made(self, transport):
        peername = '%s:%s' % transport.get_extra_info('peername')
        log.info('FAKE CONCENTRATOR: Connection from {}'.format(peername))
        self.transport = transport
        self.peername = peername

    def data_received(self, data):
        msg = "FAKE CONCENTRATOR: Data received from {}: '{!r}'"
        log.info(msg.format(self.peername, data))


def run_server(optiplex_port, aanderaa_port, concentrator_port, concentrator_ip):
    """ Start the event loop with the NMEA converter proxy running """

    loop = asyncio.get_event_loop()

    concentrator_client = ConcentratorClient(loop, concentrator_ip,
                                            concentrator_port)

    def create_optiplex_protocol():  # just a factory to pass in the client
        return OptiplexProtocol(concentrator_client)
    coro = loop.create_server(create_optiplex_protocol, '0.0.0.0', optiplex_port)
    optiplex_server = loop.run_until_complete(coro)
    con = optiplex_server.sockets[0].getsockname()
    log.info('Waiting for optiplex messages on %s:%s' % con)

    def create_aanderaa_protocol():  # just a factory to pass in the client
        return AanderaaProtocol(concentrator_client)
    coro = loop.create_server(create_aanderaa_protocol, '0.0.0.0', aanderaa_port)
    aanderaa_server = loop.run_until_complete(coro)
    con = aanderaa_server.sockets[0].getsockname()
    log.info('Waiting for aanderaa messages on %s:%s' % con)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    optiplex_server.close()
    loop.run_until_complete(optiplex_server.wait_closed())

    aanderaa_server.close()
    loop.run_until_complete(aanderaa_server.wait_closed())

    loop.close()


def run_dummy_concentrator(port):
    """ Start a dummy server acting as a fake concentrator """

    loop = asyncio.get_event_loop()
    try:
        coro = loop.create_server(FakeConcentratorProtocol, '127.0.0.1', port)
        server = loop.run_until_complete(coro)
    except OSError as e:
        sys.exit(e)

    msg = 'Fake concentrator listening %s:%s'
    log.info(msg % server.sockets[0].getsockname())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()

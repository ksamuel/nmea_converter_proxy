

import sys
import asyncio
import logging
import pathlib
import tempfile

from nmea_converter_proxy.clients import AutoReconnectTCPClient

log = logging.getLogger(__name__)


class FakeConcentratorProtocol(asyncio.Protocol):
    """ Echo server for end to end tests """

    def connection_made(self, transport):
        peername = '%s:%s' % transport.get_extra_info('peername')
        log.info('FAKE CONCENTRATOR: Connection from {}'.format(peername))
        self.transport = transport
        self.peername = peername
        dump_path = pathlib.Path(tempfile.gettempdir()) / "nmea_concentrator.dump"
        self.dump = dump_path.open(mode='ab')

    def data_received(self, data):
        msg = "FAKE CONCENTRATOR: Data received from {}: '{!r}'"
        log.info(msg.format(self.peername, data))
        self.dump.write(data)
        self.dump.flush()


class FakeConcentratorClient(AutoReconnectTCPClient):
    client_name = "Fake concentrator client"
    endpoint_name = "Proxy converter"
    protocol_factory = FakeConcentratorProtocol


class FakeSensorServer(asyncio.Protocol):
    """ Send lines of a file to an IP and PORT regularly """

    def __init__(self, name, data_file, interval=1):
        self.name = "%s fake sensor" % name.upper()
        self.data_file = data_file
        self.interval = interval

    def connection_made(self, transport):
        self.peername = '%s:%s' % transport.get_extra_info('peername')
        log.info('{}: connection from {}'.format(self.name, self.peername))
        self.transport = transport
        asyncio.ensure_future(self.send_data())

    async def send_data(self):

        while True:
            try:
                for line in self.data_file:
                    if not self.transport or self.transport.is_closing():
                        break
                    self.send_message(line)
                    await asyncio.sleep(self.interval)
                self.data_file.seek(0)
            except EnvironmentError as e:
                msg = "{}: unable to open data file '{}': {}"
                log.info(msg.format(self.name, self.data_file, e))
            await asyncio.sleep(self.interval)

    def connection_lost(self, exc):
        log.info("%s: connection to %s lost" % (self.name, self.peername))

    def send_message(self, message):
        return self.send(message.encode('ascii'))

    def send(self, message):
        """ Send the message to the server or log an error """
        if self.transport and not self.transport.is_closing():
            msg = "{}: Data sent to {}: '{!r}'"
            log.debug(msg.format(self.name, self.peername, message))
            self.transport.write(message)
        else:
            msg = '%s: could not send data to %s: not connected'
            log.error(msg % (self.name, self.peername))


class FakeAanderaa(FakeSensorServer):
    """ Send data formatted as the aanderaa sensor would send """

    def send_message(self, message):
        for x in message:
            self.send(x.encode('ascii'))
            if x == " ":
                self.send(b'\x00')


def run_dummy_concentrator(port):
    """ Start a dummy server acting as a fake concentrator """

    concentrator_client = FakeConcentratorClient('127.0.0.1', port)
    concentrator_client.connect()

    msg = 'Fake concentrator connected to %s:%s'
    log.info(msg % ('127.0.0.1', port))

    loop = asyncio.get_event_loop()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        concentrator_client.stop()
        loop.close()


def run_dummy_sensor(name, port, data_file):
    """ Start a dummy server acting as a fake concentrator """

    loop = asyncio.get_event_loop()

    if name == "aanderaa":
        def factory():
            return FakeAanderaa(name, data_file)
    else:
        def factory():
            return FakeSensorServer(name, data_file)
    try:
        coro = loop.create_server(factory, '0.0.0.0', port)
        server = loop.run_until_complete(coro)
    except OSError as e:
        sys.exit(e)

    msg = 'Fake %s listening to %s:%s'
    params = (name, *server.sockets[0].getsockname())
    log.info(msg % params)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()

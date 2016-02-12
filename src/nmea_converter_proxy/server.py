import asyncio
import logging
import sys
import tempfile
import pathlib

from nmea_converter_proxy.parser import (parse_optiplex_message,
                                         parse_aanderaa_message,
                                         format_water_flow_sentence,
                                         format_temperature_sentence,
                                         format_water_depth_sentence,
                                         format_pressure_sentence)

log = logging.getLogger(__name__)


class AanderaaProtocol(asyncio.Protocol):
    """ Receive, parse, convert and forward the aanderaa messages"""

    def __init__(self, concentrator_client, magnetic_declination):
        self.client = concentrator_client
        self.magnetic_declination = magnetic_declination

    def connection_made(self, transport):
        peername = 'Aanderaa %s:%s' % transport.get_extra_info('peername')
        log.info('Connection from {}'.format(peername))
        self.transport = transport
        self.peername = peername
        self.buffer = bytearray()

    def data_received(self, data):
        log.debug('Data received from {}: "{!r}"'.format(self.peername, data))

        self.buffer.extend(data)
        if data == b'\n':
            log.debug('Buffer is ready "{!r}"'.format(self.buffer))
            self.process_full_message(self.buffer.replace(b'\x00', b' '))
            self.buffer = bytearray()

    def process_full_message(self, data):
        try:
            parsed_data = parse_aanderaa_message(data)
            log.debug("Extracted %s" % parsed_data)
        except ValueError as e:
            msg = "Unable to parse '{!r}' from {}. Error was: {}"
            log.error(msg.format(data, self.peername, e))
            return
        except Exception as e:
            logging.exception(e)
            return

        try:
            args = {
                'magnetic_degrees': parsed_data['direction'],
                'true_degrees': parsed_data['direction'] - self.magnetic_declination,
                'speed_in_knots': parsed_data['speed'] * 0.01944
            }

            water_flow_sentence = format_water_flow_sentence(**args)
            self.client.send(water_flow_sentence)
        except ValueError as e:
            msg = ("Unable to convert '{!r}' from {} to NMEA water flow "
                   "sentence. Error was: {}")
            log.error(msg.format(data, self.peername, e))
        except Exception as e:
            logging.exception(e)

        try:
            temperature = parsed_data['temperature']
            temperature_sentence = format_temperature_sentence(temperature)
            self.client.send(temperature_sentence)
        except ValueError as e:
            msg = ("Unable to convert '{!r}' from {} to NMEA temperature "
                   "sentence. Error was: {}")
            log.error(msg.format(data, self.peername, e))
        except Exception as e:
            logging.exception(e)


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
        log.debug('Data received from {}: "{!r}"'.format(self.peername, data))
        try:
            parsed_data = parse_optiplex_message(data)
            log.debug("Extracted %s" % parsed_data)
        except ValueError as e:
            msg = "Unable to parse '{!r}' from {}. Error was: {}"
            log.error(msg.format(data, self.peername, e))
        except Exception as e:
            logging.exception(e)

        value = parsed_data['value']
        unit = parsed_data['unit']

        if unit == "cm":

            try:
                water_depth_sentence = format_water_depth_sentence(value / 100)
                self.client.send(water_depth_sentence)
            except ValueError as e:
                msg = ("Unable to convert '{!r}' from {} to NMEA water depth "
                       "sentence. Error was: {}")
                log.error(msg.format(data, self.peername, e))
            except Exception as e:
                logging.exception(e)

        if unit == "hPa":
            try:
                value *= 100
                pressure_sentence = format_pressure_sentence(value)
                self.client.send(pressure_sentence)
            except ValueError as e:
                msg = ("Unable to convert '{!r}' from {} to NMEA temperature "
                       "sentence. Error was: {}")
                log.error(msg.format(data, self.peername, e))
            except Exception as e:
                logging.exception(e)


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


class ConcentratorClientProtocol(asyncio.Protocol):
    """ Connect to the concentrator and forward NMEA messages to it """

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        log.info('Connected to concentrator on %s:%s' % peername)
        self.transport = transport

    def data_received(self, data):
        log.debug('Concentrator responded: {!r}'.format(data.decode()))


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

        while self.transport and not self.transport.is_closing():
            try:
                for line in self.data_file:
                    if not self.transport or self.transport.is_closing():
                        break
                    self.send(line.encode('ascii'))
                    await asyncio.sleep(self.interval)
                self.data_file.seek(0)
            except EnvironmentError as e:
                msg = "{}: unable to open data file '{}': {}"
                log.info(msg.format(self.name, self.data_file, e))
            await asyncio.sleep(self.interval)

    def connection_lost(self, exc):
        log.info("%s: connection to %s lost" % (self.name, self.peername))

    def send(self, message):
        """ Send the message to the server or log an error """
        if self.transport and not self.transport.is_closing():
            msg = "{}: Data sent to {}: '{!r}'"
            log.debug(msg.format(self.name, self.peername, message))
            self.transport.write(message)
        else:
            msg = '%s: could not send data to %s: not connected'
            log.error(msg % (self.name, self.peername))


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


class ConcentratorClient(AutoReconnectTCPClient):
    protocol_factory = ConcentratorClientProtocol
    client_name = "Concentrator client"
    endpoint_name = "NMEA concentrator"

    def send(self, message):
        """ Send the message to the server or log an error """
        if self.transport and not self.transport.is_closing():
            msg = "{}: Data sent to {}: '{!r}'"
            log.debug(msg.format(self.client_name, self.endpoint_name, message))
            self.transport.write(message)
        else:
            msg = '%s: could not send data to %s: not connected'
            log.error(msg % (self.client_name, self.endpoint_name))


class OptiplexClient(AutoReconnectTCPClient):
    client_name = "Optiplex client"
    endpoint_name = "Optiplex"


class AanderaaClient(AutoReconnectTCPClient):
    client_name = "Aanderaa client"
    endpoint_name = "Aanderaa"


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
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()


def run_dummy_sensor(name, port, data_file):
    """ Start a dummy server acting as a fake concentrator """

    loop = asyncio.get_event_loop()

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


def run_server(optiplex_port, aanderaa_port, concentrator_port, concentrator_ip,
               magnetic_declination, optiplex_ip, aanderaa_ip):
    """ Start the event loop with the NMEA converter proxy running """

    loop = asyncio.get_event_loop()

    concentrator_client = ConcentratorClient(concentrator_ip, concentrator_port)
    concentrator_client.connect()

    if optiplex_port:
        def factory():
            return OptiplexProtocol(concentrator_client)
        optiplex_client = OptiplexClient(optiplex_ip, optiplex_port,
                                         protocol_factory=factory)
        optiplex_client.connect()
    else:
        log.warning('Optiplex not configured')

    if aanderaa_port:
        def factory():
            return AanderaaProtocol(concentrator_client, magnetic_declination)
        aanderaa_client = AanderaaClient(aanderaa_ip, aanderaa_port,
                                         protocol_factory=factory)
        aanderaa_client.connect()
    else:
        log.warning('Aanderaa not configured')

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        optiplex_client.close()
        loop.run_until_complete(optiplex_client.wait_closed())

        aanderaa_client.close()
        loop.run_until_complete(aanderaa_client.wait_closed())

        loop.close()

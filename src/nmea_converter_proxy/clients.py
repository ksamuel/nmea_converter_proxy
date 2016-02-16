
import asyncio
import logging

from nmea_converter_proxy.parser import (parse_optiplex_message,
                                         parse_aanderaa_message,
                                         format_water_flow_sentence,
                                         format_temperature_sentence,
                                         format_water_depth_sentence,
                                         format_pressure_sentence)

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
        return self

    async def create_connection(self, ip, port):
        def factory():
            return AutoReconnectProtocolWrapper(self.protocol_factory(),
                                                self.connect)
        loop = asyncio.get_event_loop()
        con = await loop.create_connection(factory, ip, port)
        log.debug('Connected to %s on %s:%s' % (self.endpoint_name, ip, port))
        return con


class GenericProxyProtocol(asyncio.Protocol):

    def __init__(self, name, concentrator_server):
        self.concentrator_server = concentrator_server
        self.name = name + " client"

    def connection_made(self, transport):
        peername = '%s:%s' % transport.get_extra_info('peername')
        log.info('Connection from {}'.format(peername))
        self.transport = transport
        self.peername = peername

    def data_received(self, data):
        msg = 'Data received on {} from {}: "{!r}"'
        log.debug(msg.format(self.name, self.peername, data))
        self.send(data)

    def send(self, data):
        self.concentrator_server.send(data)


class AanderaaProtocol(GenericProxyProtocol):
    """ Receive, parse, convert and forward the aanderaa messages"""

    def __init__(self, concentrator_server, magnetic_declination):
        self.concentrator = concentrator_server
        self.magnetic_declination = magnetic_declination
        super().__init__("Aanderaa", concentrator_server)

    def connection_made(self, transport):
        super().connection_made(transport)
        self.buffer = bytearray()

    def send(self, data):
        self.buffer.extend(data)
        if self.buffer.endswith(b'\r\n'):
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
            self.concentrator.send(water_flow_sentence)
        except ValueError as e:
            msg = ("Unable to convert '{!r}' from {} to NMEA water flow "
                   "sentence. Error was: {}")
            log.error(msg.format(data, self.peername, e))
        except Exception as e:
            logging.exception(e)

        try:
            temperature = parsed_data['temperature']
            temperature_sentence = format_temperature_sentence(temperature)
            self.concentrator.send(temperature_sentence)
        except ValueError as e:
            msg = ("Unable to convert '{!r}' from {} to NMEA temperature "
                   "sentence. Error was: {}")
            log.error(msg.format(data, self.peername, e))
        except Exception as e:
            logging.exception(e)


class OptiplexProtocol(asyncio.Protocol):
    """ Receive, parse, convert and forward the optiplex messages"""

    def __init__(self, concentrator_server):
        super().__init__("Optiplex", concentrator_server)

    def send(self, data):
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
                self.concentrator.send(water_depth_sentence)
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
                self.concentrator.send(pressure_sentence)
            except ValueError as e:
                msg = ("Unable to convert '{!r}' from {} to NMEA temperature "
                       "sentence. Error was: {}")
                log.error(msg.format(data, self.peername, e))
            except Exception as e:
                logging.exception(e)


class OptiplexClient(AutoReconnectTCPClient):
    client_name = "Optiplex client"
    endpoint_name = "Optiplex"

    def __init__(self, concentrator_server, ip, port, *args, **kwargs):

        def factory():
            return OptiplexProtocol(concentrator_server)
        super().__init__(ip, port, protocol_factory=factory)


class AanderaaClient(AutoReconnectTCPClient):
    client_name = "Aanderaa client"
    endpoint_name = "Aanderaa"

    def __init__(self, concentrator_server, ip, port, *args, **kwargs):

        def factory():
            return AanderaaProtocol(concentrator_server)
        super().__init__(ip, port, protocol_factory=factory)


class GenericProxyClient(AutoReconnectTCPClient):

    def __init__(self, name, concentrator_server, ip, port, *args, **kwargs):

        def factory():
            return GenericProxyProtocol(name, concentrator_server)
        super().__init__(ip, port, endpoint_name=name, protocol_factory=factory)

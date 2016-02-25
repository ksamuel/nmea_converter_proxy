
import asyncio
import logging

from nmea_converter_proxy.parser import (parse_optiplex_message,
                                         parse_aanderaa_message,
                                         format_water_flow_sentence,
                                         format_temperature_sentence,
                                         format_water_depth_sentence,
                                         format_pressure_sentence)

log = logging.getLogger(__name__)
asyncio.get_event_loop().set_debug(True)

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
        self.stopped = False
        self.connecter = None

        endpoint_name = endpoint_name or self.endpoint_name
        if endpoint_name:
            self.endpoint_name = "%s (%s:%s)" % (endpoint_name, ip, port)
        else:
            self.endpoint_name = "%s:%s" % (ip, port)

    async def ensure_connection(self):

        if not self.stopped:
            while True:
                try:
                    log.debug('New attempt to connect to %s' % self.endpoint_name)
                    coro = self.create_connection(self.ip, self.port)
                    self.transport, self.protocol = await coro
                    # next reconnection 1 seconde after next failure
                    self.reconnection_timer = 1
                    break
                except (ConnectionError, OSError) as e:
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
        args = (self.client_name, self.endpoint_name, self.ip, self.port)
        log.info('%s: Connecting to %s on %s:%s' % args)
        self.connecter = asyncio.ensure_future(self.ensure_connection())
        return self

    async def create_connection(self, ip, port):
        def factory():
            return AutoReconnectProtocolWrapper(self.protocol_factory(),
                                                self.connect)
        loop = asyncio.get_event_loop()
        con = await loop.create_connection(factory, ip, port)
        log.debug('Connected to %s on %s:%s' % (self.endpoint_name, ip, port))
        return con

    def stop(self):
        log.debug('Stopping {}'.format(self.client_name))
        self.stopped = True
        if self.transport:
            self.transport.close()
        if self.connecter:
            self.connecter.cancel()


class GenericProxyProtocol(asyncio.Protocol):

    def __init__(self, name, concentrator_server):
        self.concentrator_server = concentrator_server
        self.name = name + " client"

    def connection_made(self, transport):
        peername = '%s:%s' % transport.get_extra_info('peername')
        log.info('Connection from {}'.format(peername))
        self.transport = transport
        self.peername = peername
        self.buffer = bytearray()

    def data_received(self, data):
        msg = 'Data received on {} from {}: "{!r}"'
        log.debug(msg.format(self.name, self.peername, data))

        message, self.buffer = self.build_message(self.buffer, data)

        if message:
            log.debug('{}: message is ready "{!r}"'.format(self.name, message))
            self.on_message(message)

    def build_message(self, buffer, data):

        for byte in data:
            buffer.append(byte)
            if buffer.endswith(b'\r\n'):
                return buffer, bytearray()

        return None, buffer

    def on_message(self, data):
        self.concentrator_server.send(data)


class AanderaaProtocol(GenericProxyProtocol):
    """ Receive, parse, convert and forward the aanderaa messages"""

    def __init__(self, name, concentrator_server, magnetic_declination):
        self.magnetic_declination = magnetic_declination
        super().__init__(name, concentrator_server)

    def on_message(self, message):
        message = message.replace(b'\x00', b' ')
        try:
            parsed_data = parse_aanderaa_message(message)
            log.debug("Extracted %s" % parsed_data)
        except ValueError as e:
            msg = "Unable to parse '{!r}' from {}. Error was: {}"
            log.error(msg.format(message, self.peername, e))
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
            self.concentrator_server.send(water_flow_sentence)
        except ValueError as e:
            msg = ("Unable to convert '{!r}' from {} to NMEA water flow "
                   "sentence. Error was: {}")
            log.error(msg.format(message, self.peername, e))
        except Exception as e:
            logging.exception(e)

        try:
            temperature = parsed_data['temperature']
            temperature_sentence = format_temperature_sentence(temperature)
            self.concentrator_server.send(temperature_sentence)
        except ValueError as e:
            msg = ("Unable to convert '{!r}' from {} to NMEA temperature "
                   "sentence. Error was: {}")
            log.error(msg.format(message, self.peername, e))
        except Exception as e:
            logging.exception(e)


class OptiplexProtocol(GenericProxyProtocol):
    """ Receive, parse, convert and forward the optiplex messages"""

    def connection_made(self, transport):
        super().connection_made(transport)

    def on_message(self, message):
        try:
            parsed_data = parse_optiplex_message(message)
            log.debug("Extracted %s" % parsed_data)
        except ValueError as e:
            msg = "Unable to parse '{!r}' from {}. Error was: {}"
            log.error(msg.format(message, self.peername, e))
        except Exception as e:
            logging.exception(e)

        value = parsed_data['value']
        unit = parsed_data['unit']

        if unit == "cm":

            try:
                water_depth_sentence = format_water_depth_sentence(value / 100)
                self.concentrator_server.send(water_depth_sentence)
            except ValueError as e:
                msg = ("Unable to convert '{!r}' from {} to NMEA water depth "
                       "sentence. Error was: {}")
                log.error(msg.format(message, self.peername, e))
            except Exception as e:
                logging.exception(e)

        if unit == "hPa":
            try:
                value *= 100
                pressure_sentence = format_pressure_sentence(value)
                self.concentrator_server.send(pressure_sentence)
            except ValueError as e:
                msg = ("Unable to convert '{!r}' from {} to NMEA temperature "
                       "sentence. Error was: {}")
                log.error(msg.format(message, self.peername, e))
            except Exception as e:
                logging.exception(e)


class OptiplexClient(AutoReconnectTCPClient):
    client_name = "Krohne Optiflex tide sensor client"
    endpoint_name = "Krohne Optiflex tide sensor"

    def __init__(self, concentrator_server, ip, port, *args, **kwargs):

        def factory():
            return OptiplexProtocol(self.client_name, concentrator_server)
        super().__init__(ip, port, protocol_factory=factory)


class AanderaaClient(AutoReconnectTCPClient):
    client_name = "Aanderaa 4100R current meter client"
    endpoint_name = "Aanderaa 4100R current meter"

    def __init__(self, concentrator_server, magnetic_declination,
                 ip, port, *args, **kwargs):

        def factory():
            return AanderaaProtocol(self.client_name, concentrator_server,
                                   magnetic_declination)
        super().__init__(ip, port, protocol_factory=factory)


class GenericProxyClient(AutoReconnectTCPClient):

    def __init__(self, name, concentrator_server, ip, port, *args, **kwargs):

        def factory():
            return GenericProxyProtocol(name, concentrator_server)
        super().__init__(ip, port, endpoint_name=name, protocol_factory=factory)

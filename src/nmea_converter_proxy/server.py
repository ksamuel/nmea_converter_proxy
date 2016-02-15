
import sys
import asyncio
import logging

from nmea_converter_proxy.mixins import AutoReconnectTCPClient
from nmea_converter_proxy.parser import (parse_optiplex_message,
                                         parse_aanderaa_message,
                                         format_water_flow_sentence,
                                         format_temperature_sentence,
                                         format_water_depth_sentence,
                                         format_pressure_sentence)

log = logging.getLogger(__name__)


class AanderaaProtocol(asyncio.Protocol):
    """ Receive, parse, convert and forward the aanderaa messages"""

    def __init__(self, concentrator_server, magnetic_declination):
        self.concentrator = concentrator_server
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
        self.concentrator = concentrator_server

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
        self.server.clients.pop(self.peername)


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

    def send(self, message):
        """ Send the message to the server or log an error """
        for client in self.clients.values():
            if client.transport and not client.transport.is_closing():
                msg = "{}: Sending data to {}: '{!r}'"
                log.debug(msg.format(self.name, client.peername, message))
                client.transport.write(message)
            else:
                msg = '%s: could not send data to %s: not connected'
                log.error(msg % client.peername)


class OptiplexClient(AutoReconnectTCPClient):
    client_name = "Optiplex client"
    endpoint_name = "Optiplex"


class AanderaaClient(AutoReconnectTCPClient):
    client_name = "Aanderaa client"
    endpoint_name = "Aanderaa"


class GenericProxyProtocol(asyncio.Protocol):

    def __init__(self, name, concentrator_server):
        self.concentrator = concentrator_server
        self.name = name

    def connection_made(self, transport):
        peername = self.name + ' %s:%s' % transport.get_extra_info('peername')
        log.info('Connection from {}'.format(peername))
        self.transport = transport
        self.peername = peername

    def data_received(self, data):
        log.debug('Data received from {}: "{!r}"'.format(self.peername, data))
        self.concentrator_server.send(data)


class GenericProxyClient(AutoReconnectTCPClient):
    protocol_factory = GenericProxyProtocol


def run_server(optiplex_port, aanderaa_port, concentrator_port, concentrator_ip,
               magnetic_declination, optiplex_ip, aanderaa_ip, additional_sensors):
    """ Start the event loop with the NMEA converter proxy running """

    concentrator_server = ConcentratorServer(concentrator_ip, concentrator_port)
    try:
        concentrator_server.connect()
    except OSError as e:
        log.error(e)
        sys.exit(1)

    if optiplex_port:
        def factory():
            return OptiplexProtocol(concentrator_server)
        optiplex_client = OptiplexClient(optiplex_ip, optiplex_port,
                                         protocol_factory=factory)
        optiplex_client.connect()
    else:
        log.warning('Optiplex not configured')

    if aanderaa_port:
        def factory():
            return AanderaaProtocol(concentrator_server, magnetic_declination)
        aanderaa_client = AanderaaClient(aanderaa_ip, aanderaa_port,
                                         protocol_factory=factory)
        aanderaa_client.connect()
    else:
        log.warning('Aanderaa not configured')

    loop = asyncio.get_event_loop()

    sensor_clients = []
    for name, config in additional_sensors.items():

        def factory():
            return GenericProxyProtocol(name, concentrator_server)

        client = GenericProxyClient(**config, endpoint_name=name,
                                    protocol_factory=factory)
        sensor_clients.append(client.connect())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:

        for client in sensor_clients:
            optiplex_client.close()
            loop.run_until_complete(optiplex_client.wait_closed())

        optiplex_client.close()
        loop.run_until_complete(optiplex_client.wait_closed())

        aanderaa_client.close()
        loop.run_until_complete(aanderaa_client.wait_closed())

        concentrator_server.stop()

        loop.close()


import logging
import configparser
import tempfile
import pathlib
import asyncio

from logging.handlers import RotatingFileHandler

from nmea_converter_proxy.validation import check_port, check_ipv4

log = logging.getLogger(__name__)


class ConfigurationError(Exception):
    pass


TMP_DIR = pathlib.Path(tempfile.gettempdir())
LOG_FILE = TMP_DIR / 'nmea_converter_proxy.log'


def load_config(config_file):

    optiplex_port = None
    aanderaa_port = None
    concentrator_port = None
    concentrator_ip = None
    magnetic_declination = None
    optiplex_ip = None
    aanderaa_ip = None

    if not config_file.is_file():
        raise ConfigurationError('You must provide a configuration file')

    log.debug('Loading config file "%s"' % config_file)

    try:
        cfg = configparser.ConfigParser()
        cfg.read(str(config_file))

        try:
            log.debug('Getting concentrator IP')
            concentrator_ip = check_ipv4(cfg.get('concentrator', 'ip'))
            log.debug('Getting concentrator port')
            concentrator_port = check_port(cfg.get('concentrator', 'port'))
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            raise ConfigurationError('The configuration file is incomplete: %s' % e)

        try:
            log.debug('Getting optiplex port')
            optiplex_port = check_port(cfg.get('optiplex', 'port'))
            log.debug('Getting optiplex IP')
            optiplex_ip = check_ipv4(cfg.get('optiplex', 'ip'))
        except configparser.NoOptionError as e:
            raise ConfigurationError('The configuration file is incomplete: %s' % e)
        except configparser.NoSectionError:
            optiplex_port = None

        try:
            log.debug('Getting aanderaa port')
            aanderaa_port = check_port(cfg.get('aanderaa', 'port'))
            log.debug('Getting magnetic declination')
            magnetic_declination = float(cfg.get('aanderaa', 'magnetic_declination'))
            msg = "Declination must be a number between -50 and 50"
            assert -50 <= magnetic_declination <= 50, msg
            log.debug('Getting aanderaa IP')
            aanderaa_ip = check_ipv4(cfg.get('aanderaa', 'ip'))
        except configparser.NoOptionError as e:
            raise ConfigurationError('The configuration file is incomplete: %s' % e)
        except configparser.NoSectionError:
            aanderaa_port = None
            magnetic_declination = None

    except (ValueError, AssertionError, EnvironmentError, configparser.ParsingError, configparser.DuplicateSectionError) as e:
        raise ConfigurationError('Error while loading config file "%s": %s' % (config_file, e))

    additional_sensors = {}
    for section in cfg.sections():
        if section not in ('concentrator', 'optiplex', 'aanderaa'):
            if section.startswith('sensor:'):
                name = section.replace('sensor:', '')

                try:
                    log.debug('Getting %s port' % name)
                    port = check_port(cfg.get(section, 'port'))
                    log.debug('Getting %s IP' % name)
                    ip = check_ipv4(cfg.get(section, 'ip'))
                except configparser.NoOptionError as e:
                    raise ConfigurationError('The configuration file is incomplete: %s' % e)

                additional_sensors[name] = {'port': port, 'ip': ip}

    return {
       "optiplex_port": optiplex_port,
       "aanderaa_port": aanderaa_port,
       "concentrator_port": concentrator_port,
       "concentrator_ip": concentrator_ip,
       "magnetic_declination": magnetic_declination,
       "optiplex_ip": optiplex_ip,
       "aanderaa_ip": aanderaa_ip,
       "additional_sensors": additional_sensors
    }


class LoggerConfig:
    """ Wrap a sane logging setup and provide a switch for debug mode."""

    def __init__(self, name, log_file, mode):
        """ Setup logging to write in a rotating file and the console """

        self.logger = logging.getLogger(name)
        self.logger.setLevel(mode)

        self.log_file = str(log_file)

        self.stream_handler = logging.StreamHandler()

        self.file_handler = RotatingFileHandler(self.log_file, 'a', 1000000, 1)
        template = '%(asctime)s :: %(name)s :: %(levelname)s :: %(message)s'
        self.file_handler.setFormatter(logging.Formatter(template))

        self.logger.addHandler(self.stream_handler)
        self.logger.addHandler(self.file_handler)
        self.logger.addHandler

    def debug_mode(self, value):
        """ Setup debug mode """
        asyncio.get_event_loop().set_debug(value)
        for handler in (self.stream_handler, self.file_handler):
            handler.setLevel(logging.DEBUG if value else logging.INFO)

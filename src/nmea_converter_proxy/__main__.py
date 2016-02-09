
import pathlib
import logging
import tempfile
import argparse
import sys
import re
import configparser

from os.path import expanduser

from nmea_converter_proxy.log import LoggerConfig
from nmea_converter_proxy.server import run_server, run_dummy_concentrator

MODE = logging.DEBUG
TMP_DIR = pathlib.Path(tempfile.gettempdir())
LOG_FILE = TMP_DIR / 'nmea_converter_proxy.log'

logger_config = LoggerConfig('nmea_converter_proxy', LOG_FILE, logging.DEBUG)
log = logger_config.logger

parser = argparse.ArgumentParser(prog="python -m nmea_converter_proxy",
                                 description='Convert and proxy messages to an NMEA concentrator.')
parser.add_argument('--debug', action="store_true")

subparsers = parser.add_subparsers()


def exit_on_error(msg):
    log.error(msg)
    sys.exit(1)


# RUN subcommand
def run_cmd(args):
    config_file = pathlib.Path(args.config_file)

    if not config_file.is_file():
        sys.exit('You must provide a configuration file')

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
            exit_on_error('The configuration file is incomplete: %s' % e)

        try:
            log.debug('Getting optiplex port')
            optiplex_port = check_port(cfg.get('optiplex', 'port'))
        except configparser.NoOptionError as e:
            exit_on_error('The configuration file is incomplete: %s' % e)
        except configparser.NoSectionError:
            optiplex_port = None

        try:
            log.debug('Getting aanderaa port')
            aanderaa_port = check_port(cfg.get('aanderaa', 'port'))
            log.debug('Getting magnetic declination')
            magnetic_declination = float(cfg.get('aanderaa', 'magnetic_declination'))
            msg = "Declination must be a number between -50 and 50"
            assert -50 <= magnetic_declination <= 50, msg
        except configparser.NoOptionError as e:
            exit_on_error('The configuration file is incomplete: %s' % e)
        except configparser.NoSectionError:
            aanderaa_port = None
            magnetic_declination = None

    except (ValueError, AssertionError, EnvironmentError, configparser.ParsingError) as e:
        exit_on_error('Error while loading config file "%s": %s' % (config_file, e))

    run_server(optiplex_port=optiplex_port,
               aanderaa_port=aanderaa_port,
               concentrator_port=concentrator_port,
               concentrator_ip=concentrator_ip,
               magnetic_declination=magnetic_declination)

run = subparsers.add_parser('run')
run.add_argument('config_file', metavar="CONFIG_FILE", help='.ini configuration file')
run.set_defaults(func=run_cmd)


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


# INIT subcommand
def init_cmd(args):
    print('This will generate the config file. ')

    def request_port(msg, _used_ports=[]):
        while True:
            default_port = port = next(iter(_used_ports), 8499) + 1
            port = input(msg % default_port)
            if not port:
                port = default_port
            try:
                port = check_port(port, _used_ports)
                _used_ports.insert(0, port)
                return port
            except ValueError as e:
                print(e)

    while True:
        msg = 'IP of the NMEA concentrator [default is 127.0.0.1]: '
        concentrator_ip = input(msg)
        if not concentrator_ip:
            concentrator_ip = "127.0.0.1"
        try:
            concentrator_ip = check_ipv4(concentrator_ip)
            break
        except ValueError as e:
            print(e)

    concentrator_port = request_port('Port of the NMEA concentrator [%s]: ')

    optiplex_port = request_port('Port for incomming Optiplex messages [%s]: ')

    aanderaa_port = request_port('Port for incomming Aanderaa messages [%s]: ')

    while True:
        msg = 'Magnetic declination for the aanderaa sensor [default is 0.5]'
        magnetic_declination = input(msg)
        if not magnetic_declination:
            magnetic_declination = -0.5
        try:
            magnetic_declination = float(magnetic_declination)
            assert -50 <= magnetic_declination <= 50
            break
        except (ValueError, AssertionError) as e:
            print("Magnetic declination must be a number between -50 and 50")

    home = pathlib.Path(expanduser("~"))
    default_config_file = home / 'nmea_converter_proxy.ini'
    while True:
        msg = 'Where to save the file ? [default: "%s"]: '
        config_file = input(msg % default_config_file)
        if not config_file:
            config_file = default_config_file
        config_file = pathlib.Path(config_file)
        try:
            if config_file.is_file():
                res = input('File already exist. Overwrite ? [Y/n] ')
                if not res.lower().strip() in ('y', 'yes', ''):
                    continue
            with config_file.open('w') as f:
                cfg = configparser.ConfigParser()
                cfg.add_section('optiplex')
                cfg.set('optiplex', 'port', str(optiplex_port))
                cfg.add_section('aanderaa')
                cfg.set('aanderaa', 'port', str(aanderaa_port))
                cfg.set('aanderaa', 'magnetic_declination', str(magnetic_declination))
                cfg.add_section('concentrator')
                cfg.set('concentrator', 'ip', concentrator_ip)
                cfg.set('concentrator', 'port', str(concentrator_port))
                cfg.write(f)

                print('File config file saved.')
                print('Now you can start the proxy with by running:')
                print('python -m nmea_converter_proxy run "%s"' % config_file)
            break
        except EnvironmentError:
            config_file = None
            print("Cannot write a file to '%s'" % config_file)


run = subparsers.add_parser('init')
run.set_defaults(func=init_cmd)


# FAKECONCENTRATOR subcommand
def fake_concentrator_cmd(args):
    try:
        port = check_port(args.port)
    except ValueError as e:
        sys.exit(e)
    run_dummy_concentrator(port)

fake_concentrator = subparsers.add_parser('fakeconcentrator')
fake_concentrator.set_defaults(func=fake_concentrator_cmd)
fake_concentrator.add_argument('--port', default=8500, nargs='?')


# LOG subcommand
def log_file_cmd(args):
    try:
        with LOG_FILE.open() as f:
            lines = f.readlines()[-10:]
            if lines:
                print('Last lines of log:\n')
                for line in lines:
                    print(line, end='')
            else:
                print('Log is empty')
            print('\nRead the full log at %s' % LOG_FILE)
    except EnvironmentError:
        sys.exit('Could not open any log file at "%s"' % LOG_FILE)

log_file = subparsers.add_parser('log')
log_file.set_defaults(func=log_file_cmd)

# parsing command line argument and running the proper subcommand
args = parser.parse_args()
logger_config.debug_mode(args.debug)
if not hasattr(args, 'func'):
    parser.print_usage()
else:
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit('Program interrupted manually')

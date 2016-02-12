
import pathlib
import logging
import sys
import configparser

from os.path import expanduser

from nmea_converter_proxy.utils import text_resource_stream
from nmea_converter_proxy.server import (run_server, run_dummy_concentrator,
                                         run_dummy_sensor)
from nmea_converter_proxy.conf import load_config, LOG_FILE, ConfigurationError
from nmea_converter_proxy.validation import (check_ipv4, check_port,
                                             ValidationError, check_file)

log = logging.getLogger(__name__)


def exit_on_error(msg):
    log.error(msg)
    sys.exit(1)


# RUN subcommand
def run_cmd(args):
    config_file = pathlib.Path(args.config_file)
    try:
        conf = load_config(config_file)
    except ConfigurationError as e:
        exit_on_error(e)
    run_server(**conf)


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

    def request_ip(msg, default="127.0.0.1"):
        while True:
            ip = input(msg % default)
            if not ip:
                ip = default
            try:
                return check_ipv4(ip)
            except ValueError as e:
                print(e)

    concentrator_ip = request_ip('IP of the NMEA concentrator [%s]: ')
    concentrator_port = request_port('Port of the NMEA concentrator [%s]: ')

    optiplex_ip = request_ip('IP for incomming Optiplex messages [%s]: ')
    optiplex_port = request_port('Port for incomming Optiplex messages [%s]: ')

    aanderaa_ip = request_ip('IP for incomming Aanderaa messages [%s]: ')
    aanderaa_port = request_port('Port for incomming Aanderaa messages [%s]: ')

    while True:
        msg = 'Magnetic declination for the aanderaa sensor [0.5]: '
        magnetic_declination = input(msg)
        if not magnetic_declination:
            magnetic_declination = -0.5
        try:
            magnetic_declination = float(magnetic_declination)
            assert -50 <= magnetic_declination <= 50
            break
        except (ValueError, AssertionError):
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
                cfg.set('optiplex', 'ip', optiplex_ip)
                cfg.add_section('aanderaa')
                cfg.set('aanderaa', 'port', str(aanderaa_port))
                cfg.set('aanderaa', 'ip', aanderaa_ip)
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


def fake_concentrator_cmd(args):
    try:
        port = check_port(args.port)
    except ValueError as e:
        sys.exit(e)
    run_dummy_concentrator(port)


def fake_optiplex_cmd(args):
    try:
        port = check_port(args.port)
    except ValueError as e:
        sys.exit(e)

    if args.data_file:
        try:
            data_file = check_file(args.data_file)
            data_file = data_file.open()
        except ValidationError as e:
            sys.exit(e)
    else:
        data_file = text_resource_stream('fixtures/optiplex_fake_data.txt',
                                         "nmea_converter_proxy",
                                         newline='\r\n')

    run_dummy_sensor("optiplex", port, data_file)


def fake_aanderaa_cmd(args):
    try:
        port = check_port(args.port)
    except ValueError as e:
        sys.exit(e)

    if args.data_file:
        try:
            data_file = check_file(args.data_file)
            data_file = data_file.open()
        except ValidationError as e:
            sys.exit(e)
    else:
        data_file = text_resource_stream('fixtures/aanderaa_fake_data.txt',
                                         "nmea_converter_proxy",
                                         newline='\r\n')

    run_dummy_sensor("aanderaa", port, data_file)


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

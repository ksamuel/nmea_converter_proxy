
import re
from datetime import datetime

optiplex_pattern = re.compile(r"""(?P<timestamp>\d{8}\s*\d{6})\s*
                         (?P<value>[+-]?[0-9.]+)\s*
                         (?P<unit>[a-zA-Z]+)\s*
                         (?P<alert>\d*)
                      """, re.VERBOSE)


def parse_optiplex_message(message):
    """ Parse a message sent from the optiplex sensor

        Data format example:
            20101217 150000 +0543.8 cm 0\r\n
            20101217150001+0544.0cm0\r\n
            201012171500011001.6hPa\r\n
            20101217150002+0544.1cm0\r\n
    """
    try:
        message = message.decode('ascii')
        data = optiplex_pattern.search(message).groupdict()
        timestamp = data['timestamp'].replace(' ', '')
        data['timestamp'] = datetime.strptime(timestamp, '%Y%m%d%H%M%S')
        data['value'] = float(data['value'])
        data['alert'] = int(data['alert']) if data['alert'] else None
    except (AttributeError, ValueError):
        raise ValueError("Can't parse message '%s'" % message.strip())
    return data


def parse_aanderaa_message(message):
    """ Parse a message sent from the aanderaa sensor

        Data format example:
            0701 0116 0906 0366\r\n
            0701 0106 0912 0366\r\n
            0699 0111 0915 0366\r\n
            0702 0116 0919 0366\r\n
            0704 0097 0938 0366\r\n
            0701 0089 0928 0366\r\n
            0699 0087 0945 0366\r\n
            0701 0080 0954 0366\r\n
    """
    try:
        message = message.decode('ascii')
        reference, speed, direction, temperature = message.strip().split()
        return {
            'reference': int(reference),
            'speed': int(speed) * 2.933E-01,  # cm/s
            'direction': int(direction) * 3.516E-01,  # Deg.M
            'temperature': int(temperature) * 5.181E-02  # Deg.C
        }
    except (IndexError, ValueError):
        raise ValueError("Can't parse message '%s'" % message.strip())




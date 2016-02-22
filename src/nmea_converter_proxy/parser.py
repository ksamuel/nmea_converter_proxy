
import re
import operator
from datetime import datetime
from functools import reduce


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


def raw_temp_to_celsius(value):
    v = int(value)
    a = -8.75
    b = 5.181E-02
    c = 0
    d = 0
    return a + b*v + c*v**2 + d*v**3

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
            'temperature': raw_temp_to_celsius(temperature)  
        }
    except (IndexError, ValueError):
        raise ValueError("Can't parse message '%s'" % message.strip())


def format_as_nmea(values, prefix="$"):
    string = ",".join(str(x) for x in values)
    control_sum = reduce(operator.xor, (ord(x) for x in string), 0)
    sentence = "{}{}*{:X}\r\n".format(prefix, string, control_sum)
    size = len(sentence)
    if size > 82:
        raise ValueError('Resulting NMEA sentence would be longer than allowed '
                         '82 characters: %s (%s chars)' % sentence, size)
    return sentence.encode('ascii')


def format_water_flow_sentence(true_degrees, magnetic_degrees, speed_in_knots):

    aanderaa_code = 'VW'  # MNEA code for "Weather Instruments"
    data_code = 'VDR'  # MNEA code for "Set and Drift"

    data = [
        aanderaa_code + data_code,
        "{:.1f}".format(true_degrees),
        'T',
        "{:.1f}".format(magnetic_degrees),
        'M',
        "{:.1f}".format(speed_in_knots),
        'N'
    ]

    return format_as_nmea(data)


def format_temperature_sentence(celsius_degrees):

    aanderaa_code = 'VW'  # MNEA code for "Weather Instruments"
    data_code = 'MTW'  # MNEA code for "Water Temperature"

    data = [
        aanderaa_code + data_code,
        "{:.1f}".format(celsius_degrees),
        'C'
    ]

    return format_as_nmea(data)


def format_water_depth_sentence(meters):

    aanderaa_code = 'VW'  # MNEA code for "Weather Instruments"
    data_code = 'DPT'  # MNEA code for "Water Temperature"

    data = [
        aanderaa_code + data_code,
        "{:.2f}".format(meters),
        "",
        ""
    ]

    return format_as_nmea(data)


def format_pressure_sentence(pascal):

    aanderaa_code = 'P'  # MNEA code for "Proprietary format"
    data_code = 'PRE'  # Proprietary code for "Pressure"

    data = [
        aanderaa_code + data_code,
        "{:.1f}".format(pascal),
        'P'
    ]

    return format_as_nmea(data, prefix="!")


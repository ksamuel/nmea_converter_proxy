
from datetime import datetime

from nmea_converter_proxy.parser import (parse_optiplex_message,
                                         parse_aanderaa_message,
                                         format_as_nmea)


def test_import():
    import nmea_converter_proxy  # noqa


def test_parse_optiplex_message():

    optiplex_messages = [
        b'20101217150000+0543.8cm0\r\n',
        b'20101217150001+0544.0cm0\r\n',
        b'201012171500011001.6hPa\r\n',
        b'20101217150002+0544.1cm0\r\n',
        b'20160203 145313 +0365.0 cm 0\r\n',
        b'20160203 145314 +0364.4 cm 0\r\n',
        b'20160203 145315 +0364.8 cm 0\r\n',
        b'20160203 145316 +0363.8 cm 0\r\n',
    ]

    expected_data = [
        {'timestamp': datetime(2010, 12, 17, 15, 0),
         'alert': 0,
         'unit': 'cm',
         'value': 543.8},
        {'timestamp': datetime(2010, 12, 17, 15, 0, 1),
         'alert': 0,
         'unit': 'cm',
         'value': 544.0},
        {'timestamp': datetime(2010, 12, 17, 15, 0, 1),
         'alert': None,
         'unit': 'hPa',
         'value': 1001.6},
        {'timestamp': datetime(2010, 12, 17, 15, 0, 2),
         'alert': 0,
         'unit': 'cm',
         'value': 544.1},
        {'timestamp': datetime(2016, 2, 3, 14, 53, 13),
         'alert': 0,
         'unit': 'cm',
         'value': 365.0},
        {'timestamp': datetime(2016, 2, 3, 14, 53, 14),
         'alert': 0,
         'unit': 'cm',
         'value': 364.4},
        {'timestamp': datetime(2016, 2, 3, 14, 53, 15),
         'alert': 0,
         'unit': 'cm',
         'value': 364.8},
        {'timestamp': datetime(2016, 2, 3, 14, 53, 16),
         'alert': 0,
         'unit': 'cm',
         'value': 363.8},
    ]

    for msg, data in zip(optiplex_messages, expected_data):
        assert parse_optiplex_message(msg) == data

def test_parse_aanderaa_message():

    aanderaa_messages = [
        b'0701 0116 0906 0366\r\t',
        b'0701 0106 0912 0366\r\t',
        b'0699 0111 0915 0366\r\t',
        b'0702 0116 0919 0366\r\t',
        b'0704 0097 0938 0366\r\t',
        b'0701 0089 0928 0366\r\t',
        b'0699 0087 0945 0366\r\t',
        b'0701 0080 0954 0366\r\t',
    ]

    expected_data = [
        {'direction': 318.5496,
         'temperature': 18.96246,
         'reference': 701,
         'speed': 34.022800000000004},
        {'direction': 320.6592,
         'temperature': 18.96246,
         'reference': 701,
         'speed': 31.0898},
        {'direction': 321.714,
         'temperature': 18.96246,
         'reference': 699,
         'speed': 32.5563},
        {'direction': 323.1204,
         'temperature': 18.96246,
         'reference': 702,
         'speed': 34.022800000000004},
        {'direction': 329.80080000000004,
         'temperature': 18.96246,
         'reference': 704,
         'speed': 28.4501},
        {'direction': 326.2848,
         'temperature': 18.96246,
         'reference': 701,
         'speed': 26.1037},
        {'direction': 332.262,
         'temperature': 18.96246,
         'reference': 699,
         'speed': 25.5171},
        {'direction': 335.4264,
         'temperature': 18.96246,
         'reference': 701,
         'speed': 23.464},
    ]

    for msg, data in zip(aanderaa_messages, expected_data):
        assert parse_aanderaa_message(msg) == data


def test_nmea_formatter():

    sentence = format_as_nmea(['GPGLL', '5057.970', 'N', '00146.110',
                              'E', '142451', 'A'])
    assert sentence == b'$GPGLL,5057.970,N,00146.110,E,142451,A*27\r\n'

    sentence = format_as_nmea(['GPVTG', '089.0', 'T', '',
                              '', '15.2', 'N', '', ''])
    assert sentence == b'$GPVTG,089.0,T,,,15.2,N,,*7F\r\n'


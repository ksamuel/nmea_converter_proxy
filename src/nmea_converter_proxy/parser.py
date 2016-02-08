
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


def format_as_nmea(values):
    string = ",".join(str(x) for x in values)
    control_sum = reduce(operator.xor, (ord(x) for x in string), 0)
    sentence = "${}*{:X}\r\n".format(string, control_sum)
    size = len(sentence)
    if size > 82:
        raise ValueError('Resulting NMEA sentence would be longer than allowed '
                         '82 characters: %s (%s chars)' % sentence, size)
    return sentence.encode('ascii')

# browserRequest=true
# lat1=1
# lat1Hemisphere=N
# lon1=1
# lon1Hemisphere=W
# model=WMM
# startYear=2016
# startMonth=2
# startDay=8
# resultFormat=csv
#
# curl 'http://www.ngdc.noaa.gov/geomag-web/calculators/calculateDeclination' --1.0 -H 'Host: www.ngdc.noaa.gov' -H 'User-Agent: Mozilla/5.0 (X11; Linux i686; rv:43.0) Gecko/20100101 Firefox/43.0' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'DNT: 1' -H 'Referer: http://www.ngdc.noaa.gov/geomag-web/?model=WMM&lon1=&startYear=2016&startDay=7&lat1Hemisphere=N&resultFormat=csv&browserRequest=true&startMonth=2&lat1=&lon1Hemisphere=W&fragment=declination' -H 'Cookie: JSESSIONID=B30D6BEB2C50DA249D4A7A5AE9D15B58' -H 'Connection: keep-alive' --data 'browserRequest=true&lat1=1&lat1Hemisphere=N&lon1=1&lon1Hemisphere=W&model=WMM&startYear=2016&startMonth=2&startDay=8&resultFormat=csv'
#
#
#import urllib.request, urllib.parse, urllib.error
# import socket

# try:
#     details = urllib.parse.urlencode({ 'IDToken1': 'USERNAME', 'IDToken2': 'PASSWORD' })
#     url = urllib.request.Request('https://login1.telecom.co.nz/distauth/UI/Login?realm=XtraUsers&goto=https%3A%2F%2Fwww.telecom.co.nz%3A443%2Fjetstreamum%2FxtraSum%3Flink%3Drdt', details)
#     url.add_header("User-Agent","Mozilla/5.0 (Windows; U; Windows NT 6.0; en-US) AppleWebKit/525.13 (KHTML, like Gecko) Chrome/0.2.149.29 Safari/525.13")

#     responseData = urllib.request.urlopen(url).read().decode('utf8', 'ignore')

# except urllib.error.HTTPError as e:
#     responseData = e.read().decode('utf8', errors='ignore')
#     e.getcode()

# except urllib.error.URLError:

# except socket.error:

# except socket.timeout:

# except UnicodeEncodeError:
#     print("[x]  Encoding Error")
#     responseFail = True

# print(responseData)
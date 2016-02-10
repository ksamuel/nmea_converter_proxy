NMEA converter proxy
---------------------


TCP proxy forwarding ASCII messages to an NMEA concentrator


First setup
===========

Install Python3.5 from https://www.python.org/ftp/python/3.5.1/python-3.5.1-amd64.exe.

(make sure you get the 64 bits installer on a 64bits install).

Ensure you have "Add to System path" checked in the installer.

Download the zipped Python code at https://github.com/ksamuel/nmea_converter_proxy/archive/master.zip.

Unzip nmea_converter_proxy.zip. Hold Ctrl and right click on the directory icon to open a new terminal windows inside the directory.

Type::


    python setup.py install
    python -m nmea_converter_proxy init


Follow the instructions.

Running from an existing configuration file
=============================================

Open a new terminal windows and type::

    python -m nmea_converter_proxy run "c:\path\to\your\config\file.ini"

Config file format::
    
    [optiplex]
    port = port where the optiplex sensor sends messages to
    
    [aanderaa]
    port = port where the aanderaa sensor sends messages to
    magnetic_declination = magnetic declination at the sensor location
    
    [concentrator]
    ip = IPV4 address where the NMEA concentrator is located
    port = port the NMEA concentrator is expecting messages
    

Example::

    [optiplex]
    port = 8502
    
    [aanderaa]
    port = 8501
    magnetic_declination = -0.5
    
    [concentrator]
    ip = 89.32.00.1
    port = 8500



NMEA massages formats
=============================================


Water flow sentence::

    $VWVDR,<true degrees>,T,<magnetic degrees>,M,<speed in knots>,N*<checksum>\r\n

E.G::

    $VWVDR,318.0,T,318.5,M,34.0,N*A\r\n


Temperature sentence::

    $VWMTW,<celsius degrees>,C*<checksum>\r\n
    
E.G::

    $VWMTW,17.1,C*15\r\n

Water depth variation sentence::

    $VWDPT,<meter>,<empty field>,*<checksum>\r\n

E.G::

    $VWDPT,5.4,,*42\r\n
    $VWDPT,-1.0,,*6F\r\n
    


Pressure sentence::

    b"!PPRE,<pascals>,P*<checksum>\r\n"

E.G::

    !PPRE,102400.0,P*5E\r\n
    
Note that, because I couldn't find a suitable message to send pressure, I had to use NEMA hability to define a proprietary format with "!".



Help and debug
==============

Find out more about log by doing::


    python -m nmea_converter_proxy log


You can get help on the command line tool by typing::


    python -m nmea_converter_proxy --help


Or::


    python -m nmea_converter_proxy [command] --help


If you can't run the command "python", make sure you have the directory containing Python added to your system path.

If you have several versions of Python installed at the same time, you can run a one in particular by doing::

    
    C:\direct\path\to\python.exe nmea_converter_proxy [command]
    
    
Activate more verbosity by activating the debug mode::


    python -m nmea_converter_proxy --debug [command]


Development
============

Install in editable mode::


    python -m pip install -e .[dev]
    
Run a fake concentrator::

    python -m nmea_converter_proxy fakeconcentrator


Style Guide:

 - Python: PEP8 (https://www.python.org/dev/peps/pep-0008/)
 - JS: Google (http://google-styleguide.googlecode.com/svn/trunk/javascriptguide.xml)

Deactivate dev mode::

    python setup.py develop --uninstall

Running all tests::

    python setup.py test

Install and run tox to check coverage and unit test at once::

    python -m pip install tox
    python -m tox

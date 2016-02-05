
import logging

import asyncio

from logging.handlers import RotatingFileHandler


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

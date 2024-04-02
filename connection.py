# encoding: utf-8
# Revisión 2019 (a Python 3 y base64): Pablo Ventura
# Copyright 2014 Carlos Bederián
# $Id: connection.py 455 2011-05-01 00:32:09Z carlos $

from base64 import b64encode
from constants import EOL
import re
import socket as s
from typing import Callable, List, Tuple, Union

BUFFER_SIZE = 1024


class Connection(object):
    """
    Conexión punto a punto entre el servidor y un cliente.
    Se encarga de satisfacer los pedidos del cliente hasta
    que termina la conexión.
    """

    socket: s.socket
    dir: str
    commands: List[Tuple[str, Callable[[List[str]], None]]]

    # the remaining data after calling recv_line()
    remaining_data: str

    quit: bool

    def __init__(self, socket: s.socket, directory: str):
        self.socket = socket
        self.dir = directory
        self.commands = [
            (r"^get_slice (\d+) (\d+) (\d+)\r\n$", self.get_slice_handler),
            (r"^quit\r\n$", self.quit_handler)
        ]
        self.remaining_data = ""
        self.quit = False

    def send(self, msg: str):
        msg += EOL

        while msg:
            bytes_sent = self.socket.send(msg.encode('ascii'))
            msg = msg[bytes_sent:]

    def recv_line(self) -> Union[str, None]:
        # Start the line with the remaining data of the previous recv()
        line = self.remaining_data
        self.remaining_data = ""

        while True:
            try:
                data = self.socket.recv(BUFFER_SIZE).decode('ascii')
            except UnicodeDecodeError:
                print("ERROR: message contains invalid ascii.")
                return None

            if len(data) == 0:
                return None

            eol_index = data.find(EOL)
            if eol_index == -1:
                # No EOL found, keep receiving
                line += data
                continue

            next_line_index = eol_index + len(EOL)

            line += data[0:next_line_index]
            # Set leftovers as the remaining data
            self.remaining_data = data[next_line_index:]

            return line

    def quit_handler(self, args):
        print("QUITTY")
        self.quit = True

    def get_slice_handler(self, args):
        pass

    def process_line(self, line: str):
        for (pattern, handler) in self.commands:
            match = re.search(pattern, line)
            if match is not None:
                handler(match.groups())
                return True

        return False

    def handle(self):
        """
        Atiende eventos de la conexión hasta que termina.
        """
        while not self.quit:
            line = self.recv_line()
            if line is None:
                break

            if not self.process_line(line):
                print("ERRRRRRROOROROROROROROROROR")

        print("Terminating connection with client.")

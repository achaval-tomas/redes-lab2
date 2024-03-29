# encoding: utf-8
# Revisión 2019 (a Python 3 y base64): Pablo Ventura
# Copyright 2014 Carlos Bederián
# $Id: connection.py 455 2011-05-01 00:32:09Z carlos $

import socket
from constants import *
from base64 import b64encode
import re

class Connection(object):
    """
    Conexión punto a punto entre el servidor y un cliente.
    Se encarga de satisfacer los pedidos del cliente hasta
    que termina la conexión.
    """

    def __init__(self, socket, directory):
        self.socket = socket
        self.dir = directory
        self.buffer = ""
        self.quit = False
        self.commands = [
            (r"^get_slice (\d+) (\d+) (\d+)\r\n$", self.get_slice_handler),
            (r"^quit\r\n$", self.quit_handler)
        ]


    def recv_line(self):
        self.buffer = ""
        read_cr = False
        while True:
            data = self.socket.recv(1).decode('ascii')
            if len(data) == 0:
                return False
            
            assert len(data) == 1
            [data] = data
            
            self.buffer += data

            if data == EOL[0]:
                read_cr = True
            elif data == EOL[1]:
                return read_cr


    def quit_handler(self, args):
        print("QUITTY")
        self.quit = True


    def get_slice_handler(self, args):
        pass


    def process_line(self):
        for (pattern, handler) in self.commands:
            match = re.search(pattern, self.buffer)
            if match is not None:
                handler(match.groups())
                return True

        return False


    def handle(self):
        """
        Atiende eventos de la conexión hasta que termina.
        """
        while self.recv_line() and not self.quit:
            if not self.process_line():
                print("ERRRRRRROOROROROROROROROROR")


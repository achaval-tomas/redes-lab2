# encoding: utf-8
# Revisión 2019 (a Python 3 y base64): Pablo Ventura
# Copyright 2014 Carlos Bederián
# $Id: connection.py 455 2011-05-01 00:32:09Z carlos $

import socket
from constants import *
from base64 import b64encode

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

    def recv(self):
        while True:
            data = self.socket.recv(1024).decode('ascii')
            self.buffer += data

            if data[-2:] == EOL:
                break

    def quit(self):
        pass


    def handle(self):
        self.recv()
        
        print(f'Buffer length: {len(self.buffer)}')
        print(self.buffer)

#!/usr/bin/env python
# encoding: utf-8
# Revisión 2019 (a Python 3 y base64): Pablo Ventura
# Revisión 2014 Carlos Bederián
# Revisión 2011 Nicolás Wolovick
# Copyright 2008-2010 Natalia Bidart y Daniel Moisset
# $Id: server.py 656 2013-03-18 23:49:11Z bc $

import optparse
import socket
import sys
import threading
import select
from connection import Connection
from constants import DEFAULT_ADDR, DEFAULT_DIR, DEFAULT_PORT
from typing import Dict


class Server(object):
    """
    El servidor, que crea y atiende el socket en la dirección y puerto
    especificados donde se reciben nuevas conexiones de clientes.
    """

    def __init__(self, addr=DEFAULT_ADDR, port=DEFAULT_PORT,
                 directory=DEFAULT_DIR):
        print("Serving %s on %s:%s." % (directory, addr, port))

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = port
        self.addr = addr
        self.dir = directory

    def serve(self):
        """
        Loop principal del servidor. Se acepta una conexión a la vez
        y se espera a que concluya antes de seguir.
        """
        self.socket.bind((self.addr, self.port))
        self.socket.listen()

        poller = select.poll()
        poller.register(self.socket, select.POLLIN)

        connections: Dict[int, Connection] = {}

        while True:
            pollObj = poller.poll(5000)
            for sock_fd, event in pollObj:
                if not (event & select.POLLIN):
                    break
                if sock_fd == self.socket.fileno():
                    (new_sock, _) = self.socket.accept()
                    new_sock.setblocking(False)

                    poller.register(new_sock, select.POLLIN)
                    connections[new_sock.fileno()] = Connection(new_sock, self.dir)
                else:
                    client = connections[sock_fd]
                    should_close_client = client.on_read_available()
                    if should_close_client:
                        client.close()
                        poller.unregister(sock_fd)
                        connections.pop(sock_fd)


def main():
    """Parsea los argumentos y lanza el server"""

    parser = optparse.OptionParser()
    parser.add_option(
        "-p", "--port",
        help="Número de puerto TCP donde escuchar", default=DEFAULT_PORT)
    parser.add_option(
        "-a", "--address",
        help="Dirección donde escuchar", default=DEFAULT_ADDR)
    parser.add_option(
        "-d", "--datadir",
        help="Directorio compartido", default=DEFAULT_DIR)

    options, args = parser.parse_args()
    if len(args) > 0:
        parser.print_help()
        sys.exit(1)
    try:
        port = int(options.port)
    except ValueError:
        sys.stderr.write(
            "Numero de puerto invalido: %s\n" % repr(options.port))
        parser.print_help()
        sys.exit(1)

    server = Server(options.address, port, options.datadir)
    server.serve()


if __name__ == '__main__':
    main()

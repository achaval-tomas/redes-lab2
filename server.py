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
import select
from connection import Connection
from constants import DEFAULT_ADDR, DEFAULT_DIR, DEFAULT_PORT


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
        self.connections = {}
        self.poller = None

    def serve(self):
        """
        Loop principal del servidor. Se acepta una conexión a la vez
        y se espera a que concluya antes de seguir.
        """
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.addr, self.port))
        self.socket.listen()

        self.poller = select.poll()
        self.poller.register(self.socket, select.POLLIN)

        while True:
            events = self.poller.poll()
            for sock_fd, event in events:
                if not (event & (select.POLLIN | select.POLLOUT)):
                    continue

                if (event & select.POLLOUT):
                    self.handle_pollout(sock_fd)
                elif (event & select.POLLIN):
                    if sock_fd == self.socket.fileno():
                        # Server socket event
                        self.handle_new_connection()
                    else:
                        self.handle_pollin(sock_fd)

    def handle_new_connection(self):
        (new_sock, _) = self.socket.accept()
        new_sock.setblocking(False)

        self.poller.register(new_sock, select.POLLIN)
        self.connections[new_sock.fileno()] = Connection(new_sock, self.dir)

    def handle_pollin(self, sock_fd):
        client = self.connections[sock_fd]

        should_close_client = client.on_read_available()
        if should_close_client:
            self.poller.unregister(sock_fd)
            self.connections.pop(sock_fd)
            try:
                client.close()
            except OSError:
                print('Transport endpoint not connected, connection closed.')
        elif client.shoud_pollout():
            self.poller.modify(sock_fd, select.POLLIN | select.POLLOUT)
        else:
            self.poller.modify(sock_fd, select.POLLIN)

    def handle_pollout(self, sock_fd):
        client = self.connections[sock_fd]
        client.send()
        if not client.shoud_pollout():
            self.poller.modify(sock_fd, select.POLLIN)


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

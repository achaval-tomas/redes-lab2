# encoding: utf-8
# Revisión 2019 (a Python 3 y base64): Pablo Ventura
# Copyright 2014 Carlos Bederián
# $Id: connection.py 455 2011-05-01 00:32:09Z carlos $

from base64 import b64encode
from constants import EOL
import re
import socket as s
import os
from typing import Callable, Dict, List, Tuple, Union

BUFFER_SIZE = 1024


class Connection(object):
    """
    Conexión punto a punto entre el servidor y un cliente.
    Se encarga de satisfacer los pedidos del cliente hasta
    que termina la conexión.
    """

    socket: s.socket
    dir: str
    commands: Dict[str, Tuple[List[str], Callable[[List[str]], None]]]

    # the remaining data after calling recv_line()
    remaining_data: str

    quit: bool

    def __init__(self, socket: s.socket, directory: str):
        self.socket = socket
        self.dir = directory
        self.commands = {
            "get_file_listing": ([], self.get_file_listing_handler),
            "get_metadata": ([r"a-zA-Z0-9-_."], self.get_metadata_handler),
            "get_slice": ([r"{a-zA-Z0-9-_.}", r"\d", r"\d"], self.get_slice_handler),
            "quit": ([], self.quit_handler),
        }
        self.remaining_data = ""
        self.quit = False

    def send(self, msg: str):
        msg += EOL

        while msg:
            try:
                bytes_sent = self.socket.send(msg.encode('ascii'))
            except UnicodeEncodeError:
                print("ERROR: message contains invalid ascii.")
                return False

            msg = msg[bytes_sent:]

        return True

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
        self.send('0 OK')
        self.quit = True

    def get_file_listing_handler(self, args):
        try:
            files = os.listdir(self.dir)
        except FileNotFoundError:
            self.quit = True
            self.send('199 Directory not found in server')
            return

        self.send('0 OK')

        for filename in files:
            if not self.send(filename):
                self.quit = True
                self.send('199 Filename contains non-ascii characters')
                return

        self.send('')

    def get_metadata_handler(self, args):
        filename = args[0]
        fpath = self.get_filepath(filename)
        try:
            size = os.stat(fpath).st_size
        except FileNotFoundError:
            self.send('202 File not found')
            return

        self.send('0 OK')
        self.send(str(size))

    def get_slice_handler(self, args):
        filename = args[0]
        offset = int(args[1])
        size = int(args[2])

        try:
            fpath = self.get_filepath(filename)
        except FileNotFoundError:
            self.send('202 File not found')
            return

        # return error if user asked for a slice that is outside the file
        if offset+size > os.stat(fpath).st_size:
            self.send('203 Invalid file slice')
            return

        # open file with 'b' mode to read as bytes
        with open(fpath, 'rb') as file:
            file.seek(offset)

            data = file.read(size)

        # encode file to bas64 before sending
        data = b64encode(data).decode()

        self.send('0 OK')
        self.send(data)

    def process_line(self, line: str):
        cmd_name_match = re.match(r"([a-z_]+)( |\r\n)", line)
        if cmd_name_match is None:
            return 101, "Couldn't parse command name"

        cmd_name = cmd_name_match.group(1)

        cmd = self.commands.get(cmd_name, None)
        if cmd is None:
            return 200, f"Command '{cmd_name}' is not a valid command"

        (args_charsets, handler) = cmd

        args = []
        line = line[len(cmd_name):]
        for arg_charset in args_charsets:
            arg_match = re.match(f"^ ([{arg_charset}]+)", line)
            if arg_match is None:
                return 201, "Invalid or missing argument"
            arg = arg_match.group(1)
            args.append(arg)
            line = line[1 + len(arg):]

        if line != EOL:
            return 201, "EOL not found after last argument"

        # TODO: fix
        handler(args)

        return 0, "OK"

    def handle(self):
        """
        Atiende eventos de la conexión hasta que termina.
        """
        while not self.quit:
            line = self.recv_line()
            if line is None:
                break

            code, msg = self.process_line(line)

            assert code is not None and msg is not None

            if code != 0:
                self.send(f'{code} {msg}')

        print("Terminating connection with client.")
        self.socket.close()

    # Helper functions
    def get_filepath(self, filename):
        return self.dir + "/" + filename

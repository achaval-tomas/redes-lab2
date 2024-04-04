# encoding: utf-8
# Revisión 2019 (a Python 3 y base64): Pablo Ventura
# Copyright 2014 Carlos Bederián
# $Id: connection.py 455 2011-05-01 00:32:09Z carlos $

from base64 import b64encode
from constants import EOL, bEOL
import re
import socket as s
import os
import logging
from typing import Callable, Dict, List, Tuple, Union

BUFFER_SIZE = 1024
FILENAME_CHARSET = r"a-zA-Z0-9-_."

HandlerResult = Union[
    Tuple[int, str],
    Tuple[int, str, bytes],
    Tuple[int, str, List[bytes]],
]


class Connection(object):
    """
    Conexión punto a punto entre el servidor y un cliente.
    Se encarga de satisfacer los pedidos del cliente hasta
    que termina la conexión.
    """

    socket: s.socket
    dir: str
    commands: Dict[str, Tuple[List[str], Callable[[List[str]], HandlerResult]]]

    # the remaining data after calling recv_line()
    remaining_data: str

    quit: bool

    def __init__(self, socket: s.socket, directory: str):
        self.socket = socket
        self.dir = directory
        self.commands = {
            "get_file_listing": ([], self.get_file_listing_handler),
            "get_metadata": ([FILENAME_CHARSET], self.get_metadata_handler),
            "get_slice": ([FILENAME_CHARSET, r"\d", r"\d"],
                          self.get_slice_handler),
            "quit": ([], self.quit_handler),
        }
        self.remaining_data = ""
        self.quit = False

    def send(self, msg: bytes):
        while msg:
            bytes_sent = self.socket.send(msg)

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

    def quit_handler(self, _) -> HandlerResult:
        print("Client requested to quit.")
        self.quit = True
        return 0, "OK"

    def get_file_listing_handler(self, _) -> HandlerResult:
        # List filenames. Exceptions should be handled by top level handler
        filenames = os.listdir(self.dir)

        # Encode as many filenames as possible
        encoded = [try_encode(f, 'ascii') for f in filenames]
        # Filter out filenames which contain non-ascii characters
        filtered = [f for f in encoded if f is not None]

        return 0, "OK", filtered

    def get_metadata_handler(self, args) -> HandlerResult:
        filename = args[0]

        filepath = self.get_filepath(filename)
        try:
            size = os.stat(filepath).st_size
        except FileNotFoundError:
            return 202, "File not found"

        return 0, "OK", str(size).encode('ascii')

    def get_slice_handler(self, args) -> HandlerResult:
        filename = args[0]
        offset = int(args[1])
        size = int(args[2])

        filepath = self.get_filepath(filename)

        try:
            # open file with 'b' mode to read as bytes
            file = open(filepath, 'rb')
        except FileNotFoundError:
            return 202, "File not found"
        except IsADirectoryError:
            return 202, "The specified file is a directory"
        except OSError:
            return 199, "Error opening file"

        try:
            stat = os.stat(file.fileno())

            # return error if user asked for a slice that is outside the file
            if size + offset > stat.st_size:
                return 203, "Invalid file slice"

            file.seek(offset)

            data = file.read(size)
            # encode file to base64 before sending
            data = b64encode(data)

            return 0, "OK", data
        finally:
            file.close()

    def process_line(self, line: str) -> HandlerResult:
        cmd_name_match = re.match(r"([a-z_]+)( |\r\n)", line)
        if cmd_name_match is None:
            if '\n' in line[:len(line) - 2]:
                return 100, "Found \n outside eol"

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

        return handler(args)

    def handle(self):
        """
        Atiende eventos de la conexión hasta que termina.
        """
        try:
            self.handle_inner()
        except Exception as e:
            logging.exception(e)
            try:
                self.send(b"199 Internal server error\r\n")
            except Exception as e:
                logging.exception(e)
        finally:
            print("Terminating connection with client.")
            self.socket.close()

    def handle_inner(self):
        while not self.quit:
            line = self.recv_line()
            if line is None:
                break

            result = self.process_line(line)

            code = result[0]
            desc = result[1]
            body = result[2] if len(result) == 3 else None

            msg = f'{code} {desc}'.encode('ascii')
            msg += bEOL

            if type(body) is bytes:
                msg += body
                msg += bEOL
            elif type(body) is list:
                msg += bEOL.join(body)
                msg += bEOL
                msg += bEOL

            self.send(msg)

    # Helper functions
    def get_filepath(self, filename):
        return self.dir + "/" + filename


def try_encode(s: str, encoding: str) -> Union[bytes, None]:
    try:
        return s.encode(encoding)
    except UnicodeEncodeError:
        return None

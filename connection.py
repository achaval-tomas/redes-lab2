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

        peername = format_ip(self.socket.getpeername())
        print(f"Established connection with {peername}")

    def close(self):
        peername = format_ip(self.socket.getpeername())
        print(f"Established connection with {peername}")
        self.socket.close()

    def send(self, msg: bytes):
        while msg:
            bytes_sent = self.socket.send(msg)

            msg = msg[bytes_sent:]

    def send_message(
            self,
            code: int,
            desc: str,
            body: Union[None, bytes, List[bytes]] = None
    ):
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

    def recv_line(self) -> Union[str, None]:
        """
        Tries to read a line from the socket.
        An empty string means that a line could not be read
        but the connection should not be closed.
        None means that a line could not be read
        and the connection should be closed.
        """

        # Start the line with the remaining data of the previous recv()
        line = self.remaining_data
        self.remaining_data = ""

        while True:
            try:
                data = self.socket.recv(BUFFER_SIZE).decode('ascii')
            except BlockingIOError:
                return ''
            except UnicodeDecodeError:
                self.send_message(101, "Message contains non-ascii characters")
                return None

            # If no data was read then socket is closed
            if len(data) == 0:
                return None

            line += data

            eol_index = line.find(EOL)
            if eol_index == -1:
                # No EOL found, keep receiving
                continue

            next_line_index = eol_index + len(EOL)

            # Set leftovers as the remaining data
            self.remaining_data = line[next_line_index:]

            return line[0:next_line_index]

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
        except OSError as e:
            if os.name == 'posix' and e.errno == 36:
                return 202, "Filename too long"

            return 199, "Internal error"
        except ValueError as e:
            if os.name == 'nt':
                return 202, "Filename too long"
            raise e

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
        if '\n' in line[:-len(EOL)] is not None:
            return 100, "Found \\n outside EOL"

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

        return handler(args)

    def on_read_available(self) -> bool:
        """
        Atiende eventos de la conexión hasta que termina.
        Retorna True si la conexión debe cerrarse.
        """
        try:
            return self.on_read_available_inner()
        except Exception as e:
            logging.exception(e)
            try:
                self.send_message(199, "Internal server error")
            except Exception as e:
                logging.exception(e)
            return True

    def on_read_available_inner(self) -> bool:
        """
        Retorna True si la conexión debe cerrarse.
        """
        while True:
            if self.quit:
                return True

            line = self.recv_line()
            if line == '':
                return False
            if line is None:
                return True

            result = self.process_line(line)

            code = result[0]
            desc = result[1]
            body = result[2] if len(result) == 3 else None

            self.send_message(code, desc, body)

    # Helper functions
    def get_filepath(self, filename):
        return self.dir + "/" + filename


def try_encode(s: str, encoding: str) -> Union[bytes, None]:
    try:
        return s.encode(encoding)
    except UnicodeEncodeError:
        return None


def format_ip(ip_port: Tuple[str, int]) -> str:
    return f"{ip_port[0]}:{ip_port[1]}"

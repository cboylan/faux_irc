#!/usr/bin/python2

import socket
import select
import re
import os

PORT=42427
TIMEOUT=1.0
EOM="\r\n"

class IRCChannel(object):
    def __init__(self, name, directory):
        self.name = name
        self.directory = os.path.join(directory, self.name)

    def setup(self):
        if not os.path.exists(self.directory):
            os.mkdir(self.directory)
        self.infd = os.mkfifo(os.path.join(directory, "in"))
        self.infile = os.fdopen(self.infd)

        self.outfile = open(os.path.join(directory, "out"))
        self.outfd = outfile.fileno()

    def infileno(self):
        return self.infd

    def outfileno(self):
        return self.outfd

    def process_input(self):
        pass

    def process_output(self):
        pass

class ClientManager(object):
    def __init__(self, server, port, directory):
        self.channels = {}
        self.server = server
        self.port = port
        self.directory = directory

        self.sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(0)

        self.epoll = select.epoll()

    def setup(self):
        if not os.path.exists(self.directory):
            os.mkdir(self.directory)

        self.channels["#status"] = IRCChannel("#status", self.directory)
        self.channels["#status"].setup()
        self.channels[self.channels["#status"].infileno()] = self.channels["#status"]
        self.channels[self.channels["#status"].outfileno()] = self.channels["#status"]

        self.sock.connect((socket.gethostname(), self.port))
        self.epoll.register(serversocket.fileno(), select.EPOLLIN)
        self.epoll.register(self.channels["#status"].infileno(), select.EPOLLIN)

    def process_msgs(self, msgs):
        pass

    def handle_client_input(self, client_input):
        pass

    def loop(self):
        inbuf = ""
        outbuf = ""

        while True:
            events = self.epoll.poll(TIMEOUT)
            for fileno, event in events:
                if fileno == self.sock.fileno() and event & select.EPOLLHUP:
                    self.epoll.unregister(fileno)
                    self.sock.close()
                    return
                if fileno == self.sock.fileno() and event & select.EPOLLIN:
                    # Read input pass to proper channel buffer.
                    inbuf += self.sock.recv(4096)
                    msgs = inbuf.rsplit(EOM, 1)
                    if len(msgs) > 1:
                        self.process_msgs(msgs[0])
                        ibuf = msgs[1]
                else if event & select.EPOLLIN:
                    # Read input pass to socket
                    tempbuf = channels[fileno].process_input()
                    if tempbuf is not None:
                        self.handle_client_input(tempbuf)
                        outbuf += tempbuf
                        self.epoll.modify(fileno, select.EPOLLOUT | select.EPOLLIN)
                if fileno == self.sock.fileno() and event & select.EPOLLOUT:
                    # Write out socket buffer
                    bytes_written = self.sock.send(outbuf)
                    outbuf = outbuf[bytes_written:]
                    if len(outbuf) == 0:
                        self.epoll.modify(fileno, select.EPOLLIN)
                else if event & select.EPOLLOUT:
                    # Write out to channel file.
                    if channels[fileno].process_output():
                        self.epoll.modify(fileno, select.EPOLLIN)

if __name__ == "__main__":
    server = "localhost"
    directory = os.path.join(os.getcwd(), "faux_irc_channels")

    manager = ClientManager(server, PORT, directory)
    manager.setup()
    manager.loop()

#!/usr/bin/python2

import socket
import select
import re
import os
import sys
from optparse import OptionParser

TIMEOUT=1.0
EOM="\r\n"

class IRCChannel(object):
    def __init__(self, name, directory):
        self.name = name
        self.directory = os.path.join(directory, self.name)
        self.inbuf = ""

    def setup(self):
        if not os.path.exists(self.directory):
            os.mkdir(self.directory)

        if not os.path.exists(os.path.join(self.directory, "in")):
            os.mkfifo(os.path.join(self.directory, "in"))
        self.infd = os.open(os.path.join(self.directory, "in"), os.O_NONBLOCK | os.O_RDONLY)

        self.outfile = open(os.path.join(self.directory, "out"), "w")

    def infileno(self):
        return self.infd

    def process_input(self):
        def translate_input(input_str):
            if input_str[0:5] == "/join":
                return re.sub(r"/join", "JOIN", input_str)
            elif input_str[0:5] == "/part":
                return re.sub(r"/part", "PART", input_str)
            elif input_str[0:5] == "/nick":
                return re.sub(r"/nick", "NICK", input_str)
            elif input_str[0:5] == "/list":
                return re.sub(r"/list", "LIST", input_str)
            else:
                return "PRVMSG " + self.name + " " + input_str

        self.inbuf += str(os.read(self.infd, 4096))
        msgs = self.inbuf.rsplit("\n", 1)
        if len(msgs) > 1:
            self.inbuf = msgs[1]
            return map(translate_input, msgs[0].split("\n"))
        return None

    def process_output(self, output):
        self.outfile.write(output)
        self.outfile.flush()

    def close(self):
        os.close(self.infd)
        self.outfile.close()
        

class ClientManager(object):
    def __init__(self, server, port, directory):
        self.channels = {}
        self.server = server
        self.port = port
        self.directory = directory

        self.sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)

        self.epoll = select.epoll()

    def setup(self):
        if not os.path.exists(self.directory):
            os.mkdir(self.directory)

        self.channels["#status"] = IRCChannel("#status", self.directory)
        self.channels["#status"].setup()
        self.channels[self.channels["#status"].infileno()] = self.channels["#status"]

        self.sock.connect((socket.gethostname(), self.port))
        self.sock.setblocking(0)
        self.epoll.register(self.sock.fileno(), select.EPOLLIN)
        self.epoll.register(self.channels["#status"].infileno(), select.EPOLLIN)

    def close(self):
        for key, channel in self.channels.items():
            if type(key) is str:
                self.epoll.unregister(channel.infileno())
                channel.close()
        self.epoll.unregister(self.sock.fileno())
        self.epoll.close()
        self.sock.close()

    def process_msgs(self, msgs):
        err_regex = re.compile("^ERROR (\d)$")
        prvmsg_regex = re.compile("^PRVMSG (#\w{0,199}) (.*)$")

        for msg in msgs.split(EOM):
            err_match = err_regex.match(msg)
            prvmsg_match = prvmsg_regex.match(msg)
            print msg
            if err_match and err_match.group(1) == "1":
                print "Error 1"
                self.channels["#status"].process_output("Invalid Nick\n")
            elif err_match and err_match.group(1) == "2":
                print "Error 2"
                self.channels["#status"].process_output("Invalid Join\n")
            elif prvmsg_match:
                print "printing to output channel"
                self.channels[prvmsg_match.group(1)].process_output(prvmsg_match.group(2) + "\n")

    def handle_client_input(self, fileno, msgs):
        join_regex = re.compile("^JOIN (#\w{0,199})$")
        part_regex = re.compile("^PART$")
        for msg in msgs:
            join_match = join_regex.match(msg)
            part_match = part_regex.match(msg)
            if join_match:
                name = join_match.group(1)
                self.channels[name] = IRCChannel(name, self.directory)
                self.channels[name].setup()
                self.channels[self.channels[name].infileno()] = self.channels[name]
                self.epoll.register(self.channels[name].infileno(), select.EPOLLIN)
            elif part_match:
                name = self.channels[fileno].name
                self.epoll.unregister(self.channels[name].infileno())
                self.channels[name].close()
                del self.channels[self.channels[name].infileno()]
                del self.channels[name]

    def loop(self):
        inbuf = ""
        outbuf = ""

        try:
            while True:
                events = self.epoll.poll(TIMEOUT)
                for fileno, event in events:
                    if fileno == self.sock.fileno() and event & select.EPOLLHUP:
                        sys.exit()
                    if fileno == self.sock.fileno() and event & select.EPOLLIN:
                        # Read input pass to proper channel buffer.
                        inbuf += self.sock.recv(4096)
                        msgs = inbuf.rsplit(EOM, 1)
                        if len(msgs) > 1:
                            self.process_msgs(msgs[0])
                            inbuf = msgs[1]
                    elif event & select.EPOLLIN:
                        # Read input pass to socket
                        msgs = self.channels[fileno].process_input()
                        if msgs is not None:
                            self.handle_client_input(fileno, msgs)
                            outbuf += EOM.join(msgs) + EOM
                            self.epoll.modify(self.sock.fileno(), select.EPOLLOUT | select.EPOLLIN)
                    if fileno == self.sock.fileno() and event & select.EPOLLOUT:
                        # Write out socket buffer
                        bytes_written = self.sock.send(outbuf)
                        outbuf = outbuf[bytes_written:]
                        if len(outbuf) == 0:
                            self.epoll.modify(self.sock.fileno(), select.EPOLLIN)

        finally:
            self.close()
            return

if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-s", "--server",
                      action="store", type="string", dest="server", default="localhost")
    parser.add_option("-p", "--port",
                      action="store", type="int", dest="port", default=42424)
    parser.add_option("-d", "--dir",
                      action="store", type="string", dest="directory", default=os.path.join(os.getcwd(), "faux_irc_channels"))
    (options, args) = parser.parse_args()

    manager = ClientManager(options.server, options.port, options.directory)
    manager.setup()
    manager.loop()

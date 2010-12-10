#!/usr/bin/python2
#
# Clark Boylan
# CS 494
# Final Project
# 12/10/2010
# faux_irc_client.py
# 
# (Mostly) Non blocking event driven Faux IRC client inspired by Suckless's ii
# IRC client. Each channel creates and input FIFO and an output file through
# which messages are entered and printed.
#
# Requires epoll.

import socket
import re
import os
import sys
from optparse import OptionParser
import select
if not "EPOLLRDHUP" in dir(select):
        select.EPOLLRDHUP = 0x2000

TIMEOUT=1.0
EOM="\r\n"

#TODO: Handle invalid joins and parts properly.

class IRCChannel(object):
    """Class used to manage the client side of an IRC channel."""

    def __init__(self, name, directory):
        self.name = name
        self.directory = os.path.join(directory, self.name)
        self.inbuf = ""

    def setup(self):
        """Create an input FIFO and an output file for each channel."""
        if not os.path.exists(self.directory):
            os.mkdir(self.directory)

        if not os.path.exists(os.path.join(self.directory, "in")):
            os.mkfifo(os.path.join(self.directory, "in"))
        self.infd = os.open(os.path.join(self.directory, "in"),
                os.O_NONBLOCK | os.O_RDONLY)

        self.outfile = open(os.path.join(self.directory, "out"), "w")

    def infileno(self):
        return self.infd

    def process_input(self):
        """Read from the input FIFO and translate commands."""
        def translate_input(input_str):
            """Translate user inputs into protocol compliant messages."""
            if input_str[0:5] == "/join":
                return re.sub(r"/join", "JOIN", input_str)
            elif input_str[0:5] == "/part":
                return re.sub(r"/part", "PART", input_str) + " " + self.name
            elif input_str[0:5] == "/nick":
                return re.sub(r"/nick", "NICK", input_str)
            elif input_str[0:5] == "/list":
                return re.sub(r"/list", "LIST", input_str)
            else:
                return "PRVMSG " + self.name + " " + input_str

        self.inbuf += str(os.read(self.infd, 4096))
        #Ignore any incomplete messages at the end of the read.
        msgs = self.inbuf.rsplit("\n", 1)
        if len(msgs) > 1:
            self.inbuf = msgs[1]
            #Return the translated messages.
            return map(translate_input, msgs[0].split("\n"))
        return None

    def process_output(self, output):
        """Write outputs to the output file."""
        #TODO: Make this nonblocking.
        self.outfile.write(output)
        self.outfile.flush()

    def close(self):
        """Close the file and FIFO associated with this channel."""
        os.close(self.infd)
        self.outfile.close()
        

class ClientManager(object):
    """Class used to manage an IRC connection and its associated channels."""

    def __init__(self, server, port, directory):
        self.channels = {}
        self.server = server
        self.port = port
        self.directory = directory

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.epoll = select.epoll()

    def setup(self):
        """Setup the control directory, status channel, and communication
        socket."""
        if not os.path.exists(self.directory):
            os.mkdir(self.directory)

        self.channels["#status"] = IRCChannel("#status", self.directory)
        status_channel = self.channels["#status"]
        status_channel.setup()
        self.channels[status_channel.infileno()] = status_channel

        self.sock.connect((socket.gethostname(), self.port))
        self.sock.setblocking(0)
        self.epoll.register(self.sock.fileno(),
                select.EPOLLIN | select.EPOLLRDHUP)
        self.epoll.register(self.channels["#status"].infileno(), select.EPOLLIN)

    def close(self):
        """Close all channels and the communication socket."""
        for key, channel in self.channels.items():
            if type(key) is str:
                self.epoll.unregister(channel.infileno())
                channel.close()

        self.epoll.unregister(self.sock.fileno())
        self.epoll.close()
        self.sock.close()

    def process_msgs(self, msgs):
        """Deliver messages from the server to the appropriate channel."""
        err_regex = re.compile("^ERROR (\d)$")
        prvmsg_regex = re.compile("^PRVMSG (#\w{0,199}) (.*)$")

        for msg in msgs.split(EOM):
            err_match = err_regex.match(msg)
            prvmsg_match = prvmsg_regex.match(msg)

            if err_match and err_match.group(1) == "1":
                self.channels["#status"].process_output("Invalid Nick\n")
            elif err_match and err_match.group(1) == "2":
                self.channels["#status"].process_output("Invalid Channel\n")
            elif prvmsg_match:
                self.channels[prvmsg_match.group(1)].process_output(
                        prvmsg_match.group(2) + "\n")

    def handle_client_input(self, fileno, msgs):
        """Perform side effects that result from user input."""
        join_regex = re.compile("^JOIN (#\w{0,199})$")
        part_regex = re.compile("^PART .*$")

        for msg in msgs:
            join_match = join_regex.match(msg)
            part_match = part_regex.match(msg)

            if join_match:
                #Create a new channel as we have just joined to one.
                name = join_match.group(1)
                self.channels[name] = IRCChannel(name, self.directory)
                new_channel = self.channels[name]
                new_channel.setup()
                self.channels[new_channel.infileno()] = new_channel
                self.epoll.register(new_channel.infileno(), select.EPOLLIN)
            elif part_match:
                #Remove the channel we just parted from.
                name = self.channels[fileno].name
                self.epoll.unregister(self.channels[name].infileno())
                self.channels[name].close()
                del self.channels[self.channels[name].infileno()]
                del self.channels[name]

    def loop(self):
        """Main event loop. Loop over events and process them."""
        inbuf = ""
        outbuf = ""

        try:
            while True:
                events = self.epoll.poll(TIMEOUT)
                for fileno, event in events:
                    if fileno == self.sock.fileno() and \
                            event & select.EPOLLRDHUP:
                        #Connection closed so we exit.
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
                            self.epoll.modify(self.sock.fileno(),
                                    select.EPOLLOUT | select.EPOLLIN |
                                    select.EPOLLRDHUP)
                    if fileno == self.sock.fileno() and event & select.EPOLLOUT:
                        # Write out socket buffer
                        bytes_written = self.sock.send(outbuf)
                        outbuf = outbuf[bytes_written:]
                        if len(outbuf) == 0:
                            self.epoll.modify(self.sock.fileno(),
                                    select.EPOLLIN | select.EPOLLRDHUP)

        finally:
            #Cleanup in the event that the client exits.
            self.close()
            return

if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-s", "--server", action="store", type="string",
            dest="server", default="localhost")
    parser.add_option("-p", "--port", action="store", type="int", dest="port",
            default=42424)
    parser.add_option("-d", "--dir", action="store", type="string",
            dest="directory", default=os.path.join(os.getcwd(),
            "faux_irc_channels"))
    (options, args) = parser.parse_args()

    manager = ClientManager(options.server, options.port, options.directory)
    manager.setup()
    manager.loop()

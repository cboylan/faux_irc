#!/usr/bin/python2

import socket
import re
from optparse import OptionParser
import select
if not "EPOLLRDHUP" in dir(select):
        select.EPOLLRDHUP = 0x2000

TIMEOUT=1.0
EOM="\r\n"

#TODO: Add NickManager and ChannelManager.

class IRCConnection(object):
    """Class used to manage an IRC connection and its associated socket."""
    def __init__(self, sock, epoll, channels, nicks):
        self.sock = sock
        self._fileno = sock.fileno()
        self.epoll = epoll
        self.channels = channels
        self.joined_channels = []
        self.nicks = nicks
        self.nick = None
        self.input_buf = ""
        self.output_buf = ""

        self.handlers = {
            "NICK": IRCConnection.handle_nick,
            "JOIN": IRCConnection.handle_join,
            "PART": IRCConnection.handle_part,
            "LIST": IRCConnection.handle_list,
            "PRVMSG": IRCConnection.handle_prvmsg,
        }

    def fileno(self):
        return self._fileno

    def write(self, message):
        """Update the connections buffer and ask the poll notify us when we can
        write to the socket"""
        self.output_buf += message
        self.epoll.modify(self._fileno,
                select.EPOLLOUT | select.EPOLLIN | select.EPOLLRDHUP)

    def process_input(self):
        """Read from socket then process the data that is read."""
        self.input_buf += self.sock.recv(4096)

        #Separate complete messages from the possibly incomplete message at the
        #end.
        msgs = self.input_buf.rsplit(EOM, 1)
        #If at least one whole message is found process it.
        if len(msgs) > 1:
            for msg in msgs[0].split(EOM):
                print(msg)

                if self.handlers.get(msg.split(" ", 1)[0],
                        IRCConnection.default_handler)(self, msg):
                    self.epoll.modify(self._fileno,
                            select.EPOLLOUT | select.EPOLLIN | select.EPOLLRDHUP)
            self.input_buf = msgs[1]

    def process_output(self):
        """Write out this connections buffer to its socket."""
        bytes_written = self.sock.send(self.output_buf)
        self.output_buf = self.output_buf[bytes_written:]
        if len(self.output_buf) == 0:
            self.epoll.modify(self._fileno, select.EPOLLIN | select.EPOLLRDHUP)

    def close(self):
        """Close a connection. Perform cleanup."""
        self.sock.close()
        if self.nick is not None:
            self.nicks.remove(self.nick)
        for channel in self.joined_channels:
            self.channels[channel].remove(self)

    #The following methods are message handlers. Each should return true if
    #handling the message results in an output buffer with content. False
    #otherwise.

    def default_handler(self, msg):
        return False

    def handle_nick(self, msg):
        """Handle incoming NICK messages."""
        regex = re.compile("^NICK (\w{1,9})$")
        match = regex.match(msg)
        if match and match.group(1) not in self.nicks:
            if self.nick is not None:
                self.nicks.remove(self.nick)
            self.nick = match.group(1)
            self.nicks.append(self.nick)
            return False
        else:
            self.output_buf += "ERROR 1" + EOM
            return True

    def handle_join(self, msg):
        """Handle incoming JOIN messages."""
        if self.nick is not None:
            regex = re.compile("^JOIN (#\w{0,199})$")
            match = regex.match(msg)
            if match and match.group(1) not in self.joined_channels:
                l = self.channels.get(match.group(1), [])
                l.append(self)
                self.channels[match.group(1)] = l
                self.joined_channels.append(match.group(1))
                return False
            else:
                self.output_buf += "ERROR 2" + EOM
                return True
        else:
            return False

    def handle_part(self, msg):
        """Handle incoming PART messages."""
        if self.nick is not None:
            regex = re.compile("^PART (#\w{0,199})$")
            match = regex.match(msg)

            #If the nick is joined to the channel then remove them. Otherwise
            #send an error to the client.
            if match and match.group(1) in self.joined_channels:
                try:
                    self.channels.get(match.group(1), []).remove(self)
                    self.joined_channels.remove(match.group(1))
                    return False
                except ValueError:
                    self.output_buf += "ERROR 2" + EOM
                    return True
            else:
                self.output_buf += "ERROR 2" + EOM
                return True
        else:
            return False

    def handle_list(self, msg):
        """Handle incoming LIST messages."""
        if self.nick is not None:
            regex = re.compile("^LIST$")
            match = regex.match(msg)
            if match:
                for channel in self.channels.iterkeys():
                    self.output_buf += "PRVMSG #status {c}".format(c=channel) + EOM
                return True
        return False

    def handle_prvmsg(self, msg):
        """Handle incoming PRVMSG messages."""
        if self.nick is not None:
            regex = re.compile("^PRVMSG (#\w{0,199}) (.*)$")
            match = regex.match(msg)

            if match:
                #Mulitplex the message to all clients joined to the channel.
                channel = self.channels.get(match.group(1), None)
                if channel is not None and match.group(1) in self.joined_channels:
                    for conn in channel:
                        conn.write("PRVMSG {c} {n}: {m}".format(
                                c=match.group(1), n = self.nick, m=match.group(2)) + 
                                EOM)
                else:
                    self.output_buf += "ERROR 2" + EOM
                    return True
        return False

def process_loop(port):
    """Main function and event loop processor for the server."""
    channels = {}
    connections = {}
    nicks = []

    #Set up the listen socket.
    serversocket = socket.socket(
        socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind((socket.gethostname(), port))
    serversocket.listen(5)
    serversocket.setblocking(0)

    epoll = select.epoll()
    epoll.register(serversocket.fileno(), select.EPOLLIN)

    try:
        while True:
            events = epoll.poll(TIMEOUT)
            for fileno, event in events:
                #If a new connection comes handle it.
                if fileno == serversocket.fileno():
                    connection, address = serversocket.accept()
                    connection.setblocking(0)
                    irc_conn = IRCConnection(connection, epoll, channels, nicks)
                    epoll.register(irc_conn.fileno(),
                            select.EPOLLIN | select.EPOLLRDHUP)
                    connections[irc_conn.fileno()] = irc_conn
                    continue
                #If a connection dies handle it.
                if event & select.EPOLLRDHUP:
                    print "EPOLL killing connection"
                    epoll.unregister(fileno)
                    connections[fileno].close()
                    del connections[fileno]
                    continue
                #If a connection has input process it.
                if event & select.EPOLLIN:
                    connections[fileno].process_input()
                #If a connection has output process it.
                if event & select.EPOLLOUT:
                    connections[fileno].process_output()
    finally:
        #Cleanup when the server dies.
        for key, connection in connections.items():
            epoll.unregister(connection.fileno())
            connection.close()
        epoll.unregister(serversocket.fileno())
        epoll.close()
        serversocket.close()
        return

if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-p", "--port", action="store", type="int", dest="port",
            default=42424)
    (options, args) = parser.parse_args()

    process_loop(options.port)

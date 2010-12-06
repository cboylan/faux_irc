#!/usr/bin/python2

import socket
import select
import re

PORT=42427
TIMEOUT=1.0
EOM="\r\n"

#TODO: Add NickManager, ChannelManager, and OptParse CLI option support

class IRCConnection(object):
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
        self.output_buf += message
        self.epoll.modify(self._fileno, select.EPOLLOUT | select.EPOLLIN)

    def process_input(self):
        self.input_buf += self.sock.recv(4096)
        msgs = self.input_buf.rsplit(EOM, 1)
        if len(msgs) > 1:
            for msg in msgs[0].split(EOM):
                if self.handlers.get(msg.split(" ", 1)[0], IRCConnection.default_handler)(self, msg):
                    self.epoll.modify(self._fileno, select.EPOLLOUT | select.EPOLLIN)
            self.input_buf = msgs[1]

    def process_output(self):
        bytes_written = self.sock.send(self.output_buf)
        self.output_buf = self.output_buf[bytes_written:]
        if len(self.output_buf) == 0:
            self.epoll.modify(self._fileno, select.EPOLLIN)

    def default_handler(self, msg):
        return False

    def handle_nick(self, msg):
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
        if self.nick is not None:
            regex = re.compile("^PART (#\w{0,199})$")
            match = regex.match(msg)
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
        if self.nick is not None:
            regex = re.compile("^LIST$")
            match = regex.match(msg)
            if match:
                for channel in self.channels.iterkeys():
                    self.output_buf += "PRVMSG #status {c}".format(c=channel) + EOM
                return True
        return False

    def handle_prvmsg(self, msg):
        if self.nick is not None:
            regex = re.compile("^PRVMSG (#\w{0,199}) ([\s\w]*)$")
            match = regex.match(msg)
            if match:
                channel = self.channels.get(match.group(1), None)
                if channel is not None and match.group(1) in self.joined_channels:
                    for conn in channel:
                        conn.write("PRVMSG {c} {m}".format(c=match.group(1), m=match.group(2)) + EOM)
                else:
                    self.output_buf += "ERROR 2" + EOM
                    return True
        return False

    def close(self):
        self.sock.close()
        if self.nick is not None:
            self.nicks.remove(self.nick)
        for channel in self.joined_channels:
            self.channels[channel].remove(self)

def process_loop():
    channels = {}
    connections = {}
    nicks = []

    serversocket = socket.socket(
        socket.AF_INET, socket.SOCK_STREAM)
    serversocket.bind((socket.gethostname(), PORT))
    serversocket.listen(5)
    serversocket.setblocking(0)

    epoll = select.epoll()
    epoll.register(serversocket.fileno(), select.EPOLLIN)

    try:
        while True:
            events = epoll.poll(TIMEOUT)
            for fileno, event in events:
                if fileno == serversocket.fileno():
                    connection, address = serversocket.accept()
                    connection.setblocking(0)
                    irc_conn = IRCConnection(connection, epoll, channels, nicks)
                    epoll.register(irc_conn.fileno(), select.EPOLLIN)
                    connections[irc_conn.fileno()] = irc_conn
                    continue
                if event & select.EPOLLHUP:
                    epoll.unregister(fileno)
                    connections[fileno].close()
                    del connections[fileno]
                    continue
                if event & select.EPOLLIN:
                    connections[fileno].process_input()
                if event & select.EPOLLOUT:
                    connections[fileno].process_output()
    finally:
        epoll.unregister(serversocket.fileno())
        epoll.close()
        serversocket.close()
        return

if __name__ == "__main__":
    process_loop()

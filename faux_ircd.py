#!/usr/bin/python2

import socket
import select

PORT=42425
TIMEOUT=1.0
EOM="\r\n"

class IRCConnection(object):
    def __init__(self, sock, epoll, channels):
        self._sock = sock
        self._fileno = sock.fileno()
        self._epoll = epoll
        self._channels = channels
        self.input_buf = ""
        self.output_buf = ""

        self.handlers = {
            "NICK": IRCConnection.handle_nick,
            "JOIN": IRCConnection.handle_join,
            "PRVMSG": IRCConnection.handle_prvmsg,
        }

    def fileno(self):
        return self._fileno

    def process_input(self):
        self.input_buf += self._sock.recv(4096)
        msgs = self.input_buf.rsplit(EOM, 1)
        if len(msgs) > 1:
            for msg in msgs[0].split(EOM):
                self.output_buf += msg
                if self.handlers(msg.split(" ", 1)[0], IRCConnection.default_handler)(self, msg):
                    self._epoll.modify(self._fileno, select.EPOLLOUT | select.EPOLLIN)
            self.input_buf = msgs[1]

    def process_output(self):
        bytes_written = self._sock.send(self.output_buf)
        self.output_buf = self.output_buf[bytes_written:]
        if len(self.output_buf) == 0:
            self._epoll.modify(self._fileno, select.EPOLLIN)

    def default_handler(self, msg):
        return False

    def handle_nick(self, msg):
        args = msgs.split(" ")
        if len(args) == 2:
            self.nick = args[1]
            return False
        else:
            return True

    def handle_join(self, msg):
        pass

    def handle_prvmsg(self, msg):
        pass

def process_loop():
    channels = {}
    connections = {}

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
                    irc_conn = IRCConnection(connection, epoll, channels)
                    epoll.register(irc_conn.fileno(), select.EPOLLIN)
                    connections[irc_conn.fileno()] = irc_conn
                    continue
                if event & select.EPOLLHUP:
                    poll.unregister(fileno)
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

if __name__ == "__main__":
    process_loop()

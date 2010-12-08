#!/usr/bin/python2

import socket
import select
import re

PORT=42427
TIMEOUT=1.0
EOM="\r\n"

class ClientManager(object):
    def __init__(self):
        self.channels = {}

        self.sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(0)

        self.epoll = select.epoll()


    def loop(self):
        inbuf = ""
        outbuf = ""

        self.sock.connect((socket.gethostname(), PORT))
        self.epoll.register(serversocket.fileno(), select.EPOLLIN)

        while True:
            events = self.epoll.poll(TIMEOUT)
            for fileno, event in events:
                if fileno == self.sock.fileno() and event & select.EPOLLHUP:
                    self.epoll.unregister(fileno)
                    self.sock.close()
                    continue
                if fileno == self.sock.fileno() and event & select.EPOLLIN:
                    # Read input pass to proper channel buffer.
                    inbuf += self.sock.recv(4096)
                    msgs = inbuf.rsplit(EOM, 1)
                    if len(msgs) > 1:
                        self.process_msgs(msgs[0])
                        ibuf = msgs[1]
                else if event & select.EPOLLIN:
                    # Read input pass to socket
                    tempbuf += channels[fileno].process_input()
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
                    channels[fileno].process_output()
                    pass

if __name__ == "__main__":
    manager = ClientManager()
    manager.loop()

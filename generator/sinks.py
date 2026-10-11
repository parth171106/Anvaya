import socket
import time


class UdpSink:
    """One datagram per line, all from one socket. Retries a failed send once after 50 ms (APP_FLOW.md FL-03)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5514):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.errors = 0

    def send(self, text: str) -> None:
        data = text.encode("utf-8")
        try:
            self.sock.sendto(data, self.addr)
        except OSError:
            time.sleep(0.05)
            try:
                self.sock.sendto(data, self.addr)
            except OSError:
                self.errors += 1

    def close(self) -> None:
        self.sock.close()

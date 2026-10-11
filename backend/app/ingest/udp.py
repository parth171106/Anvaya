import asyncio
import logging

log = logging.getLogger("anvaya.ingest")


class UdpSyslogProtocol(asyncio.DatagramProtocol):
    """One event per datagram (FL-01 step 1)."""

    def __init__(self, accept):
        self.accept = accept  # (data, transport, peer_ip) -> RawRecord

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            self.accept(data, "udp", addr[0])
        except Exception:
            log.exception("udp ingest failed")


async def start_udp(accept, port: int, host: str = "0.0.0.0"):
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(lambda: UdpSyslogProtocol(accept), local_addr=(host, port))
    return transport

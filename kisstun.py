#!/usr/bin/env python3
"""Bridge IP packets between a TUN interface and a KISS TNC.

Connects to Dire Wolf's TCP KISS server at 127.0.0.1:8001, starting Dire Wolf
automatically if needed. On Windows, place Wintun's wintun.dll beside this
script or supply --wintun-dll.

Run with suitable privileges. Use --address to assign an IPv4 address and
prefix to the interface at startup.
"""

from __future__ import annotations

import argparse
import ctypes
import ipaddress
import os
import platform
import select
import signal
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from ctypes import wintypes

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD
KISS_DATA = 0x00


def kiss_encode(packet: bytes, port: int = 0, command: int = KISS_DATA) -> bytes:
    if not 0 <= port <= 15 or not 0 <= command <= 15:
        raise ValueError("KISS port and command must be in 0..15")
    body = bytearray((port << 4 | command,))
    for b in packet:
        if b == FEND:
            body.extend((FESC, TFEND))
        elif b == FESC:
            body.extend((FESC, TFESC))
        else:
            body.append(b)
    return bytes((FEND,)) + body + bytes((FEND,))


class KissDecoder:
    """Incremental KISS frame decoder; yields (port, command, payload)."""

    def __init__(self, max_frame: int = 65540):
        self.max_frame = max_frame
        self.frame = bytearray()
        self.in_frame = False
        self.escaped = False
        self.dropping = False

    def feed(self, data: bytes):
        for b in data:
            if b == FEND:
                if self.in_frame and self.frame and not self.dropping:
                    control, payload = self.frame[0], bytes(self.frame[1:])
                    yield (control >> 4, control & 0x0F, payload)
                self.frame.clear()
                self.in_frame = True
                self.escaped = self.dropping = False
                continue
            if not self.in_frame or self.dropping:
                continue
            if self.escaped:
                if b == TFEND:
                    self.frame.append(FEND)
                elif b == TFESC:
                    self.frame.append(FESC)
                else:
                    self.dropping = True
                self.escaped = False
            elif b == FESC:
                self.escaped = True
            else:
                self.frame.append(b)
            if len(self.frame) > self.max_frame:
                self.dropping = True


class LinuxTun:
    def __init__(self, name: str):
        import fcntl

        self.fd = os.open("/dev/net/tun", os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
        # struct ifreq is 40 bytes on Linux's supported 64-bit ABIs; the
        # interface name occupies IFNAMSIZ bytes, followed by a short flags.
        ifreq = struct.pack("16sH", name.encode()[:15], 0x0001 | 0x1000)  # IFF_TUN | IFF_NO_PI
        ifreq += bytes(40 - len(ifreq))
        try:
            result = fcntl.ioctl(self.fd, 0x400454CA, ifreq)  # TUNSETIFF
        except Exception:
            os.close(self.fd)
            raise
        self.name = result[:16].split(b"\0", 1)[0].decode()

    def fileno(self):
        return self.fd

    def read(self, size=65535):
        return os.read(self.fd, size)

    def write(self, packet):
        return os.write(self.fd, packet)

    def close(self):
        os.close(self.fd)


class MacTun:
    """Native macOS utun socket. utun prepends a 4-byte address-family tag."""

    def __init__(self, unit: int | None = None):
        import fcntl

        AF_SYSTEM, SYSPROTO_CONTROL, AF_SYS_CONTROL = 32, 2, 2
        self.sock = socket.socket(AF_SYSTEM, socket.SOCK_DGRAM, SYSPROTO_CONTROL)
        # ctl_info { uint32_t id; char name[96]; }
        ctl_info = bytearray(100)
        ctl_info[4:4 + len(b"com.apple.net.utun_control")] = b"com.apple.net.utun_control"
        try:
            fcntl.ioctl(self.sock.fileno(), 0xC0644E03, ctl_info, True)  # CTLIOCGINFO
            ctl_id = struct.unpack_from("=I", ctl_info)[0]
            # utun is activated with connect(), not bind(). Unit 0 asks macOS
            # to allocate a free interface; utunN is requested with sc_unit N+1.
            self.sock.connect((ctl_id, 0 if unit is None else unit + 1))
            self.name = self.sock.getsockopt(SYSPROTO_CONTROL, 2, 64).split(b"\0", 1)[0].decode()
        except Exception:
            self.sock.close()
            raise

    def fileno(self):
        return self.sock.fileno()

    def read(self, size=65539):
        data = self.sock.recv(size)
        if len(data) < 4:
            return b""
        return data[4:]

    def write(self, packet):
        if not packet:
            return 0
        version = packet[0] >> 4
        if version == 4:
            family = socket.AF_INET
        elif version == 6:
            family = socket.AF_INET6
        else:
            raise ValueError("TUN packet is not IPv4 or IPv6")
        return self.sock.send(struct.pack("=I", family) + packet) - 4

    def close(self):
        self.sock.close()


class WindowsWintun:
    """Small ctypes wrapper around the official Wintun userspace API."""

    def __init__(self, name: str, dll_path: str | None):
        if os.name != "nt":
            raise OSError("Wintun is only available on Windows")
        path = dll_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "wintun.dll")
        self.dll = ctypes.WinDLL(path, use_last_error=True)
        d = self.dll
        d.WintunCreateAdapter.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
        d.WintunCreateAdapter.restype = ctypes.c_void_p
        d.WintunOpenAdapter.argtypes = [wintypes.LPCWSTR]
        d.WintunOpenAdapter.restype = ctypes.c_void_p
        d.WintunCloseAdapter.argtypes = [ctypes.c_void_p]
        d.WintunStartSession.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        d.WintunStartSession.restype = ctypes.c_void_p
        d.WintunEndSession.argtypes = [ctypes.c_void_p]
        d.WintunReceivePacket.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        d.WintunReceivePacket.restype = ctypes.POINTER(ctypes.c_ubyte)
        d.WintunReleaseReceivePacket.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte)]
        d.WintunAllocateSendPacket.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        d.WintunAllocateSendPacket.restype = ctypes.POINTER(ctypes.c_ubyte)
        d.WintunSendPacket.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte)]
        self.adapter = d.WintunOpenAdapter(name)
        if not self.adapter:
            self.adapter = d.WintunCreateAdapter(name, "KISS TUN", None)
        if not self.adapter:
            raise ctypes.WinError(ctypes.get_last_error())
        self.session = d.WintunStartSession(self.adapter, 0x400000)  # 4 MiB ring
        if not self.session:
            d.WintunCloseAdapter(self.adapter)
            raise ctypes.WinError(ctypes.get_last_error())
        self.name = name
        self.stop_event = threading.Event()
        self.incoming = []
        self.lock = threading.Lock()
        d.WintunGetReadWaitEvent.argtypes = [ctypes.c_void_p]
        d.WintunGetReadWaitEvent.restype = wintypes.HANDLE
        self.event = d.WintunGetReadWaitEvent(self.session)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.reader = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader.start()

    def _reader_loop(self):
        d = self.dll
        while not self.stop_event.is_set():
            size = wintypes.DWORD()
            packet = d.WintunReceivePacket(self.session, ctypes.byref(size))
            if packet:
                try:
                    raw = ctypes.string_at(packet, size.value)
                    with self.lock:
                        self.incoming.append(raw)
                finally:
                    d.WintunReleaseReceivePacket(self.session, packet)
            else:
                error = ctypes.get_last_error()
                if error == 259:  # ERROR_NO_MORE_ITEMS
                    self.kernel.WaitForSingleObject(self.event, 100)
                else:
                    time.sleep(0.02)

    def fileno(self):
        return -1  # Windows receive uses the dedicated Wintun reader thread.

    def read(self, size=65535):
        while not self.stop_event.is_set():
            with self.lock:
                if self.incoming:
                    return self.incoming.pop(0)
            time.sleep(0.01)
        return b""

    def write(self, packet):
        buf = self.dll.WintunAllocateSendPacket(self.session, len(packet))
        if not buf:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(buf, packet, len(packet))
        self.dll.WintunSendPacket(self.session, buf)
        return len(packet)

    def close(self):
        self.stop_event.set()
        self.reader.join(timeout=1)
        self.dll.WintunEndSession(self.session)
        self.dll.WintunCloseAdapter(self.adapter)


def open_tun(args):
    system = platform.system()
    if system == "Windows":
        return WindowsWintun(args.interface, args.wintun_dll)
    if system == "Linux":
        return LinuxTun(args.interface)
    if system == "Darwin":
        return MacTun(args.utun_unit)
    raise OSError(f"Unsupported operating system: {system}")


def configure_address(tun, address: str | None):
    """Assign an IPv4 address/prefix to the created interface."""
    if not address:
        return
    try:
        ipif = ipaddress.ip_interface(address)
    except ValueError as exc:
        raise ValueError(f"invalid --address {address!r}; use IPv4 CIDR such as 44.0.0.1/24") from exc
    if ipif.version != 4:
        raise ValueError("--address currently supports IPv4 CIDR notation only")

    system = platform.system()
    if system == "Linux":
        subprocess.run(["ip", "address", "add", str(ipif), "dev", tun.name], check=True)
        subprocess.run(["ip", "link", "set", "dev", tun.name, "up"], check=True)
    elif system == "Windows":
        subprocess.run([
            "netsh", "interface", "ipv4", "set", "address", f"name={tun.name}",
            "source=static", f"address={ipif.ip}", f"mask={ipif.network.netmask}",
        ], check=True)
    elif system == "Darwin":
        # macOS utun is inherently point-to-point. Select a distinct peer
        # from the requested subnet, then install the full subnet route.
        peer = next((candidate for candidate in ipif.network.hosts()
                     if candidate != ipif.ip), ipif.ip)
        subprocess.run([
            "ifconfig", tun.name, "inet", str(ipif.ip), str(peer),
            "netmask", str(ipif.network.netmask), "up",
        ], check=True)
        route = ["route", "-n", "add", "-net", str(ipif.network), "-interface", tun.name]
        try:
            subprocess.run(route, check=True)
        except subprocess.CalledProcessError:
            # ifconfig may already have installed the connected route.
            subprocess.run(["route", "-n", "change", "-net", str(ipif.network),
                            "-interface", tun.name], check=True)
    else:
        raise OSError(f"Address configuration is unsupported on {system}")


def disable_interface_ipv6(tun):
    """Ask the OS to disable IPv6 on this interface; packet filtering is the hard stop."""
    system = platform.system()
    try:
        if system == "Linux":
            subprocess.run([
                "sysctl", "-w", f"net.ipv6.conf.{tun.name}.disable_ipv6=1",
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        elif system == "Darwin":
            subprocess.run(["ifconfig", tun.name, "-inet6"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        elif system == "Windows":
            env = os.environ.copy()
            env["KISS_TUN_ADAPTER"] = tun.name
            subprocess.run([
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "Disable-NetAdapterBinding -Name $env:KISS_TUN_ADAPTER "
                "-ComponentID ms_tcpip6 -ErrorAction Stop",
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
               text=True, env=env)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Warning: could not disable IPv6 on {tun.name}: {exc}", file=sys.stderr)


class IPv4UnicastOnly:
    """Reject IPv6 and noisy IPv4 broadcast, multicast, and discovery packets."""

    def __init__(self, address: str | None):
        self.network = ipaddress.ip_interface(address).network if address else None

    def allows(self, packet: bytes) -> bool:
        if len(packet) < 20 or packet[0] >> 4 != 4:
            return False
        header_len = (packet[0] & 0x0F) * 4
        if header_len < 20 or len(packet) < header_len:
            return False
        source = ipaddress.IPv4Address(packet[12:16])
        destination = ipaddress.IPv4Address(packet[16:20])
        if (destination.is_multicast or destination == ipaddress.IPv4Address("255.255.255.255")
                or source.is_link_local or destination.is_link_local):
            return False
        if self.network and self.network.prefixlen <= 30 and destination == self.network.broadcast_address:
            return False
        protocol = packet[9]
        if protocol == 2:  # IGMP
            return False
        if protocol == 17 and len(packet) >= header_len + 8:
            source_port, destination_port = struct.unpack_from("!HH", packet, header_len)
            if source_port in (67, 68, 1900, 5353, 5355) or destination_port in (67, 68, 1900, 5353, 5355):
                return False
        return True


class TCPKiss:
    """TCP byte stream for Dire Wolf's KISS-over-TCP service."""

    def __init__(self, host: str, port: int, connect_timeout: float = 1.0):
        self.sock = socket.create_connection((host, port), timeout=connect_timeout)
        self.sock.settimeout(0.2)

    def read(self, size=4096):
        try:
            data = self.sock.recv(size)
        except socket.timeout:
            return b""
        if not data:
            raise ConnectionError("KISS TCP server closed the connection")
        return data

    def write(self, data):
        self.sock.sendall(data)
        return len(data)

    def close(self):
        self.sock.close()


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def has_administrator_rights():
    if os.name == "nt":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def start_direwolf_process(command):
    """Start Dire Wolf normally on Windows, with reduced UID/GID on Unix."""
    if os.name == "nt":
        return subprocess.Popen(command)
    if os.geteuid() != 0:
        raise PermissionError("the bridge must run as root to create the tunnel")
    import pwd
    target_uid = int(os.environ.get("SUDO_UID", "65534"))
    target = pwd.getpwuid(target_uid)
    target_gid = int(os.environ.get("SUDO_GID", str(target.pw_gid)))
    groups = os.getgrouplist(target.pw_name, target_gid)
    return subprocess.Popen(command, user=target_uid, group=target_gid,
                            extra_groups=groups)


def connect_or_start_direwolf(args, stop):
    """Use an existing KISS service, or start Dire Wolf from PATH/local dir."""
    try:
        return TCPKiss(args.host, args.tcp_port), None
    except OSError:
        pass

    if not args.allow_direwolf_autostart:
        raise ConnectionError(
            f"could not connect to KISS TCP at {args.host}:{args.tcp_port}; "
            "Dire Wolf auto-start is disabled when --host or --tcp-port is specified"
        )

    candidates = []
    path_executable = shutil.which("direwolf")
    if path_executable:
        candidates.append(([path_executable], "Dire Wolf from PATH"))

    local_executable = Path.cwd() / ("direwolf.exe" if os.name == "nt" else "direwolf")
    local_config = Path.cwd() / "direwolf.conf"
    if local_executable.is_file() and local_config.is_file():
        candidates.append(([str(local_executable), "-c", str(local_config)],
                           "local Dire Wolf with ./direwolf.conf"))

    problems = []
    for command, description in candidates:
        print(f"KISS TCP unavailable; starting {description}...", file=sys.stderr)
        try:
            process = start_direwolf_process(command)
        except OSError as exc:
            problems.append(f"{description}: {exc}")
            continue

        deadline = time.monotonic() + args.direwolf_startup_timeout
        while time.monotonic() < deadline and not stop.is_set():
            if process.poll() is not None:
                problems.append(f"{description} exited with status {process.returncode}")
                break
            try:
                return TCPKiss(args.host, args.tcp_port, connect_timeout=0.5), process
            except OSError:
                time.sleep(0.25)
        else:
            problems.append(f"{description} did not open {args.host}:{args.tcp_port} "
                            f"within {args.direwolf_startup_timeout:g}s")
        stop_process(process)
        if stop.is_set():
            raise KeyboardInterrupt

    if not candidates:
        problems.append("Dire Wolf was not found on PATH, and ./direwolf with ./direwolf.conf "
                        "was not available in the current directory")
    details = "; ".join(problems)
    raise ConnectionError(f"could not connect to Dire Wolf KISS TCP at {args.host}:{args.tcp_port}. {details}")


def bridge(args):
    stop = threading.Event()
    old_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    tun = None
    link = None
    direwolf_process = None
    worker = None
    try:
        tun = open_tun(args)
        configure_address(tun, args.address)
        disable_interface_ipv6(tun)
        link, direwolf_process = connect_or_start_direwolf(args, stop)
        link_description = f"Dire Wolf KISS TCP at {args.host}:{args.tcp_port}"
        decoder = KissDecoder()
        ip_policy = IPv4UnicastOnly(args.address)
        print(f"TUN interface {tun.name}; {link_description}; IPv4 unicast only")

        def tcp_to_tun():
            try:
                while not stop.is_set():
                    data = link.read(4096)
                    for kiss_port, command, packet in decoder.feed(data):
                        if command == KISS_DATA and kiss_port == args.kiss_port and packet:
                            if not ip_policy.allows(packet):
                                continue
                            try:
                                tun.write(packet)
                            except (OSError, ValueError) as exc:
                                print(f"Dropping packet from TNC: {exc}", file=sys.stderr)
            except (OSError, ConnectionError) as exc:
                if not stop.is_set():
                    print(f"KISS connection ended: {exc}", file=sys.stderr)
                    stop.set()

        worker = threading.Thread(target=tcp_to_tun, daemon=True)
        worker.start()
        while not stop.is_set():
            if tun.fileno() >= 0:
                readable, _, _ = select.select([tun.fileno()], [], [], 0.2)
                if not readable:
                    continue
            packet = tun.read()
            if packet and ip_policy.allows(packet):
                link.write(kiss_encode(packet, args.kiss_port))
    finally:
        stop.set()
        if worker is not None:
            worker.join(timeout=1)
        signal.signal(signal.SIGTERM, old_sigterm)
        if link is not None:
            link.close()
        if tun is not None:
            tun.close()
        stop_process(direwolf_process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="Dire Wolf TCP host (default: 127.0.0.1)")
    parser.add_argument("--tcp-port", type=int,
                        help="Dire Wolf KISS TCP port (default: 8001)")
    parser.add_argument("--direwolf-startup-timeout", type=float, default=10.0,
                        help="seconds to wait for a started Dire Wolf KISS server (default: 10)")
    parser.add_argument("--interface", default="kiss0", help="TUN/Wintun interface name (default: kiss0)")
    parser.add_argument("--address", help="assign an IPv4 address and prefix in CIDR notation")
    parser.add_argument("--kiss-port", type=int, default=0, help="KISS port number 0..15 (default: 0)")
    parser.add_argument("--utun-unit", type=int,
                        help="request a specific macOS utun unit (default: macOS chooses a free unit)")
    parser.add_argument("--wintun-dll", help="path to Wintun DLL (default: beside this script)")
    args = parser.parse_args()
    args.allow_direwolf_autostart = args.host is None and args.tcp_port is None
    if args.host is None:
        args.host = "127.0.0.1"
    if args.tcp_port is None:
        args.tcp_port = 8001
    if not has_administrator_rights():
        print("Error: administrator/root privileges are required to create and configure the tunnel.",
              file=sys.stderr)
        return 1
    if args.address is None:
        if not sys.stdin.isatty():
            parser.error("--address is required when stdin is not interactive; use IPv4 CIDR notation")
        try:
            args.address = input("Interface IPv4 address/prefix (CIDR notation): ").strip()
        except EOFError:
            parser.error("no address entered; use --address IPv4/PREFIX")
    try:
        parsed_address = ipaddress.ip_interface(args.address)
    except ValueError as exc:
        parser.error(f"invalid address {args.address!r}; expected IPv4 CIDR notation (address/prefix): {exc}")
    if parsed_address.version != 4:
        parser.error("only IPv4 CIDR addresses are supported")
    args.address = str(parsed_address)
    try:
        bridge(args)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
ZARA 3.0 - MCP Network Server
MCP server for Windows network operations.
"""

from __future__ import annotations

import ipaddress
import platform
import socket
import subprocess

from core.mcp.base_server import StdioMCPServer


class NetworkMCPServer(StdioMCPServer):
    """MCP server for network operations."""

    def __init__(self):
        super().__init__("zara-network", "1.0.0")
        self._register_tools()

    def _register_tools(self):
        """Register network operation tools."""

        @self.tool(
            name="network_interfaces",
            description="List network interfaces",
            input_schema={
                "type": "object",
                "properties": {},
            }
        )
        async def network_interfaces() -> dict:
            try:
                import psutil
                interfaces = []
                for name, addrs in psutil.net_if_addrs().items():
                    if_addrs = []
                    for addr in addrs:
                        if_addrs.append({
                            "family": str(addr.family),
                            "address": addr.address,
                            "netmask": addr.netmask,
                            "broadcast": addr.broadcast,
                        })
                    stats = psutil.net_if_stats().get(name)
                    interfaces.append({
                        "name": name,
                        "addresses": if_addrs,
                        "is_up": stats.isup if stats else False,
                        "speed": stats.speed if stats else 0,
                        "mtu": stats.mtu if stats else 0,
                    })
                return {"success": True, "interfaces": interfaces}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="network_connections",
            description="List network connections",
            input_schema={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["inet", "inet4", "inet6", "tcp", "tcp4", "tcp6", "udp", "udp4", "udp6"], "default": "inet", "description": "Connection type filter"},
                },
            }
        )
        async def network_connections(kind: str = "inet") -> dict:
            try:
                import psutil
                conns = []
                for conn in psutil.net_connections(kind=kind):
                    conns.append({
                        "fd": conn.fd,
                        "family": str(conn.family),
                        "type": str(conn.type),
                        "laddr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                        "raddr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                        "status": conn.status,
                        "pid": conn.pid,
                    })
                return {"success": True, "connections": conns, "count": len(conns)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="network_ping",
            description="Ping a host",
            input_schema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Host to ping"},
                    "count": {"type": "integer", "default": 4, "description": "Number of pings"},
                    "timeout": {"type": "integer", "default": 1000, "description": "Timeout in ms"},
                },
                "required": ["host"],
            }
        )
        async def network_ping(host: str, count: int = 4, timeout: int = 1000) -> dict:
            try:
                system = platform.system().lower()
                if system == "windows":
                    cmd = ["ping", "-n", str(count), "-w", str(timeout), host]
                else:
                    cmd = ["ping", "-c", str(count), "-W", str(timeout // 1000), host]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                # Parse output
                success = result.returncode == 0
                output = result.stdout

                # Extract stats
                stats = {}
                for line in output.splitlines():
                    if "Packets:" in line or "packets transmitted" in line:
                        # Parse stats line
                        import re
                        if system == "windows":
                            m = re.search(r"Sent = (\d+), Received = (\d+), Lost = (\d+)", line)
                            if m:
                                stats = {"sent": int(m.group(1)), "received": int(m.group(2)), "lost": int(m.group(3))}
                        else:
                            m = re.search(r"(\d+) packets transmitted, (\d+) received", line)
                            if m:
                                stats = {"sent": int(m.group(1)), "received": int(m.group(2)), "lost": int(m.group(1)) - int(m.group(2))}
                    if "Minimum" in line or "min/avg/max" in line:
                        import re
                        m = re.search(r"[= ](\d+)ms", line)
                        if m:
                            stats["min_ms"] = int(m.group(1))

                return {"success": success, "host": host, "output": output, "stats": stats}
            except subprocess.TimeoutExpired:
                return {"success": False, "error": "Ping timeout"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="network_port_scan",
            description="Scan ports on a host",
            input_schema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Host to scan"},
                    "ports": {"type": "array", "items": {"type": "integer"}, "description": "Ports to scan"},
                    "timeout": {"type": "integer", "default": 1000, "description": "Timeout per port in ms"},
                },
                "required": ["host", "ports"],
            }
        )
        async def network_port_scan(host: str, ports: list[int], timeout: int = 1000) -> dict:
            try:
                results = []
                for port in ports:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(timeout / 1000)
                        result = sock.connect_ex((host, port))
                        sock.close()
                        results.append({
                            "port": port,
                            "open": result == 0,
                        })
                    except Exception:
                        results.append({"port": port, "open": False, "error": "connection failed"})

                open_ports = [r["port"] for r in results if r["open"]]
                return {"success": True, "host": host, "results": results, "open_ports": open_ports}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="network_dns_lookup",
            description="DNS lookup for a hostname",
            input_schema={
                "type": "object",
                "properties": {
                    "hostname": {"type": "string", "description": "Hostname to resolve"},
                    "record_type": {"type": "string", "enum": ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "ALL"], "default": "A", "description": "Record type"},
                },
                "required": ["hostname"],
            }
        )
        async def network_dns_lookup(hostname: str, record_type: str = "A") -> dict:
            try:
                import dns.resolver

                if record_type == "ALL":
                    types = ["A", "AAAA", "CNAME", "MX", "NS", "TXT"]
                else:
                    types = [record_type]

                results = {}
                for rtype in types:
                    try:
                        answers = dns.resolver.resolve(hostname, rtype)
                        results[rtype] = [str(r) for r in answers]
                    except dns.resolver.NXDOMAIN:
                        results[rtype] = []
                    except dns.resolver.NoAnswer:
                        results[rtype] = []
                    except Exception as e:
                        results[rtype] = [f"Error: {e}"]

                return {"success": True, "hostname": hostname, "records": results}
            except ImportError:
                # Fallback to socket
                try:
                    if record_type in ["A", "ALL"]:
                        ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
                        results = {"A": [ip[4][0] for ip in ips]}
                    if record_type in ["AAAA", "ALL"]:
                        ips = socket.getaddrinfo(hostname, None, socket.AF_INET6)
                        results["AAAA"] = [ip[4][0] for ip in ips]
                    return {"success": True, "hostname": hostname, "records": results}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="network_trace_route",
            description="Trace route to a host",
            input_schema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Host to trace"},
                    "max_hops": {"type": "integer", "default": 30, "description": "Maximum hops"},
                },
                "required": ["host"],
            }
        )
        async def network_trace_route(host: str, max_hops: int = 30) -> dict:
            try:
                system = platform.system().lower()
                if system == "windows":
                    cmd = ["tracert", "-h", str(max_hops), host]
                else:
                    cmd = ["traceroute", "-m", str(max_hops), host]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                return {"success": result.returncode == 0, "host": host, "output": result.stdout, "error": result.stderr if result.returncode != 0 else None}
            except subprocess.TimeoutExpired:
                return {"success": False, "error": "Trace route timeout"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="network_http_request",
            description="Make an HTTP request",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"], "default": "GET"},
                    "headers": {"type": "object", "description": "Request headers"},
                    "data": {"type": "string", "description": "Request body"},
                    "timeout": {"type": "integer", "default": 10, "description": "Timeout in seconds"},
                },
                "required": ["url"],
            }
        )
        async def network_http_request(url: str, method: str = "GET", headers: dict = None, data: str = None, timeout: int = 10) -> dict:
            try:
                import urllib.error
                import urllib.request

                req = urllib.request.Request(url, method=method)

                if headers:
                    for k, v in headers.items():
                        req.add_header(k, v)

                if data and method in ["POST", "PUT", "PATCH"]:
                    req.data = data.encode("utf-8")

                with urllib.request.urlopen(req, timeout=timeout) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    return {
                        "success": True,
                        "url": url,
                        "status": response.status,
                        "headers": dict(response.headers),
                        "body": body,
                    }
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                return {"success": False, "status": e.code, "body": body, "error": f"HTTP {e.code}"}
            except urllib.error.URLError as e:
                return {"success": False, "error": str(e.reason)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="network_wifi_networks",
            description="List available WiFi networks (Windows)",
            input_schema={
                "type": "object",
                "properties": {},
            }
        )
        async def network_wifi_networks() -> dict:
            try:
                system = platform.system().lower()
                if system != "windows":
                    return {"success": False, "error": "WiFi scan only supported on Windows"}

                # Use netsh
                result = subprocess.run(
                    ["netsh", "wlan", "show", "networks", "mode=bssid"],
                    capture_output=True, text=True, timeout=15
                )

                if result.returncode != 0:
                    return {"success": False, "error": result.stderr}

                # Parse output
                networks = []
                current = {}
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("SSID") and ":" in line:
                        if current and "ssid" in current:
                            networks.append(current)
                        current = {"ssid": line.split(":", 1)[1].strip()}
                    elif line.startswith("Network type") and ":" in line:
                        current["network_type"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Authentication") and ":" in line:
                        current["authentication"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Encryption") and ":" in line:
                        current["encryption"] = line.split(":", 1)[1].strip()
                    elif line.startswith("BSSID") and ":" in line:
                        current["bssid"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Signal") and ":" in line:
                        current["signal"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Radio type") and ":" in line:
                        current["radio_type"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Channel") and ":" in line:
                        current["channel"] = line.split(":", 1)[1].strip()

                if current and "ssid" in current:
                    networks.append(current)

                return {"success": True, "networks": networks, "count": len(networks)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="network_ip_info",
            description="Get IP information",
            input_schema={
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "IP address (empty for local)"},
                },
            }
        )
        async def network_ip_info(ip: str = "") -> dict:
            try:
                if not ip:
                    # Get local IP
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        s.connect(("8.8.8.8", 80))
                        ip = s.getsockname()[0]
                    finally:
                        s.close()

                # Check if private
                ip_obj = ipaddress.ip_address(ip)
                is_private = ip_obj.is_private
                is_loopback = ip_obj.is_loopback
                is_multicast = ip_obj.is_multicast

                return {
                    "success": True,
                    "ip": ip,
                    "version": ip_obj.version,
                    "is_private": is_private,
                    "is_loopback": is_loopback,
                    "is_multicast": is_multicast,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}


def main():
    """Entry point for running the server."""
    import asyncio
    server = NetworkMCPServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()

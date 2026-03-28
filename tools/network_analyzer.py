#!/usr/bin/env python3
"""
Netzwerk-Analyzer für GABI Gateway
Ermöglicht Netzwerk-Analysen mit Wireshark (GUI) oder tcpdump/tshark (CLI)

Verwendung:
    python tools/network_analyzer.py capture --duration 30
    python tools/network_analyzer.py analyze --file capture.pcap
    python tools/network_analyzer.py scan
"""
import argparse
import subprocess
import sys
import os
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# Verzeichnis für Captures
CAPTURE_DIR = Path(__file__).parent.parent / "data" / "captures"
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)


def check_wireshark() -> Dict[str, Any]:
    """Prüft ob Wireshark/tshark verfügbar ist."""
    result = {
        "wireshark": False,
        "tshark": False,
        "tcpdump": False,
        "scapy": False,
        "any_available": False
    }

    # Windows: wireshark.exe
    try:
        subprocess.run(["tshark", "--version"], capture_output=True, timeout=2)
        result["tshark"] = True
        result["any_available"] = True
    except:
        pass

    # tcpdump (Linux/Mac)
    try:
        subprocess.run(["tcpdump", "--version"], capture_output=True, timeout=2)
        result["tcpdump"] = True
        result["any_available"] = True
    except:
        pass

    # Scapy (Python)
    try:
        import scapy.all
        result["scapy"] = True
        result["any_available"] = True
    except ImportError:
        pass

    return result


def list_interfaces() -> List[Dict[str, Any]]:
    """Listet alle Netzwerk-Interfaces."""
    interfaces = []

    # Mit tshark
    try:
        result = subprocess.run(
            ["tshark", "-D"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                # Format: 1. \Device\NPF_{...} (Interface Name)
                match = re.match(r"(\d+)\.\s+(.+)\s+\((.+)\)", line)
                if match:
                    interfaces.append({
                        "index": int(match.group(1)),
                        "name": match.group(2).strip(),
                        "description": match.group(3).strip()
                    })
    except:
        pass

    # Fallback: scapy
    if not interfaces:
        try:
            from scapy.all import get_if_list, get_if_addr
            for iface in get_if_list():
                try:
                    addr = get_if_addr(iface)
                    interfaces.append({
                        "index": len(interfaces) + 1,
                        "name": iface,
                        "description": f"IP: {addr}",
                        "ip": addr
                    })
                except:
                    interfaces.append({
                        "index": len(interfaces) + 1,
                        "name": iface,
                        "description": "Unknown"
                    })
        except:
            pass

    return interfaces


def capture_traffic(
    interface: Optional[str] = None,
    duration: int = 30,
    filter_expr: Optional[str] = None,
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Nimmt Netzwerk-Traffic auf.

    Args:
        interface: Interface-Name oder Index (None = erstes verfügbare)
        duration: Aufnahmedauer in Sekunden
        filter_expr: BPF-Filter (z.B. "tcp port 80")
        output_file: Ausgabedatei (None = auto-generiert)
    """
    tools = check_wireshark()

    if not tools["any_available"]:
        return {
            "success": False,
            "error": "Keine Capture-Tools verfügbar. Installiere Wireshark oder tcpdump."
        }

    # Dateiname generieren
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = str(CAPTURE_DIR / f"capture_{timestamp}.pcap")

    # Interface auflösen
    if interface and interface.isdigit():
        iface_list = list_interfaces()
        idx = int(interface)
        for iface in iface_list:
            if iface["index"] == idx:
                interface = iface["name"]
                break

    try:
        if tools["tshark"]:
            cmd = ["tshark", "-a", f"duration:{duration}", "-w", output_file]
            if interface:
                cmd.extend(["-i", interface])
            if filter_expr:
                cmd.extend(["-f", filter_expr])

            print(f"Starte Capture mit tshark ({duration}s)...")
            print(f"Interface: {interface or 'default'}")
            print(f"Filter: {filter_expr or 'none'}")
            print(f"Output: {output_file}")
            print("-" * 50)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 10)

            if os.path.exists(output_file):
                size = os.path.getsize(output_file)
                return {
                    "success": True,
                    "file": output_file,
                    "size_bytes": size,
                    "duration": duration,
                    "tool": "tshark"
                }
            else:
                return {
                    "success": False,
                    "error": "Capture-Datei wurde nicht erstellt",
                    "stderr": result.stderr
                }

        elif tools["tcpdump"]:
            cmd = ["tcpdump", "-G", str(duration), "-W", "1", "-w", output_file]
            if interface:
                cmd.extend(["-i", interface])
            if filter_expr:
                cmd.append(filter_expr)

            print(f"Starte Capture mit tcpdump ({duration}s)...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 10)

            if os.path.exists(output_file):
                size = os.path.getsize(output_file)
                return {
                    "success": True,
                    "file": output_file,
                    "size_bytes": size,
                    "duration": duration,
                    "tool": "tcpdump"
                }
            else:
                return {
                    "success": False,
                    "error": "Capture fehlgeschlagen",
                    "stderr": result.stderr
                }

        else:
            return {
                "success": False,
                "error": "Keine geeigneten Tools verfügbar"
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Timeout nach {duration + 10}s"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def analyze_capture(file_path: str, summary_only: bool = False) -> Dict[str, Any]:
    """
    Analysiert eine PCAP-Datei.

    Args:
        file_path: Pfad zur PCAP-Datei
        summary_only: Nur Zusammenfassung, keine Details
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"Datei nicht gefunden: {file_path}"}

    tools = check_wireshark()
    results = {
        "success": True,
        "file": file_path,
        "analysis": {}
    }

    try:
        # Mit tshark statistische Auswertung
        if tools["tshark"]:
            # Statistik
            stats_result = subprocess.run(
                ["tshark", "-r", file_path, "-q", "-z", "io,phs"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if stats_result.returncode == 0:
                results["analysis"]["statistics"] = stats_result.stdout

            # Protokoll-Hierarchie
            proto_result = subprocess.run(
                ["tshark", "-r", file_path, "-q", "-z", "conv,ip"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if proto_result.returncode == 0:
                results["analysis"]["conversations"] = proto_result.stdout

            # Anzahl Pakete
            count_result = subprocess.run(
                ["tshark", "-r", file_path, "-T", "fields", "-e", "frame.number"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if count_result.returncode == 0:
                packet_count = len(count_result.stdout.strip().split("\n"))
                results["analysis"]["packet_count"] = packet_count

            # Zusammenfassung
            if not summary_only:
                # Top-Talker
                top_result = subprocess.run(
                    ["tshark", "-r", file_path, "-q", "-z", "conv,ip", "-n"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if top_result.returncode == 0:
                    results["analysis"]["top_talkers"] = top_result.stdout[:2000]

                # HTTP-Übersicht (falls vorhanden)
                http_result = subprocess.run(
                    ["tshark", "-r", file_path, "-Y", "http", "-T", "fields", "-e", "http.host", "-e", "http.request.uri"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if http_result.returncode == 0 and http_result.stdout.strip():
                    results["analysis"]["http_requests"] = http_result.stdout[:1000]

        # Scapy als Fallback für Detail-Analyse
        elif tools["scapy"]:
            from scapy.all import rdpcap

            packets = rdpcap(file_path)
            results["analysis"]["packet_count"] = len(packets)

            # Protokoll-Statistik
            protocols = {}
            for pkt in packets:
                proto = pkt.name
                protocols[proto] = protocols.get(proto, 0) + 1

            results["analysis"]["protocols"] = protocols

        return results

    except Exception as e:
        return {
            "success": False,
            "error": f"Analyse fehlgeschlagen: {e}"
        }


def scan_network(
    target: Optional[str] = None,
    ports: Optional[str] = None
) -> Dict[str, Any]:
    """
    Scannt das lokale Netzwerk.
    Verwendet nmap (falls verfügbar).
    """
    results = {
        "success": True,
        "scan_type": "network",
        "hosts": []
    }

    # nmap verfügbar?
    try:
        subprocess.run(["nmap", "--version"], capture_output=True, timeout=2)
        has_nmap = True
    except:
        has_nmap = False

    if not has_nmap:
        return {
            "success": False,
            "error": "nmap nicht installiert. Verwende: sudo apt install nmap"
        }

    try:
        if target:
            # Spezifischer Scan
            cmd = ["nmap", "-sS", "-O", "-F", target]
            if ports:
                cmd = ["nmap", "-sS", "-p", ports, target]
        else:
            # Lokales Netzwerk entdecken
            # Annahme: /24 Subnetz
            import socket
            hostname = socket.gethostname()
            local_ip = socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
            subnet = ".".join(local_ip.split(".")[:3]) + ".0/24"

            cmd = ["nmap", "-sn", subnet]
            results["scan_type"] = "host_discovery"
            results["subnet"] = subnet

        print(f"Starte Scan: {' '.join(cmd)}")
        print("Dies kann einige Minuten dauern...")
        print("-" * 50)

        scan_result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 Minuten max
        )

        if scan_result.returncode == 0:
            results["raw_output"] = scan_result.stdout

            # Parse Ergebnisse
            hosts = []
            current_host = {}

            for line in scan_result.stdout.split("\n"):
                # Host-Zeile
                if "Nmap scan report for" in line:
                    if current_host:
                        hosts.append(current_host)
                    ip_match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", line)
                    if ip_match:
                        current_host = {
                            "ip": ip_match.group(1),
                            "hostname": line.split("for")[1].split("(")[0].strip()
                        }
                    else:
                        current_host = {"ip": line.split()[-1]}

                # Port-Zeile
                elif re.match(r"\d+/\w+", line):
                    if "open" in line:
                        parts = line.split()
                        port_info = {
                            "port": parts[0],
                            "state": parts[1],
                            "service": parts[2] if len(parts) > 2 else "unknown"
                        }
                        if "ports" not in current_host:
                            current_host["ports"] = []
                        current_host["ports"].append(port_info)

            if current_host:
                hosts.append(current_host)

            results["hosts_found"] = len(hosts)
            results["hosts"] = hosts

        return results

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Scan-Timeout (5 Minuten überschritten)"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def generate_report(capture_file: str) -> str:
    """Generiert einen HTML-Report aus einer Capture-Datei."""
    analysis = analyze_capture(capture_file)

    if not analysis.get("success"):
        return f"Fehler: {analysis.get('error')}"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = f"""
# Netzwerk-Analyse Report
**Erstellt:** {timestamp}
**Datei:** {capture_file}

## Zusammenfassung
- **Pakete:** {analysis.get('analysis', {}).get('packet_count', 'N/A')}
- **Größe:** {os.path.getsize(capture_file) / 1024:.2f} KB

## Protokoll-Statistik
```
{analysis.get('analysis', {}).get('statistics', 'N/A')[:500]}
```

## Top-Talker (IP-Konversationen)
```
{analysis.get('analysis', {}).get('conversations', 'N/A')[:1000]}
```

## HTTP-Aktivität
```
{analysis.get('analysis', {}).get('http_requests', 'Keine HTTP-Daten')[:500]}
```
"""

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Netzwerk-Analyzer für GABI Gateway"
    )
    subparsers = parser.add_subparsers(dest="command", help="Kommando")

    # Status
    status_parser = subparsers.add_parser("status", help="Zeigt verfügbare Tools")

    # Interfaces
    iface_parser = subparsers.add_parser("interfaces", help="Listet Netzwerk-Interfaces")

    # Capture
    capture_parser = subparsers.add_parser("capture", help="Nimmt Traffic auf")
    capture_parser.add_argument("-i", "--interface", help="Interface (Name oder Index)")
    capture_parser.add_argument("-d", "--duration", type=int, default=30, help="Dauer in Sekunden (default: 30)")
    capture_parser.add_argument("-f", "--filter", help="BPF-Filter (z.B. 'tcp port 80')")
    capture_parser.add_argument("-o", "--output", help="Ausgabedatei")

    # Analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analysiert PCAP-Datei")
    analyze_parser.add_argument("file", help="PCAP-Datei")
    analyze_parser.add_argument("--summary", action="store_true", help="Nur Zusammenfassung")

    # Scan
    scan_parser = subparsers.add_parser("scan", help="Scannt Netzwerk")
    scan_parser.add_argument("-t", "--target", help="Ziel-Host oder Netzwerk")
    scan_parser.add_argument("-p", "--ports", help="Ports (z.B. 80,443,22)")

    # Report
    report_parser = subparsers.add_parser("report", help="Erstellt Report")
    report_parser.add_argument("file", help="PCAP-Datei")

    args = parser.parse_args()

    if args.command == "status":
        tools = check_wireshark()
        print("🔧 Verfügbare Tools:")
        print(f"  Tshark: {'✅' if tools['tshark'] else '❌'}")
        print(f"  TCPDump: {'✅' if tools['tcpdump'] else '❌'}")
        print(f"  Scapy: {'✅' if tools['scapy'] else '❌'}")
        print(f"\nAny available: {'✅' if tools['any_available'] else '❌'}")

    elif args.command == "interfaces":
        print("🌐 Netzwerk-Interfaces:")
        interfaces = list_interfaces()
        for iface in interfaces:
            print(f"  {iface['index']}. {iface['name']}")
            print(f"     {iface['description']}")

    elif args.command == "capture":
        result = capture_traffic(
            interface=args.interface,
            duration=args.duration,
            filter_expr=args.filter,
            output_file=args.output
        )
        print(json.dumps(result, indent=2))

    elif args.command == "analyze":
        result = analyze_capture(args.file, args.summary)
        print(json.dumps(result, indent=2))

    elif args.command == "scan":
        result = scan_network(args.target, args.ports)
        print(json.dumps(result, indent=2))

    elif args.command == "report":
        report = generate_report(args.file)
        print(report)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Project-S - Command Library Module

This module imports command lists from system_commands.py and creates a unified 
command library dictionary for use in the AI command handler.
"""

import subprocess
import os
import platform
import socket
import datetime
import json
import psutil  # Tipp: ha ez hiányzik, telepítsd: pip install psutil
from core.system_commands import SYSTEM_COMMANDS, POWERSHELL_COMMANDS, SECURITY_COMMANDS

# Create a unified command library dictionary
# Keys are command identifiers and values are the actual commands
COMMAND_LIBRARY = {}

# Cache rendered command results
_COMMAND_CACHE = {}
_MAX_CACHE_SIZE = 100
_CACHE_TTL = 300  # 5 perc cache élettartam másodpercben

# Helper function to execute a command with subprocess
def _execute_command(cmd, args=""):
    """Execute a command with subprocess and return the output"""
    full_cmd = cmd
    if args:
        full_cmd = f"{cmd} {args}"
        
    # Ellenőrizzük a cache-t
    cache_key = f"{full_cmd}__{platform.node()}"
    if cache_key in _COMMAND_CACHE:
        result, timestamp = _COMMAND_CACHE[cache_key]
        if (datetime.datetime.now() - timestamp).total_seconds() < _CACHE_TTL:
            return result
        
    # Korlátozzuk a cache méretét
    if len(_COMMAND_CACHE) >= _MAX_CACHE_SIZE:
        # A legrégebbi 10 elem törlése
        keys_to_remove = sorted(_COMMAND_CACHE.keys(), 
                             key=lambda k: _COMMAND_CACHE[k][1])[:10]
        for key in keys_to_remove:
            del _COMMAND_CACHE[key]
    
    try:
        # Biztonsági ellenőrzések
        if len(full_cmd) > 500:
            return "Hiba: Túl hosszú parancs."
            
        harmful_patterns = ["rm -rf", "deltree", "format", ":(){", "sudo rm", ">", "|"]
        if any(pattern in full_cmd.lower() for pattern in harmful_patterns):
            return "Hiba: Potenciálisan veszélyes parancs blokkolva biztonsági okokból."
        
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=15, encoding='utf-8', errors='ignore')
        output = result.stdout.strip() or result.stderr.strip()
        
        # Limit output length
        max_output_len = 1000
        if len(output) > max_output_len:
            output = output[:max_output_len] + "... [kimenet levágva]"
        
        final_output = output if output else "(Nincs kimenet)"
        
        # Cache the result
        _COMMAND_CACHE[cache_key] = (final_output, datetime.datetime.now())
        
        return final_output
    except subprocess.TimeoutExpired:
        return "Hiba: Rendszerparancs időtúllépés."
    except Exception as e:
        return f"Rendszerparancs hiba: {str(e)}"

# Function to create command entry in the library
def _add_command(command_id, command_text):
    """Add a command to the library with a function that executes it"""
    
    # Create a function that will execute this specific command
    def execute_command(args=""):
        return _execute_command(command_text, args)
    
    # Add the function to the library
    COMMAND_LIBRARY[command_id] = execute_command

# Gyorsított belső parancsok natív Python implementációkkal
def _cmd_echo(args=""):
    """Echo parancs implementálása Pythonban"""
    return args if args else ""

def _cmd_date(args=""):
    """Dátum parancs implementálása Pythonban"""
    return datetime.datetime.now().strftime("%Y-%m-%d")

def _cmd_time(args=""):
    """Idő parancs implementálása Pythonban"""
    return datetime.datetime.now().strftime("%H:%M:%S")

def _cmd_whoami(args=""):
    """Felhasználónév lekérdezése"""
    try:
        import getpass
        return getpass.getuser()
    except:
        return os.environ.get('USERNAME', 'unknown')

def _cmd_hostname(args=""):
    """Számítógépnév lekérdezése"""
    try:
        return socket.gethostname()
    except:
        return "unknown"

def _cmd_dir(args=""):
    """Könyvtár tartalmának listázása"""
    path = args.strip() if args else "."
    try:
        items = os.listdir(path)
        result = []
        for item in items:
            full_path = os.path.join(path, item)
            size = ""
            try:
                if os.path.isdir(full_path):
                    item += "/"
                else:
                    size = f" ({os.path.getsize(full_path)} bytes)"
            except:
                pass
            result.append(f"{item}{size}")
        return "\n".join(sorted(result))
    except Exception as e:
        return f"Hiba: {str(e)}"

def _cmd_cat(args=""):
    """Fájl tartalmának megjelenítése"""
    if not args:
        return "Használat: cat [fájlnév]"
        
    filepath = args.strip()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ha túl hosszú a fájl, csak az elejét jelenítsük meg
        if len(content) > 1000:
            content = content[:1000] + "...\n[A fájl további része levágva]"
            
        return content
    except Exception as e:
        return f"Hiba a fájl olvasásakor: {str(e)}"

def _cmd_sysinfo(args=""):
    """Rendszerinformáció Python-alapú implementációja"""
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        info = [
            f"Rendszernév: {platform.node()}",
            f"Operációs rendszer: {platform.system()} {platform.release()}",
            f"CPU: {platform.processor()}",
            f"CPU magok: {psutil.cpu_count(logical=False)} (fizikai), {psutil.cpu_count()} (logikai)",
            f"CPU használat: {psutil.cpu_percent()}%",
            f"Memória: {mem.total / (1024*1024*1024):.2f} GB (használt: {mem.percent}%)",
            f"Lemez: {disk.total / (1024*1024*1024):.2f} GB (használt: {disk.percent}%)",
            f"Hálózati csatolók: {', '.join(psutil.net_if_addrs().keys())}",
            f"Bootolás ideje: {datetime.datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S')}"
        ]
        return "\n".join(info)
    except ImportError:
        return "A psutil modul nem elérhető. Telepítsd: pip install psutil"
    except Exception as e:
        return f"Hiba a rendszerinformáció lekérdezésekor: {str(e)}"

def _cmd_processes(args=""):
    """Futó processek listázása Python-alapú implementációja"""
    try:
        import psutil
        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_info']):
            try:
                pinfo = proc.info
                mem = pinfo['memory_info'].rss / (1024 * 1024) if pinfo['memory_info'] else 0
                procs.append(f"{pinfo['pid']}\t{mem:.1f} MB\t{pinfo['username'] or 'N/A'}\t{pinfo['name'] or 'N/A'}")
                if len(procs) >= 25:  # Limit to top 25 processes
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        return "PID\tMemória\tFelhasználó\tFolyamatnév\n" + "\n".join(procs)
    except ImportError:
        return "A psutil modul nem elérhető. Telepítsd: pip install psutil"
    except Exception as e:
        return f"Hiba a folyamatok lekérdezésekor: {str(e)}"

def _cmd_network(args=""):
    """Hálózati kapcsolatok megjelenítése Python-alapú implementációja"""
    try:
        import psutil
        conns = []
        for conn in psutil.net_connections(kind='inet'):
            try:
                if conn.laddr and conn.laddr.port:
                    conns.append(f"{conn.laddr.ip}:{conn.laddr.port} -> " + 
                               f"{conn.raddr.ip if conn.raddr else '*'}:{conn.raddr.port if conn.raddr else '*'} " +
                               f"[{conn.status}] (PID: {conn.pid or 'N/A'})")
                if len(conns) >= 25:  # Limit to top 25 connections
                    break
            except:
                pass
                
        return "\n".join(conns) if conns else "Nem találhatók hálózati kapcsolatok"
    except ImportError:
        return "A psutil modul nem elérhető. Telepítsd: pip install psutil"
    except Exception as e:
        return f"Hiba a hálózati kapcsolatok lekérdezésekor: {str(e)}"

def _cmd_help(args=""):
    """Parancs súgó"""
    commands = {
        "echo": "Visszaadja a megadott szöveget (echo szöveg)",
        "date": "Aktuális dátum",
        "time": "Pontos idő",
        "whoami": "Felhasználónév lekérdezése",
        "hostname": "Számítógépnév",
        "dir/ls": "Könyvtár tartalmának listázása (dir [útvonal])",
        "cat/type": "Fájl tartalmának megjelenítése (cat fájlnév)",
        "sysinfo": "Részletes rendszerinformáció",
        "processes": "Futó folyamatok listája",
        "network": "Hálózati kapcsolatok listája",
        "diskspace": "Lemezterület információ",
        "help": "Ez a súgó",
        "open_ports": "Nyitott portok listázása",
        "system_info": "Teljes rendszerinformáció"
    }
    
    result = "Elérhető parancsok:\n\n"
    for cmd, desc in sorted(commands.items()):
        result += f"{cmd:<15} - {desc}\n"
        
    return result

def _cmd_diskspace(args=""):
    """Lemezterület információ Python-alapú implementációja"""
    try:
        import psutil
        disks = []
        for part in psutil.disk_partitions(all=False):
            if os.name == 'nt':
                if 'cdrom' in part.opts or part.fstype == '':
                    # Skip CD-ROM és nem elérhető meghajtók
                    continue
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(f"{part.device} ({part.mountpoint}): " +
                       f"{usage.total / (1024*1024*1024):.2f} GB total, " +
                       f"{usage.used / (1024*1024*1024):.2f} GB used ({usage.percent}%)")
                       
        return "\n".join(disks)
    except ImportError:
        return "A psutil modul nem elérhető. Telepítsd: pip install psutil"
    except Exception as e:
        return f"Hiba a lemezterület információ lekérdezésekor: {str(e)}"

# Internal commands with fast execution
INTERNAL_COMMANDS = {
    "echo": _cmd_echo,
    "date": _cmd_date,
    "time": _cmd_time,
    "whoami": _cmd_whoami,
    "hostname": _cmd_hostname,
    "dir": _cmd_dir,
    "ls": _cmd_dir,  # alias for dir
    "cat": _cmd_cat, 
    "type": _cmd_cat,  # alias for cat
    "help": _cmd_help,
    "sysinfo": _cmd_sysinfo,
    "processes": _cmd_processes,
    "network": _cmd_network,
    "diskspace": _cmd_diskspace
}

# Add internal commands to library
for cmd_id, func in INTERNAL_COMMANDS.items():
    COMMAND_LIBRARY[cmd_id] = func

# Add system commands to library
for cmd in SYSTEM_COMMANDS:
    command_parts = cmd.split('#', 1)[0].strip()  # Remove comments
    if command_parts:
        # Extract the command name for the library key
        cmd_id = command_parts.split()[0].lower()
        if cmd_id not in COMMAND_LIBRARY:  # Ne írjuk felül a belső parancsokat
            _add_command(cmd_id, command_parts)

# Add PowerShell commands with 'ps_' prefix
for cmd in POWERSHELL_COMMANDS:
    command_parts = cmd.split('#', 1)[0].strip()  # Remove comments
    if command_parts:
        # Use 'ps_' prefix for PowerShell commands
        cmd_id = "ps_" + command_parts.split()[0].lower().replace('-', '')
        if cmd_id not in COMMAND_LIBRARY:
            _add_command(cmd_id, f"powershell {command_parts}")

# Add security commands with 'sec_' prefix
for cmd in SECURITY_COMMANDS:
    command_parts = cmd.split('#', 1)[0].strip()  # Remove comments
    if command_parts:
        # Extract first significant part for command ID
        first_part = command_parts.split()[0].lower()
        if first_part in ('powershell', 'netsh', 'reg'):
            # For commands starting with these, use the second part as well
            parts = command_parts.split()
            if len(parts) > 1:
                cmd_id = f"sec_{first_part}_{parts[1].lower()}"
            else:
                cmd_id = f"sec_{first_part}"
        else:
            cmd_id = f"sec_{first_part}"
        
        # Ensure uniqueness by adding a number if needed
        original_cmd_id = cmd_id
        counter = 1
        while cmd_id in COMMAND_LIBRARY:
            cmd_id = f"{original_cmd_id}_{counter}"
            counter += 1
            
        _add_command(cmd_id, command_parts)

# Add some common command aliases
ALIASES = {
    "open_ports": "netstat -abno | findstr \"LISTENING\"",
    "running_processes": "tasklist /v",
    "network_connections": "netstat -ano",
    "system_info": "systeminfo",
    "users": "net user",
    "firewall_status": "netsh advfirewall show currentprofile",
    "installed_software": "wmic product get name,version",
    "services": "sc query",
    "startup_items": "wmic startup list full",
    "disk_info": "wmic logicaldisk get caption,description,freespace,size",
    "cpu_info": "wmic cpu get Name,NumberOfCores,MaxClockSpeed",
    "memory_info": "wmic memorychip get Capacity,Speed"
}

# Add aliases to the command library
for alias, cmd in ALIASES.items():
    if alias not in COMMAND_LIBRARY:  # Ne írjuk felül a belső parancsokat
        _add_command(alias, cmd)

# Export just the COMMAND_LIBRARY for use in other modules
__all__ = ['COMMAND_LIBRARY']
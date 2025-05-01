"""
Command dictionaries for system, PowerShell and security related operations.
"""

# Standard system commands that work across platforms
SYSTEM_COMMANDS = {
    "echo": "Display a message",
    "dir": "List directory contents",
    "cd": "Change directory",
    "pwd": "Print working directory",
    "type": "Display file contents",
    "copy": "Copy files",
    "move": "Move files",
    "del": "Delete files",
    "mkdir": "Create directory",
    "rmdir": "Remove directory",
    "cls": "Clear screen",
    "ver": "Display system version",
    "time": "Display system time",
    "date": "Display system date",
    "whoami": "Display current user",
    "hostname": "Display computer name",
}

# PowerShell specific commands
POWERSHELL_COMMANDS = {
    "Get-Content": "Read file contents",
    "Set-Content": "Write to file",
    "Add-Content": "Append to file",
    "Get-ChildItem": "List directory contents",
    "Copy-Item": "Copy files and directories",
    "Move-Item": "Move files and directories",
    "Remove-Item": "Delete files and directories",
    "New-Item": "Create new files and directories",
    "Test-Path": "Check if path exists",
    "Get-Process": "List running processes",
    "Stop-Process": "Stop a process",
    "Get-Service": "List services",
    "Start-Service": "Start a service",
    "Stop-Service": "Stop a service",
    "Invoke-WebRequest": "Make web requests",
}

# Security related commands and operations
SECURITY_COMMANDS = {
    "icacls": "Display or modify file permissions",
    "netstat": "Display network connections",
    "netsh": "Network configuration",
    "tasklist": "List running processes",
    "taskkill": "Terminate processes",
    "sc": "Service control",
    "reg": "Registry operations",
    "gpupdate": "Update group policy",
    "certutil": "Certificate management",
    "sfc": "System file checker",
    "chkdsk": "Check disk",
    "cipher": "File encryption",
    "auditpol": "Security audit policy",
    "net": "Network commands",
    "firewall": "Firewall management",
}
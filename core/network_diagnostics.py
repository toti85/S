import socket
import subprocess
import platform
import logging

logger = logging.getLogger("Network_Diagnostics")

def check_internet_connection():
    """Test internet connectivity by pinging common addresses"""
    hosts = ["8.8.8.8", "1.1.1.1", "google.com"]
    results = []
    
    for host in hosts:
        try:
            # Use ping command with appropriate options for the platform
            if platform.system().lower() == "windows":
                command = ["ping", "-n", "1", "-w", "1000", host]
            else:
                command = ["ping", "-c", "1", "-W", "1", host]
                
            result = subprocess.run(command, capture_output=True, text=True)
            success = result.returncode == 0
            results.append(f"{host}: {'✅ Online' if success else '❌ Offline'}")
        except Exception as e:
            results.append(f"{host}: ❌ Error - {str(e)}")
    
    return "\n".join(results)

def check_dns_resolution():
    """Test DNS resolution for common domains"""
    domains = ["google.com", "microsoft.com", "github.com"]
    results = []
    
    for domain in domains:
        try:
            ip = socket.gethostbyname(domain)
            results.append(f"{domain} -> {ip}")
        except Exception as e:
            results.append(f"{domain} -> ❌ Resolution failed")
    
    return "\n".join(results)

def get_network_info():
    """Get basic network configuration info"""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        return f"""
Hostname: {hostname}
Local IP: {local_ip}
"""
    except Exception as e:
        return f"❌ Error getting network info: {str(e)}"

def main():
    """Run all network diagnostics and return results"""
    results = []
    
    results.append("=== Network Configuration ===")
    results.append(get_network_info())
    
    results.append("\n=== Internet Connectivity ===")
    results.append(check_internet_connection())
    
    results.append("\n=== DNS Resolution ===")
    results.append(check_dns_resolution())
    
    return "\n".join(results)

if __name__ == "__main__":
    print(main())
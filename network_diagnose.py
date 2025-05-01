import subprocess, json, platform
from datetime import datetime

def get_arp_ips():
    # Lekérjük az ARP-tábla IP címeit
    cmd = 'arp -a'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    ips = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0][0].isdigit():
            ips.add(parts[0])
    return list(ips)


def ping_ip(ip, count=3, timeout=1000):
    # Ping TCP/IP eszköz átlagos válaszidejének mérése
    param = '-n' if platform.system().lower().startswith('win') else '-c'
    tparam = '-w' if platform.system().lower().startswith('win') else '-W'
    cmd = f'ping {param} {count} {tparam} {timeout} {ip}'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    times = []
    for line in result.stdout.splitlines():
        low = line.lower()
        if 'time=' in low:
            idx = low.find('time=')
            try:
                val = float(low[idx+5:low.find('ms', idx)].strip())
                times.append(val)
            except:
                continue
    return sum(times)/len(times) if times else None


def traceroute_ip(ip):
    # Traceroute elemzés külön modulként
    if platform.system().lower().startswith('win'):
        cmd = f'tracert -d {ip}'
    else:
        cmd = f'traceroute -n {ip}'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


def main():
    ips = get_arp_ips()
    report = []
    for ip in ips:
        avg = ping_ip(ip)
        status = 'timeout' if avg is None else 'slow' if avg > 200 else 'ok'
        report.append({'ip': ip, 'avg_time_ms': avg, 'status': status})
        print(f'{ip} avg_time_ms={avg} status={status} >>END<<')
    # Leglassabb 3
    slowest = sorted([r for r in report if r['avg_time_ms'] is not None], key=lambda x: x['avg_time_ms'], reverse=True)[:3]
    print('\nTop 3 lassú eszköz:')
    for r in slowest:
        print(r)
    # Mentés JSON-be
    out = {'timestamp': datetime.now().isoformat(), 'report': report, 'slowest': slowest}
    with open('network_report.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print('Report saved to network_report.json >>END<<')

if __name__ == '__main__':
    main()
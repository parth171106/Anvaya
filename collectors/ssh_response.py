"""Approve a bounded SSH block locally. Standard-library only; Linux nftables required.

The console has no remote execution authority. No action is applied without an
interactive approval on the monitored host. Kernel element timeouts expire blocks
even if this process exits. Existing connections and non-SSH traffic are unaffected.
"""
import argparse
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


def validate_plan(plan, host, protected, now=None):
    now = int(time.time()) if now is None else now
    if not isinstance(plan, dict) or plan.get('version') != 1 or plan.get('action') != 'block-new-ssh':
        raise ValueError('Unsupported plan.')
    if plan.get('device') != host:
        raise ValueError('Plan device does not match this server hostname.')
    for key in ('minutes', 'created_at', 'expires_at'):
        if type(plan.get(key)) is not int:
            raise ValueError('Invalid plan time or duration.')
    if plan['minutes'] not in (5, 15) or not now - 600 <= plan['created_at'] <= now + 30:
        raise ValueError('Plan is stale or has an unsupported duration; prepare a fresh plan.')
    if not now < plan['expires_at'] <= plan['created_at'] + 600:
        raise ValueError('Plan expired; prepare a fresh plan.')
    if not re.fullmatch(r'[a-f0-9]{32}', plan.get('plan_id', '')):
        raise ValueError('Invalid plan ID.')
    address = ipaddress.ip_address(plan.get('source_ip', ''))
    if not address.is_global or address.is_multicast:
        raise ValueError('Only a single public source IP can be blocked.')
    if any(address in ipaddress.ip_network(network, strict=False) for network in protected):
        raise ValueError('Refusing to block a protected, local, or connected SSH address.')
    return address


def run(args, text=None):
    result = subprocess.run(args, input=text, text=True, capture_output=True, timeout=15, check=False)
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed; no further action taken. {result.stderr.strip()[:500]}')
    return result.stdout


def protections(ip_tool, ss_tool, port, extra):
    # Read current interfaces and established peers again immediately before apply.
    protected = list(extra)
    for interface in json.loads(run([ip_tool, '-j', 'address', 'show'])):
        for addr in interface.get('addr_info', []):
            protected.append(str(ipaddress.ip_address(addr['local'])))
    peers = run([ss_tool, '-Hnt', 'state', 'established', '( sport = :' + str(port) + ' )'])
    for line in peers.splitlines():
        # ss without -a: Recv-Q Send-Q Local Peer. Some versions include State.
        peer = line.split()[-1]
        host = peer.rsplit(':', 1)[0].strip('[]').split('%')[0]
        protected.append(str(ipaddress.ip_address(host)))
    connection = os.environ.get('SSH_CONNECTION', '').split()
    if connection:
        protected.append(str(ipaddress.ip_address(connection[0])))
    return protected


def table_name(plan):
    return 'anvaya_ssh_' + plan['plan_id']


def rules(plan, address, port):
    table = table_name(plan)
    family = 'ip' if address.version == 4 else 'ip6'
    datatype = 'ipv4_addr' if address.version == 4 else 'ipv6_addr'
    # Every variable is validated; never interpolate a hostname, log, or note.
    return (f'create table inet {table}\n'
            f'add set inet {table} blocked {{ type {datatype}; flags timeout; }}\n'
            f'add element inet {table} blocked {{ {address} timeout {plan["minutes"]}m }}\n'
            f'add chain inet {table} input {{ type filter hook input priority -10; policy accept; }}\n'
            f'add rule inet {table} input ct state new tcp dport {port} {family} saddr @blocked counter drop\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--protect', action='append', required=True, help='Trusted management IP/CIDR; repeat for each range')
    parser.add_argument('--port', type=int, default=22, help='Actual SSH listener port on this server')
    parser.add_argument('--apply', action='store_true', help='Prompt for exact-IP approval, then apply')
    parser.add_argument('--unblock', action='store_true', help='Remove only the table belonging to this plan')
    args = parser.parse_args(argv)
    try:
        if sys.platform != 'linux' or os.geteuid() != 0:
            raise ValueError('Run on the monitored Linux host with sudo. Preview also needs firewall inspection.')
        if not 1 <= args.port <= 65535 or (args.apply and args.unblock):
            raise ValueError('Invalid port or conflicting action.')
        nft, ip_tool, ss_tool = (shutil.which(name, path='/usr/sbin:/usr/bin:/sbin:/bin') for name in ('nft', 'ip', 'ss'))
        if not all((nft, ip_tool, ss_tool)):
            raise ValueError('nft, ip and ss must be installed on this server.')
        if args.plan.stat().st_size > 8192:
            raise ValueError('Plan is too large.')
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
        for network in args.protect:
            ipaddress.ip_network(network, strict=False)
        # Serialize helpers on this host. No application or collector credentials used.
        import fcntl
        lockfd = os.open('/run/anvaya-ssh-response.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lockfd, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.unblock:
                if not isinstance(plan, dict) or not re.fullmatch(r'[a-f0-9]{32}', plan.get('plan_id', '')):
                    raise ValueError('Invalid plan ID.')
                if plan.get('device') != socket.gethostname():
                    raise ValueError('Wrong server.')
                table = table_name(plan)
                print(f'Remove ANVAYA table {table} on {socket.gethostname()}.')
                if input('Type UNBLOCK to approve: ') != 'UNBLOCK':
                    raise ValueError('Cancelled.')
                run([nft, 'delete', 'table', 'inet', table])
                print('Block table removed. Other firewall rules were not changed.')
                return 0
            protected = protections(ip_tool, ss_tool, args.port, args.protect)
            address = validate_plan(plan, socket.gethostname(), protected)
            script = rules(plan, address, args.port)
            # Limit leftover empty tables; avoid an unbounded chain per user action.
            tables = json.loads(run([nft, '-j', 'list', 'tables']))
            if sum(item.get('table', {}).get('name', '').startswith('anvaya_ssh_') for item in tables['nftables']) >= 32:
                raise ValueError('32 ANVAYA tables already exist. Remove old plans with --unblock before adding more.')
            run([nft, '--check', '-f', '-'], script)
            print(f'PREVIEW: block NEW TCP/{args.port} connections from {address} on {socket.gethostname()} for {plan["minutes"]} minutes.')
            print('Existing sessions remain open. This is not eviction of an attacker already logged in.')
            print('Kernel expiry does not require ANVAYA to stay online. Do not persist these temporary rules across reboot.')
            if not args.apply:
                print('Preview only. No firewall change. Repeat with --apply to approve.')
                return 0
            if input(f'Type the full source IP {address} to approve: ').strip() != str(address):
                raise ValueError('Cancelled; IP confirmation did not match.')
            validate_plan(plan, socket.gethostname(), protections(ip_tool, ss_tool, args.port, args.protect))
            run([nft, '-f', '-'], script)
            print(f'APPLIED: {address} for {plan["minutes"]} minutes. Table: {table_name(plan)}')
            print('For early removal, repeat this command with --unblock instead of --apply.')
            # Record on host, not falsely as a console-confirmed action.
            logger = shutil.which('logger', path='/usr/bin:/bin')
            if logger:
                try:
                    subprocess.run([logger, '-t', 'anvaya-response', '--', f'applied plan={plan["plan_id"]} source={address} port={args.port} minutes={plan["minutes"]}'], timeout=5, check=False)
                except (OSError, subprocess.SubprocessError):
                    print('Block applied, but journal audit delivery failed. Retain this terminal output.')
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, EOFError, subprocess.SubprocessError) as error:
        print(f'Stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

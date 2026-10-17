# Temporary SSH response: approve on the affected server

This pilot supports an operator-approved block of **new SSH connections from one
public IP**, for **5 or 15 minutes**. It is not automatic containment. Existing
sessions stay open, other ports are unaffected, and an attacker already logged
in is not evicted. Investigate that separately. Windows and SSH forwarded into
containers are not supported by this host-input helper.

## Prepare a plan

1. Open the SSH incident and inspect its original evidence. Check that the source
   is not your own address, a shared office/VPN address, or a legitimate user.
2. Save the assessment as **Suspicious** with the investigation open. Demo,
   controlled-test and synthetic-lab findings cannot generate a plan.
3. In **Temporary SSH response**, choose the affected device and duration.
4. Click **Prepare block plan**, then **Download plan**. This records preparation
   in the server audit trail; **nothing is blocked yet**. Plans expire ten minutes
   after preparation. Do not relabel your earlier management-IP test as malicious.

## Install the helper once

Use a reviewed copy of `collectors/ssh_response.py` on the monitored Ubuntu host.
It uses Python's standard library, `nft`, `ip` and `ss`. Ubuntu packages are
`python3`, `nftables` and `iproute2`; install missing packages using the normal
system package manager. Installing these packages does not require enabling
the nftables service or replacing `/etc/nftables.conf`.

For this project's EC2 deployment, from PowerShell in the project directory:

```powershell
scp -i "..\PEM KEY\ANVAYA-SERVER.pem" .\collectors\ssh_response.py ubuntu@15.135.87.178:~/ssh_response.py
```

## Transfer and preview a fresh plan

Transfer only to the **affected device**. If your browser saved the plan under
Downloads, run this in Windows PowerShell (adjust the filename if needed):

```powershell
scp -i "..\PEM KEY\ANVAYA-SERVER.pem" "$env:USERPROFILE\Downloads\anvaya-block-plan.json" ubuntu@15.135.87.178:~/anvaya-block-plan.json
ssh -i "..\PEM KEY\ANVAYA-SERVER.pem" ubuntu@15.135.87.178
```

Now **inside the SSH session on the Ubuntu server**, identify your management IP:

```bash
echo "$SSH_CONNECTION"
```

The first value is your current SSH client address. Substitute that address for
`YOUR_MANAGEMENT_IP` below. Add more `--protect IP_OR_CIDR` options for other
administrators, VPN exits and management ranges. The helper also checks active
SSH client addresses and local interface addresses immediately before applying.

```bash
sudo python3 ~/ssh_response.py ~/anvaya-block-plan.json --protect YOUR_MANAGEMENT_IP
```

This validates the host, IP, expiry, protection list and nftables transaction.
It prints a preview without changing firewall rules. For an SSH port other
than 22, add `--port YOUR_ACTUAL_SSH_PORT` to both preview and apply commands.

## Approve, verify, undo

After reviewing the preview, repeat with `--apply`:

```bash
sudo python3 ~/ssh_response.py ~/anvaya-block-plan.json --protect YOUR_MANAGEMENT_IP --apply
```

Type the exact source IP when prompted. The helper adds a dedicated
`anvaya_ssh_<plan_id>` table in one nftables transaction; it never flushes or
replaces existing firewall rules. If the plan is stale, prepare a new one.
Retain the terminal's APPLIED output. Review the table with:

```bash
sudo nft list table inet anvaya_ssh_PLAN_ID
sudo journalctl -t anvaya-response --since "10 minutes ago" --no-pager
```

Replace `PLAN_ID` with the plan's ID. The block element expires in the kernel
after the selected duration, even when ANVAYA or its helper is offline. Empty
tables remain until removed or reboot; they match nothing. Do not save these
temporary tables into a persistent firewall configuration. Reboot clears them.

For early removal or cleanup, use the same plan (it may be expired):

```bash
sudo python3 ~/ssh_response.py ~/anvaya-block-plan.json --protect YOUR_MANAGEMENT_IP --unblock
```

Type `UNBLOCK`. This removes only that plan's table. At most 32 ANVAYA tables
are allowed; clean up old ones before creating more. Other firewall rules may
still block the source after ANVAYA's rule expires or is removed.

Record the actual outcome in the incident notes. The console tracks plan
preparation only: it does not claim a block is active, expired or removed, because
this first version has no privileged response agent reporting back to it.

## Limits and safety

- Public IPv4 and IPv6 addresses only; no subnets, private, multicast or reserved
  sources. SSH safety checks reduce risk but cannot identify every legitimate
  user behind an IP. Maintain your protection list.
- Plans are plain reviewed JSON, not signed remote commands. A local administrator
  must review and approve them. Never run an unreviewed helper as root.
- Read-only collectors retain upload-only permissions. The web application does
  not receive sudo, host-network access, AWS credentials or firewall privileges.
- Test firewall behavior in an isolated network namespace. Do not test by blocking
  your own management IP or by opening EC2 SSH to the entire internet.

Implementation references: [nftables manual](https://netfilter.org/projects/nftables/manpage.html)
and [element timeouts](https://wiki.nftables.org/wiki-nftables/index.php/Element_timeouts).

"""The four sample lines of BACKEND_SCHEMA.md §4 (also written to tests/samples/*/*.log)."""
ASA = ('<166>Sep 30 2026 10:07:12 fw01 : %ASA-6-302013: Built inbound TCP connection 77801 for outside:198.51.100.9/40133 '
       '(198.51.100.9/40133) to inside:10.2.4.18/443 (10.2.4.18/443)')
EVE = ('<134>Sep 30 10:02:05 ids01 suricata[2211]: {"timestamp":"2026-09-30T10:02:05.000000+0530","flow_id":1500000000000900,'
       '"in_iface":"eth1","event_type":"alert","src_ip":"198.51.100.9","src_port":40100,"dest_ip":"10.2.4.18","dest_port":22,'
       '"proto":"TCP","alert":{"action":"allowed","gid":1,"signature_id":9000001,"rev":1,"signature":"ANVAYA-LAB SCAN Inbound '
       'TCP port sweep","category":"Attempted Information Leak","severity":2}}')
FGT = ('<185>date=2026-09-30 time=10:05:00 devname="vpn01" devid="FGVM01TM00000001" logid="0101039426" type="event" '
       'subtype="vpn" level="alert" vd="root" logdesc="SSL VPN login fail" action="ssl-login-fail" tunneltype="ssl-web" '
       'remip=198.51.100.9 user="admin" reason="sslvpn_login_permission_denied" msg="SSL VPN user login failed"')
EDGE = 'EDGE|2026-09-30 10:13:06|br01|SESSION|ALLOW|tcp|10.2.4.31|52300|203.0.113.12|443|bytes=1200|rule=R-110'

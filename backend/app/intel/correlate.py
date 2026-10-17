"""Cross-device attack correlation (TRD.md §10, FL-04)."""
import ipaddress
import json
from collections import Counter

WINDOW_MS = 10 * 60 * 1000
SSH_SUCCESS_MS = 15 * 60 * 1000
STAGES = ("recon", "credential", "access")
LABELS = {"recon": "Reconnaissance", "credential": "Credential attack", "access": "Access"}
RFC1918 = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]


def is_internal(ip: str | None) -> bool:
    try:
        return ip is not None and any(ipaddress.ip_address(ip) in n for n in RFC1918)
    except ValueError:
        return False


def windows(events: list[dict]) -> list[list[dict]]:
    """Split one attacker's time-ordered events into 10-minute windows anchored at each window's first event."""
    out: list[list[dict]] = []
    for e in events:
        if out and e["time"] <= out[-1][0]["time"] + WINDOW_MS:
            out[-1].append(e)
        else:
            out.append([e])
    return out


def stage_events(win: list[dict]) -> dict[str, list[dict]]:
    scans = [e for e in win if e["class_uid"] == 2004 and "SCAN" in (e["title"] or "")]
    denies = [e for e in win if e["class_uid"] == 4001 and e["action"] == "Denied"]
    recon = scans + (denies if len(denies) >= 10 and len({e["dst_port"] for e in denies}) >= 5 else [])
    fails = [e for e in win if e["class_uid"] == 3002 and e["status"] == "Failure"]
    access = [e for e in win if e["class_uid"] == 4001 and e["action"] == "Allowed" and e["activity_name"] == "Open"
              and is_internal(e["dst_ip"])]
    found = {"recon": recon, "credential": fails if len(fails) >= 10 else [], "access": access}
    return {s: sorted(found[s], key=lambda e: e["time"]) for s in STAGES if found[s]}


def by_first_seen(events: list[dict]) -> list[str]:
    seen: dict[str, None] = {}
    for e in sorted(events, key=lambda e: e["time"]):
        seen.setdefault(e["device"])
    return list(seen)


def evaluate(attacker: str, win: list[dict], related: list[dict] | None = None) -> dict | None:
    st = stage_events(win)
    if len(st) < 2 or is_internal(attacker):
        failures = [e for e in win if e.get('format') == 'openssh-journal' and e['status'] == 'Failure']
        # Invalid-user and Failed-publickey messages can describe one connection.
        unique = {}
        for event in failures:
            unique.setdefault((event['device'], event['src_ip'], event['src_port']), event)
        failures = list(unique.values())
        counts = Counter(e['device'] for e in failures)
        failures = [e for e in failures if counts[e['device']] >= 10]
        if not failures:
            return None
        successes = []
        for device in by_first_seen(failures):
            device_failures = sorted((e for e in failures if e['device'] == device), key=lambda e: e['time'])
            threshold_at, last_at = device_failures[9]['time'], device_failures[-1]['time']
            successes.extend(e for e in (related if related is not None else win)
                             if e.get('format') == 'openssh-journal' and e['status'] == 'Success'
                             and e['device'] == device and e['src_ip'] == attacker
                             and threshold_at < e['time'] <= last_at + SSH_SUCCESS_MS)
        successes.sort(key=lambda e: e['time'])
        devices = by_first_seen(failures)
        stages = {'credential': failures}
        if successes:
            stages['access'] = successes
        return {'attacker_ip': attacker, 'target_ip': None, 'window_start': win[0]['time'],
                'title': f"SSH login after repeated failures: {attacker}" if successes else f"Repeated SSH login failures: {attacker}",
                'stages': list(stages), 'devices': devices, 'risk': 75 if successes else 40,
                'level': 'High' if successes else 'Medium',
                'risk_breakdown': {'stages': 75 if successes else 40, 'devices': 0, 'ordered': 0},
                'first_time': failures[0]['time'], 'last_time': max(e['time'] for e in failures + successes),
                '_stage_events': stages}
    contributing = [e for es in st.values() for e in es]
    devices = by_first_seen(contributing)
    firsts = [st[s][0]["time"] for s in STAGES if s in st]
    ordered = int(firsts == sorted(firsts))
    breakdown = {"stages": 25 * len(st), "devices": 5 * (len(devices) - 1), "ordered": 10 * ordered}
    risk = min(100, sum(breakdown.values()))
    targets = Counter(e["dst_ip"] for e in win if is_internal(e["dst_ip"]))
    target = targets.most_common(1)[0][0] if targets else None
    return {"attacker_ip": attacker, "target_ip": target, "window_start": win[0]["time"],
            "title": f"Coordinated intrusion attempt: {attacker} → {target}", "stages": list(st), "devices": devices,
            "risk": risk, "level": "High" if risk >= 70 else "Medium" if risk >= 40 else "Low",
            "risk_breakdown": breakdown, "first_time": min(e["time"] for e in contributing),
            "last_time": max(e["time"] for e in contributing), "_stage_events": st}


def headline(stage: str, es: list[dict], attacker: str, target: str | None) -> str:
    if stage == "recon":
        denies = [e for e in es if e["class_uid"] == 4001]
        scans = len(es) - len(denies)
        parts = []
        if denies:
            parts.append(f"Port sweep of {len({e['dst_port'] for e in denies})} ports on {target}")
        if scans:
            parts.append(f"{scans} IDS scan alert{'s' if scans != 1 else ''}")
        return "; ".join(parts)
    if stage == "credential":
        users = list(dict.fromkeys(e["user_name"] for e in es if e["user_name"]))
        formats = {e.get('format') for e in es}
        protocol = 'SSH' if formats == {'openssh-journal'} else 'VPN' if formats == {'fortigate-kv'} else 'authentication'
        return f"{len(es)} failed {protocol} logins from {attacker} ({', '.join(users)})"
    e = es[0]
    if all(e.get('format') == 'openssh-journal' for e in es):
        return f"{len(es)} successful SSH login(s) from {attacker} after repeated failures; review whether authorized"
    return f"Firewall allowed {attacker} → {e['dst_ip']}:{e['dst_port']}"


class Correlator:
    def __init__(self, repo, publish, notify=lambda summary, stages: None):
        self.repo, self.publish, self.notify = repo, publish, notify

    def on_batch(self, events) -> None:
        attackers = {ip for ev in events if (ip := _src(ev)) and _stage_relevant(ev.ocsf)}
        for ip in sorted(attackers):
            related = self.repo.events_from_src(ip)
            for win in windows(related):
                inc = evaluate(ip, win, related)
                if inc:
                    self._upsert(inc)

    def _upsert(self, inc: dict) -> None:
        st = inc.pop("_stage_events")
        before = self.repo.incident_by_key(inc["attacker_ip"], inc["window_start"])
        # Late/out-of-order SSH logs can shift an anchored window. Reuse a finding
        # with the same failed evidence so its review state and alert IDs survive.
        credential_ids = [e['event_id'] for e in st.get('credential', []) if e.get('format') == 'openssh-journal']
        if before is None and credential_ids:
            placeholders = ','.join('?' for _ in credential_ids)
            before = self.repo.con.execute(
                f'SELECT i.* FROM incidents i JOIN incident_events e USING(incident_id) '
                f'WHERE i.attacker_ip=? AND e.event_id IN ({placeholders}) '
                'GROUP BY i.incident_id ORDER BY COUNT(*) DESC, i.first_time LIMIT 1',
                [inc['attacker_ip'], *credential_ids]).fetchone()
            if before:
                inc['window_start'] = before['window_start']
        prior_count = self.repo.incident_summary(before["incident_id"])["event_count"] if before else 0
        row = {**inc, **{k: json.dumps(inc[k], separators=(",", ":")) for k in ("stages", "devices", "risk_breakdown")}}
        with self.repo.tx():
            iid = self.repo.upsert_incident(row, [(e["event_id"], s) for s, es in st.items() for e in es])
        summary = self.summary(iid)
        self.notify(summary, st)
        if before is None:
            self.publish("incident.opened", summary)
        elif (json.loads(before["stages"]) != inc["stages"] or before["risk"] != inc["risk"]
              or (all(e.get('format') == 'openssh-journal' for es in st.values() for e in es)
                  and prior_count != summary['event_count'])):
            self.publish("incident.updated", summary)

    def summary(self, iid: str) -> dict:
        d = self.repo.incident_summary(iid)
        return {k: d[k] for k in ("incident_id", "title", "attacker_ip", "target_ip", "risk", "level", "stages",
                                  "devices", "event_count", "first_time", "last_time", "status", "workflow")}

    def detail(self, iid: str) -> dict | None:
        d = self.repo.incident_summary(iid)
        if not d:
            return None
        rows = self.repo.incident_events(iid)
        stages = []
        for s in d["stages"]:
            es = [r for r in rows if r["stage"] == s]
            stages.append({"stage": s, "label": LABELS[s], "first_time": es[0]["time"], "last_time": es[-1]["time"],
                           "devices": by_first_seen(es), "event_count": len(es),
                           "headline": headline(s, es, d["attacker_ip"], d["target_ip"]),
                           "event_ids": [r["event_id"] for r in es]})
        ssh_only = bool(rows) and all(r.get('format') == 'openssh-journal' for r in rows)
        explanation = (
            'At least 10 distinct SSH connections failed authentication from the same source IP to the same device in a 10-minute correlation window. '
            'This may indicate password guessing, a misconfigured client or an authorized test. It does not prove a successful intrusion.'
            if ssh_only else
            'Multiple attack stages were linked by source IP and time. Review the original events before deciding whether this is an intrusion.')
        if ssh_only and 'access' in d['stages']:
            explanation += (' A successful SSH login from the same source IP to an affected device was recorded after the threshold '
                            'and within 15 minutes of the last failed connection. Shared IPs and legitimate retries can explain this; '
                            'confirm the username, authentication method, and whether the login was authorized.')
        context = []
        if ssh_only:
            failures = [e for e in rows if e['status'] == 'Failure']
            if failures:
                context = [e for e in self.repo.events_from_src(d['attacker_ip'])
                           if e.get('format') == 'openssh-journal' and e['status'] == 'Success'
                           and e['device'] in d['devices']
                           and min(r['time'] for r in failures) - WINDOW_MS <= e['time']
                           <= max(r['time'] for r in failures) + SSH_SUCCESS_MS]
        return {**self.summary(iid), "stages_detail": stages, "risk_breakdown": d["risk_breakdown"],
                'ssh_context': self.repo.summaries([e['event_id'] for e in context[:50]]),
                'ssh_context_total': len(context), 'ssh_finding': ssh_only,
                'explanation': explanation,
                'recommended_action': 'Check whether you recognize the source IP and usernames. Open the linked events to inspect raw logs and verify integrity. Review successful logins around the same time; do not block an IP solely on this finding.'}


def _stage_relevant(o: dict) -> bool:
    """Could this event satisfy a stage test (§10.3)? Other events never change an incident's stages."""
    cls = o.get("class_uid")
    if cls == 2004:
        return "SCAN" in ((o.get("finding_info") or {}).get("title") or "")
    if cls == 3002:
        return o.get("status") in {"Failure", "Success"}
    if cls == 4001:
        return o.get("action") == "Denied" or (o.get("action") == "Allowed" and o.get("activity_name") == "Open"
                                                and is_internal((o.get("dst_endpoint") or {}).get("ip")))
    return False


def _src(ev) -> str | None:
    o = ev.ocsf
    net = (o.get("evidences") or [{}])[0] if o.get("class_uid") == 2004 else o
    return (net.get("src_endpoint") or {}).get("ip")

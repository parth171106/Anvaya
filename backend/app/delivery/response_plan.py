"""Prepare operator-reviewed plans; the web service never changes a firewall."""
import ipaddress
import time
from uuid import uuid4


def prepare(c, incident_id, device, minutes, actor):
    detail = c.correlator.detail(incident_id)
    if detail is None:
        raise KeyError(incident_id)
    workflow = detail.get('workflow', {})
    if c.cfg.demo_mode or workflow.get('controlled_test') or workflow.get('assessment') != 'suspicious':
        raise ValueError('Save the assessment as Suspicious. Demo and controlled-test findings cannot create block plans.')
    if workflow.get('state') == 'resolved':
        raise ValueError('Reopen this investigation before preparing a response.')
    if not detail.get('ssh_finding') or device not in detail['devices']:
        raise ValueError('Select a device from this SSH finding.')
    if device.lower().startswith('synthetic-lab-'):
        raise ValueError('Synthetic lab devices cannot create block plans.')
    address = ipaddress.ip_address(detail['attacker_ip'])
    if not address.is_global or address.is_multicast:
        raise ValueError('Only a single public source IP is supported.')
    if minutes not in (5, 15):
        raise ValueError('Choose five or fifteen minutes.')
    now = int(time.time())
    plan = dict(version=1, plan_id=uuid4().hex, incident_id=incident_id,
                device=device, source_ip=str(address), minutes=minutes,
                created_at=now, expires_at=now + 600, action='block-new-ssh')
    c.repo.audit(now * 1000, actor, 'incident.block_plan_prepared', incident_id,
                 {'plan_id': plan['plan_id'], 'device': device, 'source_ip': str(address), 'minutes': minutes})
    return plan

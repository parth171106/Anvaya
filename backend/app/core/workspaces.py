"""Independent databases, vaults, signing keys, buses and workers for each account."""
import asyncio
from dataclasses import replace


class Workspaces:
    def __init__(self, cfg, owner, factory, start_tasks):
        self.cfg, self.factory, self.start_tasks = cfg, factory, start_tasks
        self.containers = {"owner": owner}
        self.tasks = []

    def get(self, account_id):
        # IDs come only from authenticated database rows, never from request parameters.
        if account_id not in self.containers:
            if len(account_id) != 32 or any(c not in "0123456789abcdef" for c in account_id):
                raise ValueError("Invalid workspace identifier")
            c = self.factory(replace(self.cfg, data_dir=self.cfg.data_dir / "workspaces" / account_id))
            self.containers[account_id] = c
            self.tasks.extend(self.start_tasks(c))
        return self.containers[account_id]

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for account_id, c in self.containers.items():
            if account_id != "owner":
                c.close_stores()

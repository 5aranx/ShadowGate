from __future__ import annotations

import time

import httpx

from shadowgate.agent.executor import Executor


class Poller:
    def __init__(self, executor: Executor, server_url: str, poll_interval: float = 1.0) -> None:
        self.executor = executor
        self.server_url = server_url.rstrip("/")
        self.poll_interval = poll_interval

    def poll_once(self, client: httpx.Client) -> bool:
        r = client.post(f"{self.server_url}/agent/poll", json={"agent_id": self.executor.agent_id})
        if r.status_code != 200:
            return False
        job = r.json().get("job")
        if job is None:
            return False
        result = self.executor.run(job["id"], job["action"], job.get("params", {}))
        client.post(
            f"{self.server_url}/agent/result",
            json={"job_id": job["id"], "ok": result.ok, "data": result.data, "error": result.error},
        )
        return True

    def run(self) -> None:
        with httpx.Client() as client:
            while True:
                try:
                    if not self.poll_once(client):
                        time.sleep(self.poll_interval)
                except httpx.HTTPError:
                    time.sleep(self.poll_interval)

import threading

from shadowgate.server.queue import SqlQueue


def test_concurrent_claim_exactly_once(tmp_path):
    q = SqlQueue(str(tmp_path / "q.db"))
    n_workers = 8
    n_jobs = 40
    for i in range(n_jobs):
        q.enqueue(f"job-{i}", "agent-a", "system_info", {})

    claimed: list[str] = []
    lock = threading.Lock()

    def worker():
        local_q = SqlQueue(str(tmp_path / "q.db"))
        while True:
            job = local_q.claim_next()
            if job is None:
                return
            with lock:
                claimed.append(job.id)
            local_q.complete(job.id, True, {})

    threads = [threading.Thread(target=worker) for _ in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(claimed) == n_jobs, f"expected {n_jobs} claims, got {len(claimed)}"
    assert len(set(claimed)) == n_jobs, f"duplicate claims: {len(claimed) - len(set(claimed))}"
    assert q.stats().get("done") == n_jobs

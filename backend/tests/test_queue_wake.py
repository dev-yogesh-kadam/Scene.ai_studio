"""The waits of the job queue and of the plans miss no wake (jobs.JobManager._idle, plans.PlanRunner._pause): a job
added, or ended, between a worker's look and its wait is seen at once. Each test lands that event exactly in the gap."""

import asyncio
import time

from test_plans import IMAGE, studio  # noqa: F401 (the fixture: a render that files a picture)


def test_a_job_added_between_the_workers_look_and_its_wait_is_run(studio):  # noqa: F811
    """With no job queued the render worker waited with no time limit, clearing the wake first: a job added after its
    look and before its wait stayed queued until another job came (a plan "still running" for ever)."""
    manager = studio.app.state.jobs
    db = studio.app.state.db
    real = db.aall   # the render worker reads the waiting renders in one look (jobs._place_renders)
    user = db.one("SELECT id FROM users ORDER BY id LIMIT 1")["id"]
    added = []

    async def look(sql, params=()):
        found = await real(sql, params)
        if "status = 'queued'" in sql and "NOT LIKE 'edit/%'" in sql and not found and not added:
            # a job is queued now, after the look found none and before the worker waits; its wake is delivered
            added.append(await asyncio.to_thread(manager.add, user, "late", IMAGE, {"workflow": IMAGE, "name": "late", "values": {}},
                                                 "", 10, 0))
            await asyncio.sleep(0.2)
        return found
    db.aall = look
    try:
        manager._wake()   # the waiting workers look again, through `look`
        until = time.time() + 8
        while time.time() < until and not (added and db.one("SELECT status FROM jobs WHERE id = ?", (added[0],))["status"] == "done"):
            time.sleep(0.05)
    finally:
        db.aall = real
    assert added, "the worker never looked"
    assert db.one("SELECT status FROM jobs WHERE id = ?", (added[0],))["status"] == "done"

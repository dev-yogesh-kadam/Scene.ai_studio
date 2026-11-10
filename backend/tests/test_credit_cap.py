"""The daily credit limit holds when charges come at the same moment (credits.Credits.charge): the limit is checked and
the credits taken in one transaction, with the user's row locked, so two requests on the database's threads can't both
pass a limit only one of them fits under. And Database.transaction: all of a block, or none of it."""

import threading
import time
import types

import pytest

from scene import credits as credits_module
from scene.credits import Credits, OverCap


def a_user(db, credits=1000, daily_cap=100, role="user"):
    return db.run("INSERT INTO users (email, name, password_hash, role, created, credits, daily_cap) VALUES (?, ?, 'x', ?, ?, ?, ?)",
                  ("cap{}@example.com".format(time.time_ns()), "Cap", role, time.time(), credits, daily_cap))


@pytest.fixture
def slow_spent(monkeypatch):
    """What was spent today is read, then a pause: the window in which another charge used to slip in."""
    read = Credits.spent_today

    def spent_today(self, user_id):
        found = read(self, user_id)
        time.sleep(0.3)
        return found
    monkeypatch.setattr(Credits, "spent_today", spent_today)


def at_once(*calls):
    """Run the calls on two threads at the same moment: what each returned, or the exception it raised."""
    start, results = threading.Barrier(len(calls)), [None] * len(calls)

    def run(n, call):
        start.wait()
        try:
            results[n] = call()
        except Exception as error:   # noqa: BLE001 - kept, to be looked at by the test
            results[n] = error
    threads = [threading.Thread(target=run, args=(n, call)) for n, call in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    return results


def test_two_charges_at_once_never_pass_the_daily_limit_together(database, slow_spent):
    db = database
    credits = Credits(db, types.SimpleNamespace(signup_credits=0))
    user = a_user(db, daily_cap=100)
    results = at_once(lambda: credits.charge(user, 60, "generation"), lambda: credits.charge(user, 60, "generation"))
    assert sorted(type(r).__name__ for r in results) == ["OverCap", "bool"], results
    assert True in results
    over = next(r for r in results if isinstance(r, OverCap))
    assert over.status_code == 429 and "can spend 100 in 24 hours and has spent 60" in over.detail
    assert credits.balance(user) == 940 and credits.spent_today(user) == 60
    assert db.one("SELECT COUNT(*) AS n FROM credit_events WHERE user_id = ?", (user,))["n"] == 1


def test_the_callers_way_early_check_then_charge_holds_too(database, slow_spent):
    """What the routes do (cap_problem, then charge): both early checks pass at the same moment, the charge stops one."""
    db = database
    credits = Credits(db, types.SimpleNamespace(signup_credits=0))
    user = a_user(db, daily_cap=100)

    def queue():
        if credits.cap_problem(user, 60):
            return "early no"
        return credits.charge(user, 60, "generation")
    results = at_once(queue, queue)
    assert sum(r is True for r in results) == 1, results
    assert credits.spent_today(user) == 60 and credits.balance(user) == 940


def test_charges_that_fit_together_both_pass(database, slow_spent):
    db = database
    credits = Credits(db, types.SimpleNamespace(signup_credits=0))
    user = a_user(db, daily_cap=120)
    assert at_once(lambda: credits.charge(user, 60, "generation"), lambda: credits.charge(user, 60, "generation")) == [True, True]
    assert credits.spent_today(user) == 120


def test_what_was_already_used_and_admins_are_not_capped(database):
    db = database
    credits = Credits(db, types.SimpleNamespace(signup_credits=0))
    user = a_user(db, daily_cap=50)
    with pytest.raises(OverCap):
        credits.charge(user, 60, "generation")
    assert credits.balance(user) == 1000                                    # nothing taken
    assert credits.charge(user, 60, "generation", cap=False)                # an admin's decision
    assert credits.charge_up_to(user, 30, "agent") == 30                    # tokens already used: taken anyway
    admin = a_user(db, daily_cap=10, role="admin")
    assert credits.charge(admin, 500, "generation")
    # a plan's step: checked at approval, so past the daily cap, but never more than is left of what was reserved
    plan = db.run("INSERT INTO agent_plans (user_id, steps, progress, state, created, reserved_left) "
                  "VALUES (?, '[]', '[]', 'running', 0, 10)", (user,))
    token = credits_module.PREPAID.set(plan)
    try:
        assert credits.charge(user, 5, "agent")
        with pytest.raises(OverCap):
            credits.charge(user, 50, "agent")
    finally:
        credits_module.PREPAID.reset(token)


def test_a_charge_larger_than_the_balance_takes_nothing(database):
    db = database
    credits = Credits(db, types.SimpleNamespace(signup_credits=0))
    user = a_user(db, credits=30, daily_cap=0)
    assert credits.charge(user, 40, "generation") is False
    assert credits.balance(user) == 30
    assert not db.all("SELECT 1 FROM credit_events WHERE user_id = ?", (user,))


def test_a_transaction_keeps_all_or_nothing(database):
    db = database
    user = a_user(db)
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.run("UPDATE users SET credits = 1 WHERE id = ?", (user,))
            with db.transaction():   # inside another: part of it
                db.run("INSERT INTO settings (key, value) VALUES ('tx', '1')")
            raise RuntimeError("stop")
    assert db.one("SELECT credits FROM users WHERE id = ?", (user,))["credits"] == 1000
    assert db.one("SELECT 1 FROM settings WHERE key = 'tx'") is None
    with db.transaction():
        db.run("UPDATE users SET credits = 2 WHERE id = ?", (user,))
    assert db.one("SELECT credits FROM users WHERE id = ?", (user,))["credits"] == 2


def test_a_rolled_back_transaction_does_not_leave_a_connection_showing_the_wrong_rows(database):
    """set_config inside a transaction that rolls back is undone: the connection must say whose rows again after."""
    from scene import db as storage
    db = database
    mine, theirs = a_user(db), a_user(db)
    token = storage.ACTING.set(str(mine))
    try:
        with pytest.raises(RuntimeError):
            with db.transaction():
                assert {r["id"] for r in db.all("SELECT id FROM users")} == {mine}
                raise RuntimeError("stop")
    finally:
        storage.ACTING.reset(token)
    assert {r["id"] for r in db.all("SELECT id FROM users")} == {mine, theirs}   # back to everyone's

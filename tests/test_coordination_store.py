"""Store-level tests for CoordinationStore.

These exercise the SQLite-backed store directly (no FastAPI needed), covering
task ownership, messages, advisory locks, expiry, persistence and concurrency.
"""
import gc
import threading
import warnings
from pathlib import Path

import pytest

from construct2_ai_bridge.coordination import CoordinationError, CoordinationStore


@pytest.fixture()
def store(tmp_path: Path) -> CoordinationStore:
    return CoordinationStore(tmp_path / "coordination.sqlite3")


def _status(exc: pytest.ExceptionInfo[CoordinationError]) -> int:
    return exc.value.status_code


# --- tasks -----------------------------------------------------------------

def test_create_and_filter_tasks(store: CoordinationStore) -> None:
    task = store.create_task("Parser", "Parse params", "chatgpt")
    assert task["id"].startswith("C2-") and task["status"] == "open" and task["owner"] is None
    store.claim_task(task["id"], "claude", "claude/parser")
    other = store.create_task("Docs", "", "claude")
    assert [t["id"] for t in store.list_tasks("open")] == [other["id"]]
    assert [t["id"] for t in store.list_tasks("claimed")] == [task["id"]]
    assert len(store.list_tasks()) == 2


def test_claim_is_exclusive_but_idempotent_for_owner(store: CoordinationStore) -> None:
    task = store.create_task("T", "", "local")
    first = store.claim_task(task["id"], "claude", "claude/a")
    assert first["owner"] == "claude" and first["status"] == "claimed" and first["branch"] == "claude/a"
    with pytest.raises(CoordinationError) as exc:
        store.claim_task(task["id"], "chatgpt", "chatgpt/b")
    assert _status(exc) == 409
    again = store.claim_task(task["id"], "claude")  # no branch given: keeps the existing one
    assert again["branch"] == "claude/a" and again["version"] > first["version"]


def test_claim_errors(store: CoordinationStore) -> None:
    with pytest.raises(CoordinationError) as missing:
        store.claim_task("C2-NOPE0000", "claude")
    assert _status(missing) == 404
    task = store.create_task("T", "", "claude")
    store.update_task(task["id"], "claude", "done")
    with pytest.raises(CoordinationError) as done:
        store.claim_task(task["id"], "chatgpt")
    assert _status(done) == 409


def test_update_permissions_and_version(store: CoordinationStore) -> None:
    task = store.create_task("T", "", "chatgpt")
    claimed = store.claim_task(task["id"], "claude", "claude/x")
    with pytest.raises(CoordinationError) as stranger:
        store.update_task(task["id"], "someone-else", "done")
    assert _status(stranger) == 403
    review = store.update_task(task["id"], "claude", "in_review")
    assert review["status"] == "in_review" and review["branch"] == "claude/x"
    assert review["version"] == claimed["version"] + 1
    assert store.update_task(task["id"], "chatgpt", "blocked")["status"] == "blocked"  # creator may update
    with pytest.raises(CoordinationError) as missing:
        store.update_task("C2-NOPE0000", "claude", "done")
    assert _status(missing) == 404


# --- messages --------------------------------------------------------------

def test_messages_are_ordered_filtered_and_paged(store: CoordinationStore) -> None:
    a = store.create_task("A", "", "local")
    b = store.create_task("B", "", "local")
    m1 = store.post_message("claude", "one", a["id"])
    m2 = store.post_message("chatgpt", "two", b["id"])
    m3 = store.post_message("claude", "three")
    assert [m["id"] for m in store.list_messages()] == [m1["id"], m2["id"], m3["id"]]
    assert [m["body"] for m in store.list_messages(task_id=a["id"])] == ["one"]
    assert [m["body"] for m in store.list_messages(after_id=m1["id"])] == ["two", "three"]
    assert [m["body"] for m in store.list_messages(limit=2)] == ["one", "two"]
    with pytest.raises(CoordinationError) as exc:
        store.post_message("claude", "orphan", "C2-NOPE0000")
    assert _status(exc) == 404


# --- locks -----------------------------------------------------------------

def test_lock_blocks_other_agents_and_release_requires_token(store: CoordinationStore) -> None:
    lock = store.acquire_lock("src/a.py", "claude", None, 60)
    with pytest.raises(CoordinationError) as held:
        store.acquire_lock("src/a.py", "chatgpt", None, 60)
    assert _status(held) == 409
    for agent, token in (("claude", "wrong"), ("chatgpt", lock["token"])):
        with pytest.raises(CoordinationError) as bad:
            store.release_lock("src/a.py", agent, token)
        assert _status(bad) == 409
    store.release_lock("src/a.py", "claude", lock["token"])
    assert store.list_locks() == []
    assert store.acquire_lock("src/a.py", "chatgpt", None, 60)["agent"] == "chatgpt"


def test_same_agent_reacquire_rotates_token(store: CoordinationStore) -> None:
    old = store.acquire_lock("src/a.py", "claude", None, 60)
    new = store.acquire_lock("src/a.py", "claude", None, 60)
    assert new["token"] != old["token"]
    with pytest.raises(CoordinationError):
        store.release_lock("src/a.py", "claude", old["token"])  # stale token no longer works
    store.release_lock("src/a.py", "claude", new["token"])


def test_expired_lock_is_purged_and_can_be_taken(store: CoordinationStore) -> None:
    store.acquire_lock("src/a.py", "claude", None, 0)  # expires immediately
    assert store.list_locks() == []
    store.acquire_lock("src/b.py", "claude", None, 0)
    assert store.acquire_lock("src/b.py", "chatgpt", None, 60)["agent"] == "chatgpt"


def test_data_persists_across_store_instances(tmp_path: Path) -> None:
    path = tmp_path / "persist.sqlite3"
    first = CoordinationStore(path)
    task = first.create_task("T", "d", "claude")
    first.post_message("claude", "hello", task["id"])
    lock = first.acquire_lock("src/a.py", "claude", task["id"], 600)
    second = CoordinationStore(path)
    assert second.list_tasks()[0]["id"] == task["id"]
    assert second.list_messages()[0]["body"] == "hello"
    assert second.list_locks()[0]["token"] == lock["token"]


# --- concurrency -----------------------------------------------------------

def _race(count: int, action) -> tuple[list[object], list[CoordinationError]]:
    wins: list[object] = []
    losses: list[CoordinationError] = []
    unexpected: list[BaseException] = []
    barrier = threading.Barrier(count)

    def run(index: int) -> None:
        barrier.wait()
        try:
            wins.append(action(index))
        except CoordinationError as exc:
            losses.append(exc)
        except BaseException as exc:  # e.g. sqlite "database is locked"
            unexpected.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not unexpected, unexpected
    return wins, losses


def test_concurrent_claims_have_exactly_one_winner(store: CoordinationStore) -> None:
    task = store.create_task("T", "", "local")
    wins, losses = _race(8, lambda i: store.claim_task(task["id"], f"agent{i}", f"branch{i}"))
    assert len(wins) == 1 and len(losses) == 7
    assert all(exc.status_code == 409 for exc in losses)
    assert store.list_tasks()[0]["owner"] == wins[0]["owner"]


def test_concurrent_lock_acquires_have_exactly_one_winner(store: CoordinationStore) -> None:
    wins, losses = _race(8, lambda i: store.acquire_lock("src/a.py", f"agent{i}", None, 60))
    assert len(wins) == 1 and len(losses) == 7
    assert store.list_locks()[0]["agent"] == wins[0]["agent"]


def test_concurrent_messages_all_land_with_unique_ids(store: CoordinationStore) -> None:
    wins, losses = _race(12, lambda i: store.post_message(f"agent{i}", f"msg{i}"))
    assert len(wins) == 12 and not losses
    ids = [m["id"] for m in store.list_messages(limit=100)]
    assert len(ids) == len(set(ids)) == 12


# --- resource handling -----------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="Known issue: CoordinationStore._connect() connections are used with `with` (which "
    "commits but does not close), so every call leaves an unclosed connection until GC. "
    "Remove this marker once the store closes its connections.",
)
def test_operations_do_not_leak_open_sqlite_connections(tmp_path: Path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        local = CoordinationStore(tmp_path / "leak.sqlite3")
        task = local.create_task("T", "", "claude")
        local.claim_task(task["id"], "claude")
        local.post_message("claude", "hi", task["id"])
        local.acquire_lock("src/a.py", "claude", None, 60)
        local.list_tasks(), local.list_messages(), local.list_locks()
        gc.collect()
    leaks = [str(w.message) for w in caught if issubclass(w.category, ResourceWarning)]
    assert not leaks, leaks

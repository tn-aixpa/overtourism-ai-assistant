import os

import pytest

from app.agent import memory
from app.agent.state import AgentState


@pytest.fixture(autouse=True)
def _clean_store():
    """The store is a module-level dict — isolate tests from each other."""
    memory._STATE_STORE.clear()
    memory._LOCKS.clear()
    yield
    memory._STATE_STORE.clear()
    memory._LOCKS.clear()


class TestLoadState:
    def test_load_missing_session_returns_none(self):
        assert memory.load_state("nonexistent") is None

    def test_load_state_with_falsy_session_id_returns_none(self):
        assert memory.load_state(None) is None
        assert memory.load_state("") is None

    def test_load_returns_previously_saved_state(self, tmp_path):
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            state = AgentState(session_id="abc")
            memory.save_state(state)
            loaded = memory.load_state("abc")
        finally:
            os.chdir(cwd)
        assert loaded is state


class TestSaveState:
    def test_save_requires_session_id(self):
        state = AgentState(session_id="")
        with pytest.raises(ValueError, match="must have a session_id"):
            memory.save_state(state)

    def test_save_state_persists_and_dumps_to_file(self, tmp_path):
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            state = AgentState(session_id="s1")
            memory.save_state(state)
            assert memory.load_state("s1") is state
            assert os.path.exists("logs/state_s1.json")
        finally:
            os.chdir(cwd)


class TestDeleteState:
    def test_delete_removes_state_and_lock(self, tmp_path):
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            state = AgentState(session_id="s1")
            memory.save_state(state)
            memory._get_lock("s1")
            memory.delete_state("s1")
        finally:
            os.chdir(cwd)
        assert memory.load_state("s1") is None
        assert "s1" not in memory._LOCKS

    def test_delete_missing_session_is_noop(self):
        memory.delete_state("never-existed")  # should not raise


class TestGetLock:
    def test_returns_same_lock_for_same_session(self):
        lock1 = memory._get_lock("s1")
        lock2 = memory._get_lock("s1")
        assert lock1 is lock2

    def test_returns_different_locks_for_different_sessions(self):
        lock1 = memory._get_lock("s1")
        lock2 = memory._get_lock("s2")
        assert lock1 is not lock2


class TestRememberVsPersist:
    """remember_state is the microsecond in-memory publish (what the next
    request's load_state sees); persist_state is the slow disk copy."""

    def test_remember_state_is_visible_without_touching_the_disk(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        state = AgentState(session_id="s1")

        memory.remember_state(state)

        assert memory.load_state("s1") is state
        assert not (tmp_path / "logs").exists()

    def test_remember_state_requires_a_session_id(self):
        with pytest.raises(ValueError, match="session_id"):
            memory.remember_state(AgentState(session_id=""))

    def test_persist_state_writes_the_file_but_does_not_register_the_state(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        state = AgentState(session_id="s1")

        memory.persist_state(state)

        assert (tmp_path / "logs" / "state_s1.json").exists()
        assert memory.load_state("s1") is None

    def test_remember_replaces_the_previous_state_object(self):
        first, second = AgentState(session_id="s"), AgentState(session_id="s")

        memory.remember_state(first)
        memory.remember_state(second)

        assert memory.load_state("s") is second

    def test_sessions_are_isolated(self):
        a, b = AgentState(session_id="a"), AgentState(session_id="b")
        memory.remember_state(a)
        memory.remember_state(b)

        memory.delete_state("a")

        assert memory.load_state("a") is None
        assert memory.load_state("b") is b

    def test_persisted_state_contains_the_conversation(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        state = AgentState(session_id="s1")
        state.add_user_message("ciao mondo")

        memory.persist_state(state)

        assert "ciao mondo" in (tmp_path / "logs" / "state_s1.json").read_text()

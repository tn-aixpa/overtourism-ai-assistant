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

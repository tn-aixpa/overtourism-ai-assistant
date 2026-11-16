"""app.utils.settings: the SAVE_CONVERSATION_LOGS and LOG_LEVEL switches."""

import logging

import pytest

from app.utils import settings


class TestParseBool:
    @pytest.mark.parametrize("raw", ["true", "TRUE", " True ", "1", "t", "yes", "Y", "on"])
    def test_true_spellings(self, raw):
        assert settings.parse_bool(raw) is True

    @pytest.mark.parametrize("raw", ["false", "FALSE", "0", "f", "no", "N", "off"])
    def test_false_spellings(self, raw):
        assert settings.parse_bool(raw) is False

    @pytest.mark.parametrize("raw", [None, "", "  ", "maybe", "2", "enabled"])
    def test_unset_or_unrecognised_is_none(self, raw):
        assert settings.parse_bool(raw) is None


class TestSaveConversationLogs:
    def test_default_is_disabled(self):
        assert settings.DEFAULT_SAVE_CONVERSATION_LOGS is False
        assert settings.save_conversation_logs_enabled() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
    def test_enabled(self, monkeypatch, value):
        monkeypatch.setenv("SAVE_CONVERSATION_LOGS", value)
        assert settings.save_conversation_logs_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "garbage"])
    def test_disabled_or_unrecognised_falls_back_to_default(self, monkeypatch, value):
        monkeypatch.setenv("SAVE_CONVERSATION_LOGS", value)
        assert settings.save_conversation_logs_enabled() is False

    def test_is_read_at_call_time(self, monkeypatch):
        assert settings.save_conversation_logs_enabled() is False
        monkeypatch.setenv("SAVE_CONVERSATION_LOGS", "true")
        assert settings.save_conversation_logs_enabled() is True
        monkeypatch.setenv("SAVE_CONVERSATION_LOGS", "false")
        assert settings.save_conversation_logs_enabled() is False


class TestParseLogLevel:
    @pytest.mark.parametrize(
        "raw, level",
        [
            ("DEBUG", logging.DEBUG),
            ("info", logging.INFO),
            (" Warning ", logging.WARNING),
            ("WARN", logging.WARNING),
            ("error", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
            ("fatal", logging.CRITICAL),
        ],
    )
    def test_names_are_case_insensitive(self, raw, level):
        assert settings.parse_log_level(raw) == level

    @pytest.mark.parametrize("raw", ["verbose", "10", "trace", "", None])
    def test_invalid_raises_and_lists_the_valid_names(self, raw):
        with pytest.raises(ValueError, match="LOG_LEVEL") as exc:
            settings.parse_log_level(raw)
        for name in settings.VALID_LOG_LEVELS:
            assert name in str(exc.value)


class TestConfiguredLogLevel:
    def test_unset_is_none(self):
        assert settings.configured_log_level() is None

    def test_empty_is_none(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "  ")
        assert settings.configured_log_level() is None

    def test_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "debug")
        assert settings.configured_log_level() == logging.DEBUG

    def test_invalid_value_raises(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "loud")
        with pytest.raises(ValueError, match="loud"):
            settings.configured_log_level()

    def test_default_level_name_is_valid(self):
        assert settings.parse_log_level(settings.DEFAULT_LOG_LEVEL) == logging.INFO

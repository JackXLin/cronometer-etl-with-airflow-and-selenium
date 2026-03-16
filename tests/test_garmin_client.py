"""Tests for Garmin authentication helpers."""

import os
import sys
from pathlib import Path

import pytest

# Reason: dags/ is not a package, so we add it to sys.path for test imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import garmin_client


class TestGetGarminTokenstore:
    """Tests for Garmin token store path resolution."""

    def test_expected_use_reads_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return the configured token store path from the environment.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest environment patch helper.

        Returns:
            None
        """
        monkeypatch.setenv("GARMINTOKENS", "/tmp/garmin_tokens")

        result = garmin_client.get_garmin_tokenstore()

        assert result == Path("/tmp/garmin_tokens")


class TestLoadGarminClientFromTokens:
    """Tests for token-based Garmin client restoration."""

    def test_expected_use_restores_saved_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should instantiate Garmin and restore from the provided token store.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary directory for token files.

        Returns:
            None
        """
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        (token_dir / "session.json").write_text("{}", encoding="utf-8")
        captured = {}

        class FakeGarmin:
            """Fake Garmin client used to verify token restore."""

            def login(self, tokenstore: str) -> None:
                """Record the token store path used during login.

                Args:
                    tokenstore (str): Token store path.

                Returns:
                    None
                """
                captured["tokenstore"] = tokenstore

        monkeypatch.setattr(garmin_client, "Garmin", FakeGarmin)

        client = garmin_client.load_garmin_client_from_tokens(str(token_dir))

        assert isinstance(client, FakeGarmin)
        assert captured["tokenstore"] == str(token_dir)

    def test_missing_tokenstore_raises_bootstrap_required(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should fail clearly when no saved Garmin session exists yet.

        Args:
            tmp_path (Path): Temporary directory root.

        Returns:
            None
        """
        missing_dir = tmp_path / "missing_tokens"
        monkeypatch.setattr(garmin_client, "Garmin", object)

        with pytest.raises(garmin_client.GarminBootstrapRequiredError):
            garmin_client.load_garmin_client_from_tokens(str(missing_dir))


class TestBootstrapGarminTokens:
    """Tests for the manual Garmin bootstrap flow."""

    def test_expected_use_handles_mfa_and_persists_tokens(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should resume MFA login, dump tokens, and return verification metadata.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary directory for token output.

        Returns:
            None
        """
        token_dir = tmp_path / "tokens"
        recorded = {}

        class FakeGarth:
            """Fake garth session dumper."""

            profile = {"displayName": "tester", "fullName": "Test User"}

            def dump(self, destination: str) -> None:
                """Persist a fake token file to the requested directory.

                Args:
                    destination (str): Token directory path.

                Returns:
                    None
                """
                destination_path = Path(destination)
                destination_path.mkdir(parents=True, exist_ok=True)
                (destination_path / "oauth.json").write_text("{}", encoding="utf-8")
                recorded["dump_destination"] = destination

        class FakeGarmin:
            """Fake interactive Garmin client."""

            def __init__(
                self,
                email: str,
                password: str,
                is_cn: bool,
                return_on_mfa: bool,
            ) -> None:
                """Store constructor inputs for later verification.

                Args:
                    email (str): Garmin email.
                    password (str): Garmin password.
                    is_cn (bool): China region toggle.
                    return_on_mfa (bool): MFA behavior flag.

                Returns:
                    None
                """
                recorded["email"] = email
                recorded["password"] = password
                recorded["is_cn"] = is_cn
                recorded["return_on_mfa"] = return_on_mfa
                self.garth = FakeGarth()

            def login(self, tokenstore=None):
                """Simulate a Garmin login that requires MFA.

                Returns:
                    tuple[str, str]: MFA-required login response.
                """
                assert tokenstore is None
                assert os.getenv("GARMINTOKENS") is None
                return ("needs_mfa", "challenge-token")

            def resume_login(self, challenge: str, mfa_code: str) -> None:
                """Record the MFA challenge response.

                Args:
                    challenge (str): Challenge token.
                    mfa_code (str): MFA code entered by the user.

                Returns:
                    None
                """
                recorded["challenge"] = challenge
                recorded["mfa_code"] = mfa_code

            def get_user_summary(self, verification_date: str):
                """Return a minimal verification payload.

                Args:
                    verification_date (str): Verification date string.

                Returns:
                    dict[str, object]: Synthetic Garmin summary payload.
                """
                return {"totalSteps": 1234, "calendarDate": verification_date}

        monkeypatch.setattr(garmin_client, "Garmin", FakeGarmin)
        monkeypatch.setenv("GARMIN_EMAIL", "test@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "secret")
        monkeypatch.setattr("builtins.input", lambda _: "123456")

        result = garmin_client.bootstrap_garmin_tokens(str(token_dir))

        assert result["tokenstore"] == str(token_dir)
        assert "totalSteps" in result["verification_keys"]
        assert recorded["challenge"] == "challenge-token"
        assert recorded["mfa_code"] == "123456"
        assert recorded["dump_destination"] == str(token_dir)

    def test_missing_credentials_raise_configuration_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should fail clearly when bootstrap credentials are absent.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary directory root.

        Returns:
            None
        """
        monkeypatch.delenv("GARMIN_EMAIL", raising=False)
        monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
        monkeypatch.setattr(garmin_client, "Garmin", object)

        with pytest.raises(garmin_client.GarminConfigurationError):
            garmin_client.bootstrap_garmin_tokens(str(tmp_path / "tokens"))

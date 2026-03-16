"""Garmin Connect authentication helpers for Airflow tasks and manual bootstrap."""

import logging
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    Garmin = None

    class GarminConnectAuthenticationError(Exception):
        """Fallback auth exception when garminconnect is unavailable."""

    class GarminConnectConnectionError(Exception):
        """Fallback connection exception when garminconnect is unavailable."""

    class GarminConnectTooManyRequestsError(Exception):
        """Fallback rate-limit exception when garminconnect is unavailable."""

try:
    from garth.exc import GarthHTTPError
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    class GarthHTTPError(Exception):
        """Fallback HTTP exception when garth is unavailable."""


LOGGER = logging.getLogger(__name__)
DEFAULT_GARMIN_TOKENSTORE = "/opt/airflow/config/garmin_tokens"


class GarminConfigurationError(RuntimeError):
    """Raised when Garmin-related environment configuration is invalid."""


class GarminBootstrapRequiredError(RuntimeError):
    """Raised when a manual Garmin token bootstrap is required."""


class GarminServiceError(RuntimeError):
    """Raised when Garmin Connect cannot be reached successfully."""


class GarminRateLimitError(GarminServiceError):
    """Raised when Garmin rate limits API access."""


def _prepare_bootstrap_tokenstore(tokenstore_path: Path) -> None:
    """Prepare the tokenstore path for a fresh Garmin bootstrap login.

    Args:
        tokenstore_path (Path): Configured tokenstore directory.

    Returns:
        None
    """
    tokenstore_path.parent.mkdir(parents=True, exist_ok=True)
    if tokenstore_path.exists() and tokenstore_path.is_dir() and not any(tokenstore_path.iterdir()):
        # Reason: garminconnect treats an existing empty token directory as a
        # restorable session and fails before interactive login can begin.
        tokenstore_path.rmdir()


def _ensure_profile_loaded(client: Any) -> None:
    """Ensure the Garmin client has profile fields needed by summary endpoints.

    Args:
        client (Any): Authenticated Garmin API client.

    Returns:
        None

    Raises:
        GarminServiceError: If the user profile cannot be resolved.
    """
    if getattr(client, "display_name", None):
        return

    garth_client = getattr(client, "garth", None)
    profile = getattr(garth_client, "profile", None)
    if isinstance(profile, dict) and profile.get("displayName"):
        client.display_name = profile.get("displayName")
        client.full_name = profile.get("fullName")
        return

    connectapi = getattr(garth_client, "connectapi", None)
    if not callable(connectapi):
        raise GarminServiceError(
            "Garmin login succeeded, but the user profile could not be loaded."
        )

    try:
        profile = connectapi("/userprofile-service/userprofile/profile")
    except Exception as exc:
        raise GarminServiceError(
            "Garmin login succeeded, but the user profile could not be loaded."
        ) from exc

    if not isinstance(profile, dict) or not profile.get("displayName"):
        raise GarminServiceError(
            "Garmin login succeeded, but the user profile response was incomplete."
        )

    client.display_name = profile.get("displayName")
    client.full_name = profile.get("fullName")


def _require_garmin_library() -> None:
    """Validate that the `garminconnect` dependency is importable.

    Raises:
        GarminConfigurationError: If the dependency is unavailable.
    """
    if Garmin is None:
        raise GarminConfigurationError(
            "The `garminconnect` dependency is not installed in this Python "
            "environment. Rebuild the Airflow image or install requirements first."
        )


def get_garmin_tokenstore(tokenstore: Optional[str] = None) -> Path:
    """Resolve the Garmin token storage directory.

    Args:
        tokenstore (str | None): Optional override for the token directory.

    Returns:
        Path: Expanded Garmin token directory path.
    """
    configured_path = tokenstore or os.getenv(
        "GARMINTOKENS", DEFAULT_GARMIN_TOKENSTORE
    )
    return Path(configured_path).expanduser()


def _build_http_error(exc: Exception, fallback_message: str) -> RuntimeError:
    """Convert Garmin/Garth HTTP failures into actionable runtime errors.

    Args:
        exc (Exception): The original exception.
        fallback_message (str): Default message when no status-specific mapping exists.

    Returns:
        RuntimeError: Mapped Garmin-specific runtime error.
    """
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    error_text = str(exc)

    if status_code == 429 or "429" in error_text:
        return GarminRateLimitError(
            "Garmin rejected the request with a rate-limit response. Wait before "
            "retrying the Garmin task."
        )

    if status_code in (401, 403) or "401" in error_text or "403" in error_text:
        return GarminBootstrapRequiredError(
            "Stored Garmin authentication is invalid or expired. Run the manual "
            "Garmin bootstrap flow again to refresh tokens."
        )

    return GarminServiceError(fallback_message)


def load_garmin_client_from_tokens(tokenstore: Optional[str] = None) -> Any:
    """Create a Garmin client by restoring an existing token-based session.

    Args:
        tokenstore (str | None): Optional override for the token directory.

    Returns:
        Any: Authenticated Garmin API client.

    Raises:
        GarminBootstrapRequiredError: If no reusable token session exists.
        GarminConfigurationError: If the dependency is unavailable.
        GarminRateLimitError: If Garmin rate limits the restore attempt.
        GarminServiceError: If Garmin cannot be reached successfully.
    """
    _require_garmin_library()
    tokenstore_path = get_garmin_tokenstore(tokenstore)

    if not tokenstore_path.exists():
        raise GarminBootstrapRequiredError(
            f"Garmin token store does not exist at `{tokenstore_path}`. Run the "
            "manual bootstrap helper before enabling scheduled Garmin fetches."
        )

    if not list(tokenstore_path.glob("*.json")):
        raise GarminBootstrapRequiredError(
            f"No Garmin token files were found in `{tokenstore_path}`. Run the "
            "manual bootstrap helper before enabling scheduled Garmin fetches."
        )

    try:
        client = Garmin()
        client.login(str(tokenstore_path))
        return client
    except FileNotFoundError as exc:
        raise GarminBootstrapRequiredError(
            "Garmin token files could not be loaded from the configured token store."
        ) from exc
    except GarminConnectTooManyRequestsError as exc:
        raise GarminRateLimitError(
            "Garmin rejected the token restore due to rate limiting."
        ) from exc
    except GarminConnectAuthenticationError as exc:
        raise GarminBootstrapRequiredError(
            "Stored Garmin tokens are invalid or expired. Run the manual bootstrap "
            "helper again to refresh them."
        ) from exc
    except GarminConnectConnectionError as exc:
        raise GarminServiceError(
            "Garmin Connect could not be reached while restoring the saved session."
        ) from exc
    except GarthHTTPError as exc:
        raise _build_http_error(
            exc,
            "Garmin returned an unexpected HTTP response while restoring the saved "
            "session.",
        ) from exc


def bootstrap_garmin_tokens(tokenstore: Optional[str] = None) -> Dict[str, Any]:
    """Perform an interactive Garmin login and persist reusable tokens.

    Args:
        tokenstore (str | None): Optional override for the token directory.

    Returns:
        dict[str, Any]: Metadata about the persisted token session.

    Raises:
        GarminBootstrapRequiredError: If credentials or MFA are rejected.
        GarminConfigurationError: If required configuration is missing.
        GarminRateLimitError: If Garmin rate limits the login attempt.
        GarminServiceError: If verification fails for a non-auth reason.
    """
    _require_garmin_library()

    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        raise GarminConfigurationError(
            "`GARMIN_EMAIL` and `GARMIN_PASSWORD` must be set before running the "
            "manual Garmin bootstrap helper."
        )

    tokenstore_path = get_garmin_tokenstore(tokenstore)
    _prepare_bootstrap_tokenstore(tokenstore_path)

    try:
        client = Garmin(
            email=email,
            password=password,
            is_cn=False,
            return_on_mfa=True,
        )
        previous_tokenstore = os.environ.pop("GARMINTOKENS", None)
        try:
            login_result = client.login(tokenstore=None)
        finally:
            if previous_tokenstore is not None:
                os.environ["GARMINTOKENS"] = previous_tokenstore

        if isinstance(login_result, tuple) and login_result[0] == "needs_mfa":
            mfa_code = input("Please enter your Garmin MFA code: ").strip()
            if not mfa_code:
                raise GarminBootstrapRequiredError(
                    "Garmin MFA verification was required, but no MFA code was provided."
                )
            client.resume_login(login_result[1], mfa_code)

        client.garth.dump(str(tokenstore_path))
        _ensure_profile_loaded(client)
        verification_date = date.today().isoformat()
        verification_payload = client.get_user_summary(verification_date)
        LOGGER.info("Garmin token bootstrap verified successfully for %s.", verification_date)
        return {
            "tokenstore": str(tokenstore_path),
            "verified_date": verification_date,
            "verification_keys": sorted(list((verification_payload or {}).keys())),
        }
    except GarminConnectTooManyRequestsError as exc:
        raise GarminRateLimitError(
            "Garmin rejected the interactive login due to rate limiting. Wait before "
            "retrying the bootstrap helper."
        ) from exc
    except GarminConnectAuthenticationError as exc:
        raise GarminBootstrapRequiredError(
            "Garmin rejected the supplied credentials or MFA code during bootstrap."
        ) from exc
    except GarminConnectConnectionError as exc:
        raise GarminServiceError(
            "Garmin Connect could not be reached during the interactive bootstrap."
        ) from exc
    except GarthHTTPError as exc:
        raise _build_http_error(
            exc,
            "Garmin returned an unexpected HTTP response during bootstrap."
        ) from exc

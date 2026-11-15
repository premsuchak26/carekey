"""Centralized application domain constants.

Defines timing windows, security parameters, and shared string literals.
"""

from typing import Final, Literal

# --- Localization & Defaults ---
DEFAULT_TIMEZONE: Final[str] = "Asia/Kolkata"
DEFAULT_ELDER_EMAIL: Final[str] = "elder@carekey.local"
DEFAULT_MEMBER_EMAIL: Final[str] = "member@carekey.local"

# --- Security & Cryptography ---
UNAMBIGUOUS_CHARSET: Final[str] = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
PASSCODE_LENGTH: Final[int] = 12
SALT_BYTES_LENGTH: Final[int] = 16
SCRYPT_N: Final[int] = 16384
SCRYPT_R: Final[int] = 8
SCRYPT_P: Final[int] = 1

# --- Authentication & Lockout ---
MAX_FAILED_LOGIN_ATTEMPTS: Final[int] = 5
LOCKOUT_DURATION_MINUTES: Final[int] = 15
IP_RATE_LIMIT_MAX_ATTEMPTS: Final[int] = 10
IP_RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60
DEFAULT_SESSION_MAX_AGE_SECONDS: Final[int] = 3600  # 1 hour
DEFAULT_ACTION_TOKEN_EXPIRY_HOURS: Final[int] = 24

# --- Medication Adherence Thresholds ---
LATE_THRESHOLD_SECONDS: Final[int] = 30 * 60  # 30 minutes
MISSED_THRESHOLD_SECONDS: Final[int] = 2 * 3600  # 2 hours
ALREADY_HANDLED_WINDOW_SECONDS: Final[int] = 7200  # 2 hours

# --- Reminder Escalation Stages ---
STAGE_10M_BEFORE: Final[str] = "elder_10m_before"
STAGE_15M_LATE: Final[str] = "elder_15m_late"
STAGE_60M_MISSED: Final[str] = "caretaker_60m_missed"
STAGE_APPT_24H: Final[str] = "app_24h_before"
STAGE_APPT_2H: Final[str] = "app_2h_before"

# --- Action Token Types ---
ACTION_TOOK_IT: Final = "took_it"
ACTION_SNOOZE: Final = "snooze"
ACTION_CALL_ME: Final = "call_me"
DEFAULT_SNOOZE_MINUTES: Final[int] = 15

# --- Dose Status Literals ---
DOSE_STATUS_ON_TIME: Final = "on_time"
DOSE_STATUS_LATE: Final = "late"
DOSE_STATUS_MISSED: Final = "missed"
DOSE_STATUS_SKIPPED: Final = "skipped"
DOSE_STATUS_TAKEN: Final = "taken"

DoseAdministrationStatus = Literal["taken", "skipped"]
DosePunctualityStatus = Literal["on_time", "late", "missed", "skipped"]

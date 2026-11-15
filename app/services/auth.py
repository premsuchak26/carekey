"""Authentication and authorization service for CareKey."""

import hashlib
import hmac
import secrets
import string
import time
from datetime import datetime, timedelta

from app.config import Settings
from app.models import CareCircle, Elder, Member, MemberRole
from app.repositories import RepositoryContainer
from app.services.audit import AuditService


class AuthError(Exception):
    """Generic authentication failure with uniform error messaging."""

    def __init__(self, message: str = "Invalid circle code or passcode.") -> None:
        super().__init__(message)
        self.message = message


class AuthService:
    """Manages circle creation, scrypt key issuance, verification, and lockouts."""

    CHARSET = string.ascii_uppercase + string.digits
    LOCKOUT_THRESHOLD = 5
    LOCKOUT_DURATION_MINUTES = 15
    IP_RATE_LIMIT_WINDOW = 60  # seconds
    IP_RATE_LIMIT_MAX_ATTEMPTS = 10

    def __init__(
        self,
        repositories: RepositoryContainer,
        settings: Settings,
        audit_service: AuditService | None = None,
    ) -> None:
        self.repos = repositories
        self.settings = settings
        self.audit = audit_service or AuditService(repositories=repositories)
        self._ip_failed_attempts: dict[str, list[float]] = {}

    @classmethod
    def generate_passcode(cls, length: int = 12) -> str:
        """Generate a cryptographically secure random alphanumeric passcode."""
        return "".join(secrets.choice(cls.CHARSET) for _ in range(length))

    @classmethod
    def generate_circle_code(cls) -> str:
        """Generate a readable 6-character circle code."""
        suffix = "".join(secrets.choice(cls.CHARSET) for _ in range(4))
        return f"CARE-{suffix}"

    @classmethod
    def hash_passcode(cls, passcode: str, salt: str | None = None) -> tuple[str, str]:
        """Hash passcode with scrypt and a unique per-key salt.

        Returns:
            Tuple of (salt_hex, key_hash_hex)
        """
        if salt is None:
            salt = secrets.token_hex(16)
        salt_bytes = salt.encode("utf-8")
        passcode_bytes = passcode.encode("utf-8")

        # OpenSSL scrypt parameters (N=16384, r=8, p=1)
        derived = hashlib.scrypt(passcode_bytes, salt=salt_bytes, n=16384, r=8, p=1)
        return salt, derived.hex()

    @classmethod
    def verify_passcode(cls, passcode: str, salt: str, stored_hash: str) -> bool:
        """Verify passcode using constant-time comparison against scrypt hash."""
        try:
            _, computed_hash = cls.hash_passcode(passcode=passcode, salt=salt)
            return hmac.compare_digest(computed_hash, stored_hash)
        except Exception:
            return False

    def check_ip_rate_limit(self, client_ip: str) -> None:
        """Enforce simple per-IP rate limit on authentication attempts."""
        now = time.time()
        attempts = self._ip_failed_attempts.get(client_ip, [])
        # Prune expired timestamps
        attempts = [t for t in attempts if now - t < self.IP_RATE_LIMIT_WINDOW]
        self._ip_failed_attempts[client_ip] = attempts

        if len(attempts) >= self.IP_RATE_LIMIT_MAX_ATTEMPTS:
            raise AuthError("Too many login attempts. Please wait a minute and try again.")

    def record_ip_failure(self, client_ip: str) -> None:
        """Record a failed authentication attempt for an IP address."""
        now = time.time()
        if client_ip not in self._ip_failed_attempts:
            self._ip_failed_attempts[client_ip] = []
        self._ip_failed_attempts[client_ip].append(now)

    async def create_circle(
        self, elder_name: str, circle_name: str | None = None
    ) -> tuple[CareCircle, Elder, str]:
        """Create a new Elder profile and CareCircle, returning the owner passcode once."""
        circle_name = circle_name or f"{elder_name}'s Care Circle"

        elder = Elder(name=elder_name)
        await self.repos.elders.save(elder.id, elder)

        circle_code = self.generate_circle_code()
        circle = CareCircle(
            circle_code=circle_code,
            elder_id=elder.id,
            name=circle_name,
        )
        await self.repos.circles.save(circle.id, circle)

        # Generate single-use owner passcode for elder
        raw_passcode = self.generate_passcode(12)
        salt, key_hash = self.hash_passcode(raw_passcode)

        owner_member = Member(
            circle_id=circle.id,
            name=f"{elder_name} (Owner)",
            role=MemberRole.ELDER,
            key_hash=key_hash,
            salt=salt,
            expires_at=None,  # Owner passcodes do not expire
        )
        await self.repos.members.save(owner_member.id, owner_member)

        return circle, elder, raw_passcode

    async def issue_member_key(
        self,
        circle_id: str,
        name: str,
        role: MemberRole,
        validity_days: int = 30,
        actor_name: str = "Elder",
    ) -> tuple[Member, str]:
        """Issue a new random 12-character member key with scrypt hash and expiration."""
        raw_passcode = self.generate_passcode(12)
        salt, key_hash = self.hash_passcode(raw_passcode)
        expires_at = datetime.now() + timedelta(days=validity_days)

        member = Member(
            circle_id=circle_id,
            name=name,
            role=role,
            key_hash=key_hash,
            salt=salt,
            expires_at=expires_at,
        )
        await self.repos.members.save(member.id, member)

        circle = await self.repos.circles.get(circle_id)
        elder_id = circle.elder_id if circle else ""
        # Audit key issuance - PASSCODES ARE NEVER LOGGED
        await self.audit.log_event(
            elder_id=elder_id,
            circle_id=circle_id,
            actor=actor_name,
            action="key.issue",
            target=name,
            details={"member_name": name, "role": role.value, "validity_days": validity_days},
        )

        return member, raw_passcode

    async def revoke_member_key(
        self, circle_id: str, member_id: str, actor_name: str = "Elder"
    ) -> bool:
        """Instantly revoke a member key."""
        member = await self.repos.members.get(member_id)
        if not member or member.circle_id != circle_id:
            return False
        member.revoked_at = datetime.now()
        await self.repos.members.save(member.id, member)

        circle = await self.repos.circles.get(circle_id)
        elder_id = circle.elder_id if circle else ""
        # Audit key revocation
        await self.audit.log_event(
            elder_id=elder_id,
            circle_id=circle_id,
            actor=actor_name,
            action="key.revoke",
            target=member.name,
            details={"member_name": member.name, "role": member.role.value},
        )
        return True

    async def login(
        self, circle_code: str, passcode: str, client_ip: str = "127.0.0.1"
    ) -> tuple[CareCircle, Member]:
        """Authenticate with circle code and passcode.

        Enforces IP rate limit, constant-time scrypt check, generic errors, and 15-min lockout.
        """
        self.check_ip_rate_limit(client_ip)

        clean_code = circle_code.strip().upper()
        clean_passcode = passcode.strip()

        # Find circle by circle_code
        matching_circles = await self.repos.circles.find(
            lambda c: c.circle_code.upper() == clean_code
        )
        if not matching_circles:
            self.record_ip_failure(client_ip)
            # Perform dummy scrypt hash to prevent timing attacks on circle existence
            _ = self.hash_passcode(clean_passcode, salt="0" * 32)
            raise AuthError("Invalid circle code or passcode.")

        circle = matching_circles[0]
        circle_members = await self.repos.members.find(lambda m: m.circle_id == circle.id)

        now = datetime.now()

        # Check all members in the circle using constant time comparison
        authenticated_member: Member | None = None
        target_locked: bool = False

        for member in circle_members:
            # Check if currently locked out
            if member.locked_until and now < member.locked_until:
                # Still check hash to avoid timing leak, but mark locked
                _ = self.verify_passcode(clean_passcode, member.salt, member.key_hash)
                target_locked = True
                continue

            # Check expiration or revocation
            if member.revoked_at or (member.expires_at and now > member.expires_at):
                # Expired or revoked - verify hash for constant timing, but do not authenticate
                _ = self.verify_passcode(clean_passcode, member.salt, member.key_hash)
                continue

            if self.verify_passcode(clean_passcode, member.salt, member.key_hash):
                authenticated_member = member
                break

        if target_locked and not authenticated_member:
            self.record_ip_failure(client_ip)
            raise AuthError(
                "Account temporarily locked due to multiple failed attempts. "
                "Try again in 15 minutes."
            )

        if not authenticated_member:
            # Increment failed attempts on all active members in this circle
            self.record_ip_failure(client_ip)
            for m in circle_members:
                if not m.revoked_at and (not m.expires_at or now <= m.expires_at):
                    m.failed_attempts += 1
                    if m.failed_attempts >= self.LOCKOUT_THRESHOLD:
                        m.locked_until = now + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)
                    await self.repos.members.save(m.id, m)

            # Audit failed login attempt (PASSCODES ARE NEVER LOGGED)
            await self.audit.log_event(
                elder_id=circle.elder_id,
                circle_id=circle.id,
                actor=f"Unrecognized ({client_ip})",
                action="auth.login_failed",
                target=clean_code,
                details={"client_ip": client_ip, "reason": "Failed authentication"},
            )
            raise AuthError("Invalid circle code or passcode.")

        # Success: reset failed attempts
        authenticated_member.failed_attempts = 0
        authenticated_member.locked_until = None
        await self.repos.members.save(authenticated_member.id, authenticated_member)

        # Audit successful login
        await self.audit.log_event(
            elder_id=circle.elder_id,
            circle_id=circle.id,
            actor=authenticated_member.name,
            action="auth.login",
            target=clean_code,
            details={"role": authenticated_member.role.value, "client_ip": client_ip},
        )

        return circle, authenticated_member

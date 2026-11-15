"""Tests for email sender protocol and fake sender."""

import pytest

from app.services.email import FakeEmailSender


@pytest.mark.asyncio
async def test_fake_email_sender():
    sender = FakeEmailSender()
    assert len(sender.sent_emails) == 0

    success = await sender.send_email(
        to="elder@carekey.local",
        subject="Medication Reminder",
        text_body="Time to take Metformin",
        html_body="<p>Time to take Metformin</p>",
    )
    assert success is True
    assert len(sender.sent_emails) == 1
    assert sender.sent_emails[0]["to"] == "elder@carekey.local"
    assert sender.sent_emails[0]["subject"] == "Medication Reminder"
    assert "Metformin" in sender.sent_emails[0]["text_body"]
    assert "<p>" in sender.sent_emails[0]["html_body"]

    # Filter emails
    elder_emails = sender.get_emails_for("elder@carekey.local")
    assert len(elder_emails) == 1

    other_emails = sender.get_emails_for("other@carekey.local")
    assert len(other_emails) == 0

    # Clear
    sender.clear()
    assert len(sender.sent_emails) == 0

"""Unit tests for the Two-Key Rule risk scoring pure function."""

from app.models import Medication, RiskLevel
from app.services.proposals import risk_score


def test_risk_rule_new_medication() -> None:
    """Adding a brand new medication yields at least MEDIUM risk with plain language reason."""
    before = None
    after = {
        "name": "Metformin",
        "dosage": "500mg",
        "schedule": {"times_of_day": ["08:00"], "max_doses_per_day": 1},
    }
    risk, reasons = risk_score(before=before, after=after)
    assert risk == RiskLevel.MEDIUM
    assert any("New medication" in r for r in reasons)


def test_risk_rule_dose_increase_over_1_point_5x() -> None:
    """Increasing dose over 1.5x triggers HIGH risk with threshold details."""
    before = {"name": "Lisinopril", "dosage": "10mg"}
    after = {"name": "Lisinopril", "dosage": "20mg"}  # 2.0x increase
    risk, reasons = risk_score(before=before, after=after)
    assert risk == RiskLevel.HIGH
    assert any("1.5x" in r for r in reasons)


def test_risk_rule_dose_increase_under_1_point_5x() -> None:
    """Dose increase within 1.5x (e.g. 10mg -> 12.5mg) does not trigger 1.5x rule."""
    before = {"name": "Lisinopril", "dosage": "10mg"}
    after = {"name": "Lisinopril", "dosage": "12.5mg"}  # 1.25x increase
    risk, reasons = risk_score(before=before, after=after)
    assert risk == RiskLevel.LOW
    assert not any("1.5x" in r for r in reasons)


def test_risk_rule_duplicate_active_ingredient() -> None:
    """Prescribing medication with same active ingredient as an existing one triggers HIGH risk."""
    existing = [
        Medication(
            id="med-1",
            circle_id="circle-1",
            name="Tylenol 500mg",
            dosage="500mg",
        )
    ]
    # Adding Panadol which also has active ingredient acetaminophen
    after = {
        "name": "Panadol Extra",
        "dosage": "500mg",
        "schedule": {"times_of_day": ["08:00"], "max_doses_per_day": 1},
    }
    risk, reasons = risk_score(before=None, after=after, existing_medications=existing)
    assert risk == RiskLevel.HIGH
    assert any("Duplicate active ingredient" in r for r in reasons)
    assert any("acetaminophen" in r.lower() for r in reasons)


def test_risk_rule_exceeds_daily_maximum() -> None:
    """Exceeding recommended daily maximum limit for active ingredient triggers HIGH risk."""
    # Acetaminophen max is 4000mg. 1000mg x 5 times/day = 5000mg
    after = {
        "name": "Acetaminophen",
        "dosage": "1000mg",
        "schedule": {
            "times_of_day": ["08:00", "12:00", "16:00", "20:00", "23:00"],
            "max_doses_per_day": 5,
        },
    }
    risk, reasons = risk_score(before=None, after=after)
    assert risk == RiskLevel.HIGH
    assert any("exceeds recommended daily maximum" in r.lower() for r in reasons)


def test_risk_rule_more_doses_per_day_than_allowed() -> None:
    """Scheduling more doses than allowed by max_doses_per_day triggers HIGH risk."""
    after = {
        "name": "Atorvastatin",
        "dosage": "20mg",
        "schedule": {
            "times_of_day": ["08:00", "14:00", "20:00"],  # 3 times
            "max_doses_per_day": 2,  # allowed 2
        },
    }
    risk, reasons = risk_score(before=None, after=after)
    assert risk == RiskLevel.HIGH
    assert any("More doses per day" in r for r in reasons)


def test_risk_rule_medication_removal() -> None:
    """Medication deletion or removal yields MEDIUM risk."""
    before = {"id": "med-1", "name": "Aspirin", "dosage": "81mg"}
    after = None
    risk, reasons = risk_score(before=before, after=after)
    assert risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)
    assert any("Medication removal" in r for r in reasons)


def test_risk_rule_minor_routine_adjustment() -> None:
    """Updating non-critical details (e.g. instructions) is scored LOW risk."""
    before = {
        "id": "med-1",
        "name": "Amlodipine",
        "dosage": "5mg",
        "instructions": "Take with water",
    }
    after = {
        "id": "med-1",
        "name": "Amlodipine",
        "dosage": "5mg",
        "instructions": "Take with water after breakfast",
    }
    risk, reasons = risk_score(before=before, after=after)
    assert risk == RiskLevel.LOW
    assert any("Routine" in r for r in reasons)

from enum import Enum
import re

from pydantic import BaseModel

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"

class RiskReport(BaseModel):
    level: RiskLevel
    reasons: list[str]

HIGH_RISK_PATTERNS = [
    "subprocess",
    "os.system",
    "shell=True",
    "pip install",
    "requests.",
    "http://",
    "https://",
    "socket",
    "chmod",
    "chown",
    "rm -rf",
    "shutil.rmtree",
]

BLOCKED_PATTERNS = [
    "steal",
    "exfiltrate",
    "keylogger",
    "persistence",
    "disable antivirus",
    "credential",
    "password dump",
]

BLOCKED_NORMALIZED_PHRASES = [
    "key logger",
    "keystroke recorder",
]

MEDIUM_RISK_PATTERNS = [
    "open(",
    "sqlite3",
    "Path(",
    "os.listdir",
    "glob",
    "hashlib",
]

def normalize_keyword_text(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value).lower())
    return " ".join(text.split())

def contains_normalized_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "

def classify_text(text: str) -> RiskReport:
    lowered = text.lower()
    normalized = normalize_keyword_text(text)
    reasons = []

    for pattern in BLOCKED_PATTERNS:
        if pattern in lowered:
            reasons.append(f"Blocked pattern detected: {pattern}")

    for phrase in BLOCKED_NORMALIZED_PHRASES:
        if contains_normalized_phrase(normalized, phrase):
            reasons.append(f"Blocked normalized phrase detected: {phrase}")

    if reasons:
        return RiskReport(level=RiskLevel.BLOCKED, reasons=reasons)

    for pattern in HIGH_RISK_PATTERNS:
        if pattern.lower() in lowered:
            reasons.append(f"High-risk pattern detected: {pattern}")

    if reasons:
        return RiskReport(level=RiskLevel.HIGH, reasons=reasons)

    for pattern in MEDIUM_RISK_PATTERNS:
        if pattern.lower() in lowered:
            reasons.append(f"Medium-risk pattern detected: {pattern}")

    if reasons:
        return RiskReport(level=RiskLevel.MEDIUM, reasons=reasons)

    return RiskReport(level=RiskLevel.LOW, reasons=["No elevated-risk patterns detected."])

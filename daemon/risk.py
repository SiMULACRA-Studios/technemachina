from enum import Enum
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

MEDIUM_RISK_PATTERNS = [
    "open(",
    "sqlite3",
    "Path(",
    "os.listdir",
    "glob",
    "hashlib",
]

def classify_text(text: str) -> RiskReport:
    lowered = text.lower()
    reasons = []

    for pattern in BLOCKED_PATTERNS:
        if pattern in lowered:
            reasons.append(f"Blocked pattern detected: {pattern}")

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

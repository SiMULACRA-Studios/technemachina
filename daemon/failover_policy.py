"""
Restriction-Aware Failover Policy for Technemachina Daemon.

Purpose:
- Technical/provider failures should trigger automatic fallback.
- Obvious provider false-positives on allowed tasks may trigger fallback.
- Confirmed unsafe requests should not be provider-shopped.
"""

import re


TECHNICAL_FAILURE_KEYWORDS = [
    "503",
    "502",
    "500",
    "429",
    "402",
    "401",
    "timeout",
    "timed out",
    "rate limit",
    "rate_limit",
    "quota",
    "overloaded",
    "unavailable",
    "network error",
    "server error",
    "internal error",
    "empty content",
    "invalid json",
    "missing content",
    "capacity",
    "high demand",
]

PROVIDER_REFUSAL_KEYWORDS = [
    "i can't assist",
    "i cannot assist",
    "i can’t help",
    "i cannot help",
    "i'm sorry, but i can't",
    "i’m sorry, but i can’t",
    "i can't provide",
    "i cannot provide",
    "not able to help with that",
    "against my policy",
    "safety policy",
    "disallowed",
]

CONFIRMED_UNSAFE_KEYWORDS = [
    "steal credentials",
    "phishing kit",
    "malware",
    "ransomware",
    "keylogger",
    "credential theft",
    "exfiltrate",
    "bypass authentication",
    "unauthorized access",
    "destroy hardware",
    "explosive",
    "poison",
]


CONFIRMED_UNSAFE_NORMALIZED_PHRASES = [
    "key logger",
    "keystroke recorder",
]


def normalize_keyword_text(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value).lower())
    return " ".join(text.split())


def contains_normalized_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def classify_failure(error_text: str) -> str:
    """
    Classify provider failure text.

    Returns:
    - technical_failure
    - provider_refusal_uncertain
    - unknown_failure
    """
    text = str(error_text).lower()

    if any(keyword in text for keyword in TECHNICAL_FAILURE_KEYWORDS):
        return "technical_failure"

    if any(keyword in text for keyword in PROVIDER_REFUSAL_KEYWORDS):
        return "provider_refusal_uncertain"

    return "unknown_failure"


def classify_user_request(prompt: str) -> str:
    """
    Lightweight request classifier.

    This is not the final safety system.
    It prevents obvious provider-shopping for clearly unsafe requests.
    """
    text = str(prompt).lower()
    normalized_text = normalize_keyword_text(prompt)

    if any(keyword in text for keyword in CONFIRMED_UNSAFE_KEYWORDS):
        return "confirmed_unsafe"

    if any(
        contains_normalized_phrase(normalized_text, phrase)
        for phrase in CONFIRMED_UNSAFE_NORMALIZED_PHRASES
    ):
        return "confirmed_unsafe"

    return "allowed_or_unclear"


def should_try_next_provider(prompt: str, error_text: str) -> tuple[bool, str]:
    """
    Decide whether router should try the next provider.

    Returns:
    (decision, reason)
    """
    request_class = classify_user_request(prompt)
    failure_class = classify_failure(error_text)

    if request_class == "confirmed_unsafe":
        return False, "confirmed_unsafe_request_do_not_provider_shop"

    if failure_class == "technical_failure":
        return True, "technical_failure_try_next_provider"

    if failure_class == "provider_refusal_uncertain":
        return True, "possible_false_positive_refusal_try_next_provider"

    return True, "unknown_failure_try_next_provider_once"

"""The escalation ladder.

A step is ``(minutes_after_due, tier)``. Tiers widen the blast radius; they do
not merely repeat. Once the list is exhausted a profile may loop forever at its
final tier -- that is what makes "relentless" relentless.
"""
from dataclasses import dataclass

# Which channels participate at each tier. Channels not configured are skipped
# and logged, so a tier never silently does nothing.
TIER_CHANNELS: dict[int, list[str]] = {
    0: ["push"],
    1: ["push", "ntfy"],
    2: ["push", "ntfy", "gotify", "telegram", "matrix"],
    3: ["push", "ntfy", "gotify", "telegram", "matrix", "email", "webhook"],
    4: [
        "push", "ntfy", "gotify", "telegram", "matrix",
        "email", "webhook", "sms", "whatsapp",
    ],
}

# ntfy priority per tier (1 min .. 5 max).
#
# Deliberately capped at 4. Priority 5 bypasses Android Do Not Disturb, and
# DND is the phone owner deciding they are unavailable -- an app should not
# overrule that. A reminder marked "critical" opts into 5 explicitly; nothing
# else ever does.
TIER_NTFY_PRIORITY: dict[int, int] = {0: 3, 1: 3, 2: 4, 3: 4, 4: 4}
CRITICAL_NTFY_PRIORITY = 5


@dataclass(frozen=True)
class Profile:
    key: str
    steps: tuple[tuple[int, int], ...]
    repeat_every: int | None  # minutes; None = stop after the last step
    repeat_tier: int


PROFILES: dict[str, Profile] = {
    # Asks a few times, then trusts the daily brief to carry it.
    "gentle": Profile(
        key="gentle",
        steps=((0, 0), (120, 0), (1440, 1)),
        repeat_every=None,
        repeat_tier=1,
    ),
    # Widens channels through the first day, then a daily knock forever.
    "normal": Profile(
        key="normal",
        steps=((0, 0), (30, 0), (120, 1), (360, 2), (1440, 3)),
        repeat_every=1440,
        repeat_tier=3,
    ),
    # Never stops. Every channel you own, every four hours, until you close it.
    "relentless": Profile(
        key="relentless",
        steps=(
            (0, 0),
            (10, 0),
            (30, 1),
            (60, 1),
            (120, 2),
            (240, 2),
            (480, 3),
            (720, 3),
            (1080, 4),
        ),
        repeat_every=240,
        repeat_tier=4,
    ),
}

DEFAULT_PROFILE = "relentless"


def get_profile(key: str | None) -> Profile:
    return PROFILES.get(key or DEFAULT_PROFILE, PROFILES[DEFAULT_PROFILE])


def plan_attempt(profile: Profile, attempts: int) -> tuple[int, int]:
    """Return ``(minutes_after_due, tier)`` for attempt number ``attempts``.

    ``attempts`` is how many have already been made, so 0 is the first one.
    """
    if attempts < len(profile.steps):
        return profile.steps[attempts]

    if profile.repeat_every is None:
        # Ladder finished. Park it far enough out that only the daily brief
        # keeps mentioning it.
        last_offset = profile.steps[-1][0]
        return last_offset + 100 * 365 * 24 * 60, profile.repeat_tier

    overflow = attempts - len(profile.steps) + 1
    last_offset = profile.steps[-1][0]
    return last_offset + overflow * profile.repeat_every, profile.repeat_tier


def channels_for_tier(tier: int) -> list[str]:
    return TIER_CHANNELS.get(min(tier, max(TIER_CHANNELS)), TIER_CHANNELS[0])


def ntfy_priority(tier: int, critical: bool = False) -> int:
    """Priority for a tier. Only an explicitly critical reminder reaches 5,
    which is the level that overrides Do Not Disturb."""
    if critical:
        return CRITICAL_NTFY_PRIORITY
    return TIER_NTFY_PRIORITY.get(min(tier, 4), 3)


def is_terminal(profile: Profile, attempts: int) -> bool:
    """True when a profile has run out of ladder and will not chase again."""
    return profile.repeat_every is None and attempts >= len(profile.steps)

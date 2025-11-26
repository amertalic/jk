import enum


class MemberStatus(str, enum.Enum):
    """
    Enum representing the membership status of a club member.

    Values:
        ACTIVE: Member is currently active and in good standing
        INACTIVE: Member is temporarily inactive (e.g., on break)
        BANNED: Member has been banned from the club
        SUSPENDED: Member is temporarily suspended
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"
    SUSPENDED = "suspended"


class Sex(str, enum.Enum):
    """
    Enum representing biological sex or gender identity.

    Values:
        MALE: Male
        FEMALE: Female
        OTHER: Other or prefer not to say
    """

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


# Export a simple ordered list of choices suitable for templates.
# Each entry is (value, translation_key) so templates can call _() for labels.
SEX_CHOICES = [
    (Sex.MALE.value, "sex.male"),
    (Sex.FEMALE.value, "sex.female"),
]

# Membership status choices: (value, translation_key)
MEMBER_STATUS_CHOICES = [
    (MemberStatus.ACTIVE.value, "status.active"),
    (MemberStatus.INACTIVE.value, "status.inactive"),
    (MemberStatus.SUSPENDED.value, "status.suspended"),
    (MemberStatus.BANNED.value, "status.banned"),
]

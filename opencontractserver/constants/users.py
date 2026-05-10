"""
User-related constants.
"""

# Maximum length for the auto-assigned ``handle`` field on the User model.
# Bounded by the size of the camelCase pair plus a numeric collision suffix.
USER_HANDLE_MAX_LENGTH = 64

# Handle generator tunables. Selection is random within the curated word list
# (``ADJECTIVES × NOUNS`` ~= 56k base combos), so plain attempts almost always
# succeed; the suffixed phase is the safety net for namespace saturation.
HANDLE_PLAIN_ATTEMPTS = 50
HANDLE_SUFFIXED_ATTEMPTS = 100
HANDLE_SUFFIX_MIN = 10
HANDLE_SUFFIX_MAX = 9999

# Bounded retry loop for the User.save() handle auto-assignment when a
# concurrent insert wins the unique-constraint race. With the ~56k namespace,
# realistic collision odds make a handful of retries effectively guaranteed
# to succeed; bound prevents pathological loops.
HANDLE_INSERT_RETRY_ATTEMPTS = 5

"""
Constants related to fulfillment.
"""

OPEN_COURSES_COURSE_TYPES = {
    'audit',
    'professional',
    'verified-audit',
    'credit-verified-audit',
    'verified',
    'spoc-verified-audit',
    'honor',
    'verified-honor',
    'credit-verified-honor',
}

# Everything below is technical debt that we'll have to extract
# at some future point, due to Open edX concerns.
EXEC_ED_2U_COURSE_TYPES = {
    'executive-education-2u',
}


EXEC_ED_2U_FULFILLMENT_REQUEST_KWARGS = [
    'order_id',
]

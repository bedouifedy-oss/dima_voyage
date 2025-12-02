# core/constants.py

# Booking Classification
BOOKING_TYPES = [
    ("ticket", "✈️ Air Ticket"),
    ("hotel_out", "🏨 Outgoing Hotel"),
    ("hotel_loc", "🇹🇳 Local Hotel"),
    ("umrah", "🕋 Umrah Package"),
    ("trip", "🚌 Organized Trip"),
    ("tour", "🗺️ Tours"),
    ("visa_app", "Visa Application"),
    ("transfer", "🚖 Transfer"),
    ("dummy", "📄 Dummy Booking"),
]

# The Transactional Verbs (Physics of Value)
OPERATION_TYPES = [
    ("issue", "Issue / New Sale"),  # Creation of Value
    ("change", "Change / Amendment"),  # Modification of Value
    ("refund", "Refund / Reversal"),  # Destruction of Value
]

# Financial State
PAYMENT_STATUSES = [
    ("pending", "Pending Payment"),
    ("advance", "Partial / Advance"),
    ("paid", "Fully Paid"),
    ("refunded", "Refunded"),
    ("cancelled", "Cancelled (Void)"),
]

# Languages
LANGUAGES = [
    ("tn", "🇹🇳 Tunisian (Derja)"),
    ("fr", "🇫🇷 Français"),
]

# Support
PRIORITY_CHOICES = [
    ("low", "ℹ️ Info"),
    ("medium", "⚠️ Important"),
    ("high", "🚨 Critical"),
]

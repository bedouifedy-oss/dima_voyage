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
    ("overpaid", "Overpaid (Credit)"),  # Edge case handling
    ("refunded", "Refunded"),
]

SUPPLIER_PAYMENT_STATUSES = [
    ("unpaid", "🔴 Unpaid"),
    ("partial", "🟠 Partially Paid"),
    ("paid", "🟢 Paid"),
]

# Booking state
BOOKING_STATUSES = [
    ("quote", "📝 Quote"),  # Legacy support
    ("draft", "🚧 Draft"),  # NEW: For invoices that shouldn't touch ledger
    ("confirmed", "✅ Confirmed"),
    ("cancelled", "🚫 Cancelled"),
]

# Ledger logic
LEDGER_ENTRY_TYPES = [
    ("sale_revenue", "Sale Revenue"),  # + Credit (Income)
    ("customer_payment", "Customer Payment"),  # + Debit (Cash/Bank)
    ("customer_refund", "Customer Refund"),  # - Credit (Cash/Bank)
    ("supplier_cost", "Supplier Cost"),  # + Credit (Payable)
    ("supplier_payment", "Supplier Payment"),  # + Debit (Payable)
]

# Payment types
PAYMENT_TRANSACTION_TYPES = [
    ("payment", "💰 Payment Received"),
    ("refund", "💸 Refund Issued"),
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

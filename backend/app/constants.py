# Default grocery categories matching the mobile app's defaults.
# Used for new authenticated users (AuthUtils.create_user) and as the
# fallback for guest recipe generation, which has no User row to read
# grocery_categories from.
DEFAULT_GROCERY_CATEGORIES = [
    'produce', 'butchery', 'dry-goods', 'chilled',
    'frozen', 'pantry', 'bakery', 'deli', 'beverages', 'spices'
]

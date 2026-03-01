import os

BOT_A_TOKEN             = os.getenv("BOT_A_TOKEN")
BOT_B_TOKEN             = os.getenv("BOT_B_TOKEN")
ADMIN_CHAT_ID           = int(os.getenv("ADMIN_CHAT_ID"))
OPERATIONS_BOT_USERNAME = os.getenv("OPERATIONS_BOT_USERNAME")
DATABASE_URL            = os.getenv("DATABASE_URL")
DASHBOARD_SECRET_KEY    = os.getenv("DASHBOARD_SECRET_KEY", "change_this_in_production")
DASHBOARD_USER          = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASS          = os.getenv("DASHBOARD_PASS", "kingsriver2024")
TONCENTER_API_KEY       = os.getenv("TONCENTER_API_KEY", "")  # optional, increases rate limit

# config.py — DO NOT COMMIT
# Copy this file, fill in your values, and add config.py to .gitignore

OUTTURN_URL    = "https://smwsa.com/collections/whisky"
CHECK_INTERVAL = (45, 75)   # randomized interval range in seconds

NTFY_CHANNEL = ""           # e.g. "smws-monitor-zp7k" — leave blank to skip

USERS = [
    {
        "name": "User1",
        "discord_webhook": "",          # your private Discord channel webhook URL
        "priority_regions": ["Islay"],
        "priority_flavors": [
            "Bold & Peaty", "Heavily Peated", "Coastal & Maritime",
            "Oily & Coastal", "Lightly Peated", "Peated", "Smoky & Fruity"
        ],
        "exclude_distilleries": ["53"], # Caol Ila
        "price_threshold": 175,
    },
    {
        "name": "User2",
        "discord_webhook": "",          # friend's private Discord channel webhook URL
        "priority_regions": [],         # TBD
        "priority_flavors": [],         # TBD
        "exclude_distilleries": [],
        "price_threshold": 200,
    },
]
"""
Constants for RSNBusBot
"""

### DEFAULT SETTINGS
DEFAULT_MAX_RIDERS = 40


### MESSAGES
START_MSG = """Welcome to RSN Bus Bot! Please send /start directly to the bot to enable receiving of tokens. \
Use /settings to edit the default settings."""
USER_START_MSG = """Welcome to RSN Bus Bot! Booking confirmation tokens can now be sent to you."""
HELP_MSG = """Here are a list of currently available commands:
/start - Introduce the bot; initialize daily registration.
/view_settings - Shows a list of current bot settings.
/settings - Edit bot settings.
/help - List of bot commands.
/book - Manually open registration.
/manage - Manage bookings. Allows admin to close, reopen, end and cancel bookings.
/cancel_book - Cancels automatic booking for the next day.
/uncancel_book - Enables automatic booking for the next day.
/broadcast - Broadcast a custom message to all service chats.
/notify_late - Send notification message to chat informing users that bus will be late.
/notify_late_all - Broadcast notification message to all service chats informing users that buses will be late.
/view_data_summary - Send message summarizing ridership statistics across all services.
/cancel - Cancels any conversation.
"""
USER_HELP_MSG = """There are currently no commands available for riders."""

VIEW_SETTINGS_MSG = """Here are the current settings for the bot:"""
SETTINGS_MSG = """Select a setting to edit, or /cancel to stop editing.
Max Riders
Pickup Location
Destination
Chat Type
Buses"""
RIDER_SETTING_MSG = """Please enter a number for the max riders allowed per registration."""
PICKUP_SETTING_MSG = """Please enter the pickup location."""
DESTINATION_SETTING_MSG = """Please enter the destination."""
CHAT_SETTING_MSG = """Please enter the type of chat (Admin/Service)."""
BUSES_SETTING_MSG = """Please send a list of bus timings in this format. E.g.,

0630
0645

A minimum of one bus timing must be sent."""
UPDATED_SETTINGS_MSG = """Settings updated! Select another setting to continue editing, or /cancel to stop editing."""

MAX_RIDERS_NOTIF_MSG = """The maximum number of riders have been registered. Please find alternative means of transport, or check again later."""
OPEN_SPACES_NOTIF_MSG = """New spaces have opened up for shuttle bus registration!"""

MANAGE_MSG = "Enter booking ID of registration to edit: "
MANAGE_FUNCTIONS_MSG = """Select a function to use, or /cancel to stop editing.
Close
Reopen
End
Cancel"""
INVALID_BOOK_ID_MSG = "Invalid booking ID. Please try again: "
CLOSE_NOTIF_MSG = """Registration has been closed by the admin."""
REOPEN_NOTIF_MSG = """Registration has been reopened by the admin."""
END_NOTIF_MSG = """Registration has ended."""
END_DAILY_NOTIF_MSG = """Registration has been ended for the day."""
CANCEL_NOTIF_MSG = """Registration has been cancelled by the admin."""
OVERWRITE_FALSE_MSG = """Dear all, the bus service will not be running tomorrow. Thank you for your understanding."""

BROADCAST_PROMPT_MSG = """Please type the message you wish to broadcast, or /cancel to cancel broadcast."""
BROADCAST_CONFIRM_MSG = """Please confirm that this is the message you want to broadcast? (Yes/No)"""
BROADCAST_SENT_MSG = """Message has been broadcasted!"""
BROADCAST_CANCEL_MSG = """Broadcasting has been cancelled!"""
NOTIFY_LATE_MSG = """Dear all, the bus at 0700hrs will be late. Please inform your respective units of the delay and to seek their understanding. Thank you"""

CONVERSATION_INVALID_MSG = """Invalid response."""
CONVERSATION_CANCEL_MSG = """Conversation exited."""
CONVERSATION_TIMEOUT_MSG = """Conversation timeout reached, conversation exited."""
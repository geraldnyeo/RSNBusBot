"""
RSNBusBot v0.1.0
"""

### IMPORTS
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    ConversationHandler, 
    CallbackQueryHandler, 
    ContextTypes,
    MessageHandler,
    filters
)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from http import HTTPStatus

import os
from datetime import datetime, timedelta, time
import pytz
from functools import wraps

import sqlite3

### CONSTANTS
# Environment Variables
TOKEN = os.environ['TOKEN']
BOT_USERNAME = os.environ['BOT_USERNAME']
TIMEZONE = os.environ['TIMEZONE']
DB_FILEPATH = os.environ['DB_FILEPATH']
DEFAULT_MAX_RIDERS = 40

# Messages
START_MSG = """Welcome to Shuttle Bus Bot! Please send /start directly to the bot to enable recieving of tokens. \
Use /settings to edit the default settings."""
VIEW_SETTINGS_MSG = """Here are the current settings for the bot:"""
SETTINGS_MSG = """Select a setting to edit, or /cancel to stop editing.
Chat Type
Max Riders
Pickup Location
Destination"""
CHAT_SETTING_MSG = """Please enter the type of chat (Admin/Service)."""
RIDER_SETTING_MSG = """Please enter a number for the max riders allowed per registration."""
PICKUP_SETTING_MSG = """Please enter the pickup location."""
DESTINATION_SETTING_MSG = """Please enter the destination."""
UPDATED_SETTINGS_MSG = """Settings updated! Select another setting to continue editing, or /cancel to stop editing."""
CANCELLED_SETTINGS_MSG = """Settings cancelled."""
INVALID_RESPONSE_MSG = """Invalid response."""
HELP_MSG = """Here are a list of currently available commands:
/start - Starts the bot, and initialises the daily registration.
/help - Displays a list of help functions.
/book - Manually starts registration for the next day."""
PRIVATE_HELP_MSG = """Private chat functionality is currently unavailable. Look forward to our future updates!"""
MAX_RIDERS_NOTIF_MSG = """The maximum number of riders have been registered. Please find alternative means of transport, or check again later."""
OPEN_SPACES_NOTIF_MSG = """New spaces have opened up for shuttle bus registration!"""
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


### DATABASE
con = sqlite3.connect(f"{DB_FILEPATH}/test.db")
cur = con.cursor()
cur.execute("CREATE TABLE movie(title, year, score)")
res = cur.execute("SELECT name FROM sqlite_master")
print(res.fetchone())


### HELPER FUNCTIONS
def group(func):
    """
    Decorator for commands which can only be run in a group chat, not private chat.
    """
    # TODO: Debug - apparently group / private =/= group chat / DM
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs):
        if update.effective_chat.type == "group":
            return await func(update, context, *args, **kwargs)
        else:
            print(f"Command failed as attempted to run in private chat.")
            return

    return wrapped

def private(func):
    """
    Decorator for commands which can only be run in a private chat, not group chat.
    """
    # TODO: Debug (see above)
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs):
        if update.effective_chat.type == "private":
            return await func(update, context, *args, **kwargs)
        else:
            print(f"Command failed as attempted to run in group chat.")
            return

    return wrapped

def restricted(func):
    """
    Defines decorator which marks commands as restricted.
    Restricted commands can only be run by the group admins.
    """
    # TODO: Debug along with above decorators
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs):
        chat_admins = await update.effective_chat.get_administrators()
        user = update.effective_user
        if user in (admin.user for admin in chat_admins):
            return await func(update, context, *args, **kwargs)
        else:
            print(f"Unauthorized access denied for {user.username}")
            return
    
    return wrapped

# Invalid response catcher
async def invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invalid response catcher for all ConversationHandlers"""
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id = chat_id,
        text = INVALID_RESPONSE_MSG,
    )


### COMMANDS
## GENERAL / SETTINGS
# @group
# @restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Introduce the bot to users, and initialises various processes:
     - Auto Messaging
     - Setup Constants
    """
    # TODO: Setup constants conversation handler
    chat_id = update.effective_chat.id

    await context.bot.send_message(
        chat_id = chat_id,
        text = START_MSG,
        reply_markup = ReplyKeyboardRemove() # Remove any unwanted keyboards on start
    ) # TODO: If group, introduce. If private, something else.

    if update.effective_chat.id not in context.bot_data: # Only initialize if not yet intialized
        context.job_queue.run_daily(daily_booking,
                                    time=time(hour=17, minute=30, second=0, tzinfo=pytz.timezone(TIMEZONE)), 
                                    days=(0, 1, 2, 3, 4, 5, 6), # MUST be 0 to 6 or it won't work
                                    chat_id=chat_id) # Sends booking every day
        context.job_queue.run_daily(end_book_job,
                                    time=time(hour=23, minute=59, second=59, tzinfo=pytz.timezone(TIMEZONE)),
                                    days=(0, 1, 2, 3, 4, 5, 6),
                                    chat_id=chat_id)

        # Initialise the data structure which the bot will be using.
        payload = {
            update.effective_chat.id: { # TODO: Swap to using chat_data rather than bot_data
                "settings": {
                    "CHAT": "service",
                    "MAX RIDERS": DEFAULT_MAX_RIDERS,
                    "PICKUP": "",
                    "DESTINATION": "",
                },
                "message_id": None,
                "bookings": 0,
                "users": [],
                "overwrite": {}
            }
        }
        context.bot_data.update(payload)
        print(context.bot_data)

# @group
# @restricted
async def view_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows users the current settings.
    """
    chat_id = update.effective_chat.id

    text = VIEW_SETTINGS_MSG
    for key, value in context.bot_data[chat_id]["settings"].items():
        text = f"{text}\n{key}: {value}"
    
    await context.bot.send_message(
        chat_id = chat_id,
        text = text
    )

SELECT, CHAT, RIDERS, PICKUP, DESTINATION = range(5) # states for settings conversation handler

# @group
# @restricted
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Settings Menu
    """
    buttons = [
        [KeyboardButton("Pickup Location"),
         KeyboardButton("Destination")],
        [KeyboardButton("Max Riders"),
         KeyboardButton("Chat Type")]
    ]
    reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
    await context.bot.send_message(
        chat_id = update.effective_chat.id,
        text = SETTINGS_MSG,
        reply_markup = reply_markup
    )
        
    return SELECT

async def settings_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends prompt messages once a setting to change is selected."""

    # Get the chat data
    chat_id = update.effective_chat.id

    # Redirect user to correct state
    selection = update.message.text
    match selection:
        case "Chat Type":
            buttons = [
                [KeyboardButton("Admin"),
                 KeyboardButton("Service")]
            ]
            reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
            await context.bot.send_message(
                chat_id = chat_id,
                text = CHAT_SETTING_MSG,
                reply_markup = reply_markup
            )
            return CHAT
        case "Max Riders":
            await context.bot.send_message(
                chat_id = chat_id,
                text = RIDER_SETTING_MSG,
            )
            return RIDERS
        case "Pickup Location":
            await context.bot.send_message(
                chat_id = chat_id,
                text = PICKUP_SETTING_MSG,
            )
            return PICKUP
        case "Destination":
            await context.bot.send_message(
                chat_id = chat_id,
                text = DESTINATION_SETTING_MSG,
            )
            return DESTINATION
        
async def settings_update(update: Update, context: ContextTypes.DEFAULT_TYPE, setting, value):
    """Update settings and prompts user to select another setting."""

    # Get chat data
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    chat_data["settings"][setting] = value
    await context.bot.send_message(
        chat_id = chat_id,
        text = UPDATED_SETTINGS_MSG
    )

    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data) # Important for debugging

async def settings_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for chat type"""

    await settings_update(update, context, "CHAT", update.message.text)
    return SELECT

async def settings_riders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for max riders"""

    await settings_update(update, context, "MAX RIDERS", int(update.message.text))
    return SELECT

async def settings_pickup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for pickup"""

    await settings_update(update, context, "PICKUP", update.message.text)
    return SELECT

async def settings_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for destination"""

    await settings_update(update, context, "DESTINATION", update.message.text)
    return SELECT

async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation"""
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id = chat_id,
        text = CANCELLED_SETTINGS_MSG,
    )

    return ConversationHandler.END

settings_handler = ConversationHandler(
    entry_points=[CommandHandler("settings", settings_command)],
    states = {
        SELECT: [MessageHandler(filters.Regex(r"^(Chat Type|Max Riders|Pickup Location|Destination)$"), settings_select),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        CHAT: [MessageHandler(filters.Regex(r"^(Admin|Service)$"), settings_chat),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        RIDERS: [MessageHandler(filters.Regex(r"^[0-9]+$"), settings_riders),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        PICKUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_pickup),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_destination),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
    },
    fallbacks = [CommandHandler("cancel", cancel_settings)]
)

# @group
# @restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inform the user about the bot's available commands."""

    await update.message.reply_text(HELP_MSG) # TODO: Update list of commands

## REGISTRATION
async def registration_message(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id=None, close=False):
    """Creates / Re-creates menu for registration."""

    chat_data = context.bot_data[chat_id]
    pickup, destination = chat_data["settings"]["PICKUP"], chat_data["settings"]["DESTINATION"]

    # Prepare the text message
    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")
    text = f"Registration of {pickup} to {destination} Shuttle Bus slots for {date}."
    
    if message_id:
        users = context.bot_data[chat_id]['users']
        text = f"{text}\n\nPlaces Reserved:"
        for u in users:
            text += f"\n{u['username']}"
    
    # Send the message
    reply_markup = None
    if not close:
        buttons = [
            [InlineKeyboardButton("Book", callback_data="book"),
            InlineKeyboardButton("Cancel", callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
    
    if message_id:
        message = await context.bot.edit_message_text(
            chat_id = chat_id,
            message_id = message_id,
            text = text,
            reply_markup = reply_markup,
        )
    else:
        message = await context.bot.send_message(
            chat_id = chat_id,
            text = text,
            reply_markup = reply_markup,
        )

    return message

# @group
# @restricted
async def book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message to book shuttle bus slots."""

    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]
    
    # Send the registration message
    message = await registration_message(context, chat_id)

    # Update data
    chat_data["message_id"] = message.message_id
    chat_data["bookings"] = 0
    chat_data["users"] = []
    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)

async def daily_booking(context: ContextTypes.DEFAULT_TYPE):
    """Initiates / cancels daily booking for special cases."""

    chat_id = context.job.chat_id
    chat_data = context.bot_data[chat_id]
    dt = datetime.today() + timedelta(1)

    # Check for any overwrites
    date = dt.strftime("%d %b %y")
    overwrites = chat_data["overwrite"]
    if date in overwrites:
        flag = overwrites[date]
        
        # Remove overwrite once it has been triggered
        del overwrites[date]
        chat_data["overwrite"] = overwrites
        payload = {
            chat_id: chat_data
        }
        context.bot_data.update(payload)
        print(context.bot_data)

        # Sends appropriate message
        if flag:
            await book_job(context)
        else:
            await context.bot.send_message(
                chat_id = chat_id,
                text = OVERWRITE_FALSE_MSG
            )

            return

    # Don't send message on weekends
    day = dt.weekday()
    if day == 5 or day == 6: # Don't send if the next day is Sat or Sun
        return
    
    await book_job(context)

async def book_job(context: ContextTypes.DEFAULT_TYPE):
    """Sends a message to book shuttle bus slots for a day."""

    chat_id = context.job.chat_id
    chat_data = context.bot_data[chat_id]
    
    # Send registration message
    message = await registration_message(context, chat_id)

    # Update data
    chat_data["message_id"] = message.message_id
    chat_data["bookings"] = 0
    chat_data["users"] = []
    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)

# @group
# @restricted
async def close_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Close registration for the current day. 
    New riders will not be registered. 
    List of registered users will still be stored.
    """
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Exit if no registration to close
    if chat_data["message_id"] == None:
        print("Close command failed as booking not open.")
        return

    # Remove reply_markup so users cannot register
    await registration_message(context, 
                               chat_id, 
                               message_id=chat_data['message_id'],
                               close=True
                               )
    
    # Notif message
    await context.bot.send_message(chat_id = chat_id,
                                   text = CLOSE_NOTIF_MSG)

# @group
# @restricted
async def reopen_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Reopen registration for the current day. New riders can continue being registered.
    """
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Exit if no registration to open
    if chat_data["message_id"] == None:
        print("Reopen command failed as booking not open.")
        return

    # Add back reply_markup so users can register
    await registration_message(context, 
                               update.effective_chat.id,
                               message_id=context.bot_data[update.effective_chat.id]['message_id']
                               )
    
    # Notif message
    await context.bot.send_message(chat_id = update.effective_chat.id,
                                   text = REOPEN_NOTIF_MSG)
    
# @group
# @restricted
async def end_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ends registration"""
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Exit if no registration to end
    if chat_data["message_id"] == None:
        print("End command failed as booking not open.")
        return
    
    # Remove reply_markup so users cannot reply
    await registration_message(context, 
                               chat_id, 
                               message_id=chat_data['message_id'],
                               close=True
                               )
    
    # Notif message
    await context.bot.send_message(chat_id = chat_id,
                                   text = END_NOTIF_MSG)
    
    # Send tokens
    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")
    booking_token = f"Your registration for the shuttle bus from \
{chat_data['settings']['PICKUP']} to {chat_data['settings']['DESTINATION']} \
for {date} has been confirmed."
    for user in chat_data["users"]:
        try:
            await context.bot.send_message(
                chat_id = user["id"],
                text = booking_token
            )
        except error as e:
            print(f"Failed to send token to user {user['username']} (id: {user['id']}) as user did not initiate conversation with bot.")
            print(e)

async def end_book_job(context: ContextTypes.DEFAULT_TYPE):
    """Ends registration"""

    chat_id = context.job.chat_id
    chat_data = context.bot_data[chat_id]

    # Exit if no registration to end
    if chat_data["message_id"] == None:
        print("Close command failed as booking not open.")
        return

    # Remove reply_markup so users cannot reply
    await registration_message(context, 
                               chat_id, 
                               message_id=chat_data['message_id'],
                               close=True
                               )
    
    # Notif message
    await context.bot.send_message(chat_id = chat_id,
                                   text = END_NOTIF_MSG)
    
    # Send tokens
    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")
    booking_token = f"Your registration for the shuttle bus from \
{chat_data['settings']['PICKUP']} to {chat_data['settings']['DESTINATION']} \
for {date} has been confirmed."
    for user in chat_data["users"]:
        try:
            await context.bot.send_message(
                chat_id = user["id"],
                text = booking_token
            )
        except error as e:
            print(e)

# @group
# @restricted
async def cancel_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    1730-2359: Cancel registration for the current day (irreversible).
    Otherwise: Cancel automatic registration for the next day.
    """
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]
    
    if chat_data["message_id"] == None: # Cancel automatic registration for the next day
        # TODO: Replace this clause with call of booking cancellation for a range

        # Update overwrite data
        date = datetime.today() + timedelta(1)
        date = date.strftime("%d %b %y")
        chat_data["overwrite"][date] = False
        payload = {
            chat_id: chat_data
        }
        context.bot_data.update(payload)
        print(context.bot_data)

        # Notif Message
        await context.bot.send_message(
            chat_id = chat_id,
            text = f"Booking cancelled for {date}" # TODO: Generalize
        )
    else: # Cancel registration for the current day
        # Exit if no registration to cancel
        if chat_data["message_id"] == None:
            print("Booking reset failed as booking not open.")
            return

        # Remove button functionality
        await registration_message(context, 
                                chat_id, 
                                message_id=chat_data['message_id'],
                                close=True
                                )

        # Delete data
        chat_data["message_id"] = None
        chat_data["bookings"] = 0
        chat_data["users"] = []
        payload = {
            chat_id: chat_data
        }
        context.bot_data.update(payload)
        print(context.bot_data)

        # Notif message
        await context.bot.send_message(
            chat_id = chat_id,
            text = CANCEL_NOTIF_MSG
        )

# @group
# @restricted
async def uncancel_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Uncancels the next day's booking. Can also be used to overwrite the next day to True."""
    
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Update overwrite data
    dt = datetime.today() + timedelta(1)
    date = dt.strftime("%d %b %y")
    chat_data["overwrite"][date]
    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)

    # Notif Message
    await context.bot.send_message(
        chat_id = chat_id,
        text = f"Booking uncancelled for {date}" # TODO: Generalize
    )


async def booking_cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Updates the bot once user has clicked certain options of the booking message."""

    query = update.callback_query.data
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]
    
    # Get user information
    user = {
        'username': update.callback_query.from_user.username,
        'id': update.callback_query.from_user.id
    }
    users = chat_data['users']

    if "book" in query: # "Book" button clicked
        # Check if max users have been reached
        if len(users) == chat_data["settings"]["MAX RIDERS"]:
            print(f"Registration failed as maximum number of riders have registered.")
            return
        # Check if user has already booked
        if user in users:
            print(f"Registration failed as user attempted to register twice.")
            return

        users.append(user)

        # Update bot data
        chat_data['bookings'] += 1
        chat_data["users"] = users
        payload = {
            chat_id: chat_data
        }
        context.bot_data.update(payload)
        print(context.bot_data) # Important for debugging

        # Notif message for MAX RIDERS reached
        if len(users) >= chat_data["settings"]["MAX RIDERS"]:
            await update.callback_query.message.reply_text(MAX_RIDERS_NOTIF_MSG)

    if "cancel" in query: # "Cancel" button clicked
        # Check if user has already booked
        if user not in users:
            print(f"Registration cancellation failed as user has not registered before.")
            return
        
        users.remove(user)

        # Update bot data
        chat_data['bookings'] -= 1
        chat_data["users"] = users
        payload = {
            chat_id: chat_data
        }
        context.bot_data.update(payload)
        print(context.bot_data) # Important for debugging

        # If new spaces open up, send a notification message
        if len(users) == chat_data["settings"]["MAX RIDERS"] - 1:
            await update.callback_query.message.reply_text(OPEN_SPACES_NOTIF_MSG)

    # Edit the message to show list of users
    await registration_message(context, 
                               chat_id, 
                               message_id = chat_data['message_id']
                               )

## BROADCAST / NOTIFICATION
CONFIRM, SENT = range(6, 8) # States for broadcast conversation handler

# @group
# @restricted
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast a message to every service chat."""
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id = chat_id,
        text = BROADCAST_PROMPT_MSG
    )

    return CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message to confirm sending the message."""

    chat_id = update.effective_chat.id
    message = update.message.text
    text = f'"{message}"\n\n{BROADCAST_CONFIRM_MSG}'

    buttons = [
        [KeyboardButton("Yes"),
         KeyboardButton("No")]
    ]
    reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
    await context.bot.send_message(
        chat_id = chat_id,
        text = text,
        reply_markup = reply_markup
    )

    # Save the message the user wants to broadcast
    context.user_data["broadcast"] = message
    print(context.user_data)

    return SENT

async def broadcast_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a confirmation message for the broadcast."""

    chat_id = update.effective_chat.id
    message = update.message.text

    if message == "Yes":
        # Notif Message
        await context.bot.send_message(
            chat_id = chat_id,
            text = BROADCAST_SENT_MSG
        )

        # Send message to every service chat
        for chat in context.bot_data.keys():
            if context.bot_data[chat]["settings"]["CHAT"] == "service":
                await context.bot.send_message(
                    chat_id = chat,
                    text = context.user_data["broadcast"]
                )

        del context.user_data["broadcast"]

        return ConversationHandler.END
    
    else: # if message = "No"
        await context.bot.send_message(
            chat_id = chat_id,
            text = BROADCAST_PROMPT_MSG
        )
        return CONFIRM

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message to indicate broadcast has been cancelled."""

    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id = chat_id,
        text = BROADCAST_CANCEL_MSG
    )

    return ConversationHandler.END

broadcast_handler = ConversationHandler(
    entry_points=[CommandHandler("broadcast", broadcast_command)],
    states = {
        CONFIRM: [MessageHandler(filters.TEXT &~filters.COMMAND, broadcast_confirm),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        SENT: [MessageHandler(filters.Regex(r"^(Yes|No)$"), broadcast_sent),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
    },
    fallbacks = [CommandHandler("cancel", cancel_broadcast)]
)

# @group
# @restricted
async def notify_late(update: Update, context: ContextTypes.DEFAULT_TYPE, all_chats=False):
    """Send a notification message to notify users of late buses."""

    chat_id = update.effective_chat.id
    
    chats = [chat_id]
    if all_chats:
        chats = context.bot_data.keys()

    for chat in chats:
        await context.bot.send_message(
            chat_id = chat,
            text = NOTIFY_LATE_MSG
        )


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catches any error and prints it to the command line for debugging."""
    print(f'Update:\n {update}\n caused error:\n {context.error}')


### MAIN
"""
There are two applications running:
 - The Python Telegram Bot application, which handles receiving, processing and sending Telegram updates.
 - The FastAPI application, which sets up the webhook endpoint for Telegram to send updates to.
"""
print('Starting bot...') # Logging

# Create the PTB application
ptb = (
    Application.builder()
    .token(TOKEN)
    .concurrent_updates(False)
    .build()
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """This code only runs once, before the application starts up and starts receiving requests."""

    await ptb.bot.setWebhook(url="https://rsnbusbot.onrender.com/webhook",
                            certificate=None) # Sets up webhook
    
    # Allows ptb and fastapi applications to run together
    async with ptb:
        await ptb.start()
        yield
        await ptb.stop()

# Create the FastAPI application
app = FastAPI(lifespan=lifespan) # Do not run FastAPI code for local dev using polling

@app.get("/")
async def index():
    """Landing page for the bot."""
    # TODO FUTURE: Add a basic single static page here to explain the bot!
    return "Hello"

@app.post("/webhook")
async def process_update(request: Request):
    """Updates PTB application when post request received at webhook"""
    req = await request.json()
    update = Update.de_json(req, ptb.bot)
    await ptb.process_update(update)
    return Response(status_code = HTTPStatus.OK)

# Set up PTB handlers
# Commands (General)
ptb.add_handler(CommandHandler('start', start_command))
ptb.add_handler(CommandHandler('view_settings', view_settings_command))
ptb.add_handler(settings_handler)
ptb.add_handler(CommandHandler('help', help_command))

# Commands (Booking)
ptb.add_handler(CommandHandler('book', book_command))
ptb.add_handler(CallbackQueryHandler(booking_cb_handler, r"^(book|cancel)$")) # Handles callbacks for book command
ptb.add_handler(CommandHandler('close_book', close_book_command))
ptb.add_handler(CommandHandler('reopen_book', reopen_book_command))
ptb.add_handler(CommandHandler('end_book', end_book_command))
ptb.add_handler(CommandHandler('cancel_book', cancel_book_command))
ptb.add_handler(CommandHandler('uncancel_book', uncancel_book_command))

# Commands (Broadcasting)
ptb.add_handler(broadcast_handler)
ptb.add_handler(CommandHandler('notify_late', lambda u, c: notify_late(u, c)))
ptb.add_handler(CommandHandler('notify_late_all', lambda u, c: notify_late(u, c, all_chats=True)))

# Messages
# For later development

# Errors
ptb.add_error_handler(error)

# Polling, for dev purposes
# print('Polling...')
# ptb.run_polling(poll_interval=3, allowed_updates=Update.ALL_TYPES)
    
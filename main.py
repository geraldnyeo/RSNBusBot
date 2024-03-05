"""
RSNBusBot v1.0.0
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
from fastapi import FastAPI

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
START_MSG = """Welcome to RSN Bus Bot! Please send /start directly to the bot to enable recieving of tokens. \
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


### DATABASE
con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db") 
cur = con.cursor()


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
     - Database Configuration
     - Auto Messaging
     - Setup Ephermeral Data 
    """
    chat_id = update.effective_chat.id

    # Add new row for chat into database if required
    # Check if chat has been initialized for settings table
    res = cur.execute(f"SELECT EXISTS (SELECT 1 FROM settings WHERE chat_id={chat_id})")
    exists = res.fetchone()
    exists = exists[0]

    # Initialize settings
    if not exists: 
        cur.execute(f"INSERT INTO settings VALUES \
                    ({chat_id}, 'service', {DEFAULT_MAX_RIDERS}, '', '')")
        con.commit()

    # Setup automatic processes and chat_data
    if chat_id not in context.bot_data.keys():
        # Automatic processes
        context.job_queue.run_daily(daily_booking,
                                    time=time(hour=17, minute=30, second=0, tzinfo=pytz.timezone(TIMEZONE)), 
                                    days=(0, 1, 2, 3, 4, 5, 6), # MUST be 0 to 6 or it won't work
                                    chat_id=chat_id) # Sends booking every day
        context.job_queue.run_daily(end_book_job,
                                    time=time(hour=23, minute=59, second=59, tzinfo=pytz.timezone(TIMEZONE)),
                                    days=(0, 1, 2, 3, 4, 5, 6), 
                                    chat_id=chat_id) #Ends all bookings
        
        # print(context.job_queue.jobs())

        # Initialise the message data structure which the bot will be using.
        payload = {
            chat_id: { # TODO: Swap to using chat_data rather than bot_data
                "initialized": False,
                "bookings": {},
                "overwrite": {}
            }
        }
        context.bot_data.update(payload)
        print(context.bot_data)

    # Send introduction message
    await context.bot.send_message(
        chat_id = chat_id,
        text = START_MSG,
        reply_markup = ReplyKeyboardRemove() # Remove any unwanted keyboards on start
    ) # TODO: If group, introduce. If private, something else.

    # TODO: Setup constants conversation handler

# @group
# @restricted
async def view_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows users the current settings.
    """
    chat_id = update.effective_chat.id

    # Get database data
    res = cur.execute(f"SELECT chat_type, max_riders, pickup, destination \
                      FROM settings WHERE chat_id={chat_id}")
    data = res.fetchone()
    if data is None:
        print("Unable to retrieve data from database.")
        return

    # Prepare message
    text = VIEW_SETTINGS_MSG
    settings = ["Chat Type", "Max Riders", "Pickup", "Destination"]
    for i in range(len(settings)):
        text = f"{text}\n{settings[i]}: {data[i]}"
    
    # Send message
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
    # Send nessage
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
    """
    Update settings and prompts user to select another setting.
    """
    chat_id = update.effective_chat.id

    # Send message
    await context.bot.send_message(
        chat_id = chat_id,
        text = UPDATED_SETTINGS_MSG
    )

    # Update database
    if type(value) == str: # add quotes to denote string in SQL
        value = f"'{value}'"

    cur.execute(f"UPDATE settings SET \
                {setting}={value} \
                WHERE chat_id={chat_id}")
    con.commit()

async def settings_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for chat type"""

    await settings_update(update, context, "chat_type", update.message.text)
    return SELECT

async def settings_riders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for max riders"""

    await settings_update(update, context, "max_riders", int(update.message.text))
    return SELECT

async def settings_pickup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for pickup"""

    await settings_update(update, context, "pickup", update.message.text)
    return SELECT

async def settings_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for destination"""

    await settings_update(update, context, "destination", update.message.text)
    return SELECT

async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation"""
    chat_id = update.effective_chat.id

    # Send message
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
async def registration_message(context: ContextTypes.DEFAULT_TYPE, 
                               chat_id, 
                               date=None,
                               t=None,
                               message_id=None, 
                               close=False):
    """
    Creates / Re-creates menu for registration.
    """
    chat_data = context.bot_data[chat_id]

    # Get pickup and destination info
    res = cur.execute(f"SELECT pickup, destination FROM settings WHERE chat_id={chat_id}")
    data = res.fetchone()
    pickup, destination = data[0], data[1]

    # Get date and time
    if not date:
        date = chat_data["bookings"][message_id]["date"]
    if not t:
        t = chat_data["bookings"][message_id]["time"]

    # Get the book_id
    if not message_id:
        res = cur.execute("SELECT COUNT(*) FROM ridership")
        book_id = res.fetchone()[0]
    else:
        book_id = chat_data["bookings"][message_id]["book_id"]

    # Prepare the text message
    text = f"Booking ID: {book_id} \n\
Registration of {pickup} to {destination} Shuttle Bus slots for {date} at {t}."
    
    if message_id:
        users = chat_data["bookings"][message_id]['users']
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

        return message
    else:
        message = await context.bot.send_message(
            chat_id = chat_id,
            text = text,
            reply_markup = reply_markup,
        )

        return message, book_id

# @group
# @restricted
async def book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a message to book shuttle bus slots.
    """
    # TODO: Conversation handler for this command
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Get date and time
    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")
    t = "NA"
    
    # Send the registration message
    message, book_id = await registration_message(context, chat_id, date, t)

    # Update data
    chat_data["bookings"][message.message_id] = {
        "book_id": book_id,
        "bookings": 0,
        "users": [],
        "date": date,
        "time": t
    }
    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)

    # Update database
    cur.execute(f"INSERT INTO ridership VALUES \
                ({book_id}, {chat_id}, '{date}', '{t}', 0)")
    con.commit()

async def daily_booking(context: ContextTypes.DEFAULT_TYPE):
    """
    Initiates / cancels daily booking for special cases.
    """
    chat_id = context.job.chat_id
    chat_data = context.bot_data[chat_id]
    
    dt = datetime.today() + timedelta(1)

    # Check for any overwrites
    date = dt.strftime("%d %b %y")
    overwrites = chat_data["overwrite"]
    if date in overwrites:
        # Save the overwrite temporarily
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
            await book_job(context, "0630") # 0630 bus
            await book_job(context, "0645") # 0645 bus
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
    
    await book_job(context, "0630") # 0630 bus
    await book_job(context, "0645") # 0645 bus

async def book_job(context: ContextTypes.DEFAULT_TYPE, t):
    """
    Sends a message to book shuttle bus slots for a day.
    """
    # TODO: Multiple services update
    chat_id = context.job.chat_id
    chat_data = context.bot_data[chat_id]

    # Get date
    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")
    
    # Send registration message
    message, book_id = await registration_message(context, chat_id, date, t)

    # Update data
    chat_data["bookings"][message.message_id] = {
        "book_id": book_id,
        "bookings": 0,
        "users": [],
        "date": date,
        "time": t
    }
    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)

    # Update database
    cur.execute(f"INSERT INTO ridership VALUES \
                ({message.message_id}, {chat_id}, '{date}', '{t}', 0)")
    con.commit()

async def booking_cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Updates the bot once user has clicked certain options of the booking message.
    """
    query = update.callback_query.data
    message_id = update.callback_query.message.message_id
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Get max_riders from database
    res = cur.execute(f"SELECT max_riders \
                      FROM settings WHERE chat_id={chat_id}")
    data = res.fetchone()
    max_riders = data[0]
    
    # Get user information
    user = {
        'username': update.callback_query.from_user.username,
        'id': update.callback_query.from_user.id
    }
    users = chat_data["bookings"][message_id]['users']

    # Handle the callback
    if "book" in query: # "Book" button clicked
        # Check if max users have been reached
        if len(users) == max_riders:
            print(f"Registration failed as maximum number of riders have registered.")
            return
        # Check if user has already booked
        if user in users:
            print(f"Registration failed as user attempted to register twice.")
            return

        users.append(user)

        # Update bot data
        chat_data["bookings"][message_id]['bookings'] += 1
        chat_data["bookings"][message_id]["users"] = users
        payload = {
            chat_id: chat_data
        }
        context.bot_data.update(payload)
        print(context.bot_data) # Important for debugging

        # Notif message for MAX RIDERS reached
        if len(users) >= max_riders:
            await update.callback_query.message.reply_text(MAX_RIDERS_NOTIF_MSG)

    if "cancel" in query: # "Cancel" button clicked
        # Check if user has already booked
        if user not in users:
            print(f"Registration cancellation failed as user has not registered before.")
            return
        
        users.remove(user)

        # Update bot data
        chat_data["bookings"][message_id]['bookings'] -= 1
        chat_data["bookings"][message_id]["users"] = users
        payload = {
            chat_id: chat_data
        }
        context.bot_data.update(payload)
        print(context.bot_data) # Important for debugging

        # If new spaces open up, send a notification message
        if len(users) == max_riders - 1:
            await update.callback_query.message.reply_text(OPEN_SPACES_NOTIF_MSG)

    # Edit the message to show list of users
    await registration_message(context, 
                               chat_id, 
                               message_id = message_id
                               )

BOOK_ID, FUNCTION = range(5, 7)

# @group
# @restricted
async def manage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Select the booking for the following functions: 
     - Close
     - Reopen
     - End
     - Cancel
    """
    chat_id = update.effective_chat.id

    # Send message
    await context.bot.send_message(
        chat_id = chat_id,
        text = MANAGE_MSG
    )

    return BOOK_ID

async def manage_book_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Select the function to use on the booking.
    """
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]
    
    # Get book_id
    book_id = int(update.message.text)

    # Check if book_id is valid
    for i in chat_data["bookings"].keys():
        if chat_data["bookings"][i]["book_id"] == book_id:
            fail = False
    if fail:
        # Send message
        await context.bot.send_message(
            chat_id = chat_id,
            text = INVALID_BOOK_ID_MSG
        )

        return BOOK_ID
    else:
        # Temporarily save book_id selected by user
        context.user_data["book_id"] = book_id
        print(context.user_data)
    
    # Send message
    buttons = [
        [KeyboardButton("Close"),
         KeyboardButton("Reopen")],
        [KeyboardButton("End"),
         KeyboardButton("Cancel")]
    ]
    reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
    await context.bot.send_message(
        chat_id = update.effective_chat.id,
        text = MANAGE_FUNCTIONS_MSG,
        reply_markup = reply_markup
    )
        
    return FUNCTION

async def manage_function(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Executes the function chosen.
    """
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Get book_id's corresponding message_id
    for i in chat_data["bookings"].keys():
        if chat_data["bookings"][i]["book_id"] == context.user_data["book_id"]:
            message_id = i

    # Execute function based on user's selection
    selection = update.message.text
    match selection:
        case "Close":
            await manage_close(update, context, message_id)
        case "Reopen":
            await manage_reopen(update, context, message_id)
        case "End":
            await manage_end(update, context, message_id)
        case "Cancel":
            await manage_cancel(update, context, message_id)

    # Remove book_id selected by user
    del context.user_data["book_id"]
    print(context.user_data)

    return ConversationHandler.END

async def manage_close(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id):
    """
    Close registration for the current day. 
    New riders will not be registered. 
    List of registered users will still be stored.
    """
    chat_id = update.effective_chat.id

    # Remove reply_markup so users cannot register
    await registration_message(context, 
                               chat_id, 
                               message_id=message_id,
                               close=True
                               )
    
    # Notif message
    await context.bot.send_message(chat_id = chat_id,
                                   text = CLOSE_NOTIF_MSG)

async def manage_reopen(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id):
    """
    Reopen registration for the selected booking. New riders can continue being registered.
    """
    chat_id = update.effective_chat.id

    # Add back reply_markup so users can register
    await registration_message(context, 
                               chat_id,
                               message_id=message_id
                               )
    
    # Notif message
    await context.bot.send_message(chat_id = update.effective_chat.id,
                                   text = REOPEN_NOTIF_MSG)

async def manage_end(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id):
    """Ends registration"""
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Get date
    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")
    
    # Remove reply_markup so users cannot reply
    await registration_message(context, 
                               chat_id, 
                               message_id=message_id,
                               close=True
                               )
    
    # Notif message
    await context.bot.send_message(chat_id = chat_id,
                                   text = END_NOTIF_MSG)
    
    # Send tokens
    res = cur.execute(f"SELECT pickup, destination \
                      FROM settings WHERE chat_id={chat_id}")
    data = res.fetchone()
    pickup, destination = data[0], data[1]

    booking_token = f"Your registration for the shuttle bus from \
{pickup} to {destination} for {date} has been confirmed."
    for user in chat_data["bookings"][message_id]["users"]:
        try:
            await context.bot.send_message(
                chat_id = user["id"],
                text = booking_token
            )
        except error as e:
            print(f"Failed to send token to user {user['username']} (id: {user['id']}) as user did not initiate conversation with bot.")
            print(e)
    
    # Update database
    book_id = chat_data["bookings"][message_id]["book_id"]
    bookings = chat_data["bookings"][message_id]["bookings"]
    cur.execute(f"UPDATE ridership SET \
                riders={bookings} \
                WHERE book_id={book_id}")
    con.commit()

    # Delete data
    del chat_data["bookings"][message_id]
    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)
    
async def manage_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id):
    """
    Cancels registration for the selected booking (irreversible).
    """
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Remove button functionality
    await registration_message(context, 
                               chat_id, 
                               message_id = message_id,
                               close=True
                               )

    # Delete data
    del chat_data["bookings"][message_id]
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
async def cancel_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancels automatic registration for the next day
    """
    # TODO: Replace this clause with call of booking cancellation for a range
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")

    # Update overwrite data
    chat_data["overwrite"][date] = False
    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)

    # Notif Message
    await context.bot.send_message(
        chat_id = chat_id,
        text = f"Booking cancelled for {date}"
    )

# @group
# @restricted
async def uncancel_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Uncancels the next day's booking by overwriting the next day to True.
    """
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    dt = datetime.today() + timedelta(1)
    date = dt.strftime("%d %b %y")

    # Update overwrite data
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

async def end_book_job(context: ContextTypes.DEFAULT_TYPE):
    """Ends all registrations"""

    chat_id = context.job.chat_id
    chat_data = context.bot_data[chat_id]

    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")

    res = cur.execute(f"SELECT pickup, destination \
                        FROM settings WHERE chat_id={chat_id}")
    data = res.fetchone()
    pickup, destination = data[0], data[1]

    for message_id in chat_data["bookings"].keys():

        # Remove reply_markup so users cannot reply
        await registration_message(context, 
                                chat_id, 
                                message_id=message_id,
                                close=True
                                )
        
        # Update database
        book_id = chat_data["bookings"][message_id]["bookings"]
        bookings = chat_data["bookings"][message_id]["bookings"]
        cur.execute(f"UPDATE ridership SET \
                    riders={bookings} \
                    WHERE book_id={book_id}")
        con.commit()
            
        # Send tokens
        booking_token = f"Your registration for the shuttle bus from \
{pickup} to {destination} for {date} has been confirmed."
        for user in chat_data["bookings"][message_id]["users"]:
            try:
                await context.bot.send_message(
                    chat_id = user["id"],
                    text = booking_token
                )
            except error as e:
                print(f"Failed to send token to user {user['username']} (id: {user['id']}) as user did not initiate conversation with bot.")
                print(e)

    # Delete data
    chat_data["bookings"] = {}
    payload = {
        chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)

    # Notif message
    await context.bot.send_message(chat_id = chat_id,
                                   text = END_NOTIF_MSG)
    
manage_book_handler = ConversationHandler(
    entry_points = [CommandHandler("manage", manage_command)],
    states = {
        BOOK_ID: [MessageHandler(filters.Regex(r"^[0-9]+$"), manage_book_id),
                  MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        FUNCTION: [MessageHandler(filters.Regex(r"^(Close|Reopen|End|Cancel)$"), manage_function),
                   MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
    },
    fallbacks = [CommandHandler("cancel", cancel_settings)]
)

## BROADCAST / NOTIFICATION
CONFIRM, SENT = range(7, 9) # States for broadcast conversation handler

# @group
# @restricted
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Broadcast a message to every service chat.
    """
    chat_id = update.effective_chat.id
    
    # Send message
    await context.bot.send_message(
        chat_id = chat_id,
        text = BROADCAST_PROMPT_MSG
    )

    return CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Send a message to confirm sending the message.
    """
    chat_id = update.effective_chat.id

    # Send message
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
    """
    Send a confirmation message for the broadcast.
    """
    chat_id = update.effective_chat.id

    message = update.message.text

    if message == "Yes":
        # Notif Message
        await context.bot.send_message(
            chat_id = chat_id,
            text = BROADCAST_SENT_MSG
        )

        res = cur.execute("SELECT chat_id, chat_type FROM settings")
        data = res.fetchall()

        # Send message to every service chat
        for chat in data:
            if chat[1] == "service":
                await context.bot.send_message(
                    chat_id = chat[0],
                    text = context.user_data["broadcast"]
                )

        del context.user_data["broadcast"]
        print(context.user_data)

        return ConversationHandler.END
    
    else: # if message = "No"
        await context.bot.send_message(
            chat_id = chat_id,
            text = BROADCAST_PROMPT_MSG
        )
        return CONFIRM

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a message to indicate broadcast has been cancelled.
    """
    chat_id = update.effective_chat.id

    # Send message
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


### DATA AND STATISTICS
# @group
# @restricted
async def view_data_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a message displaying the ridership stats.
     - Average ridership / day for each service (overall for all bus timings)
    """
    chat_id = update.effective_chat.id

    res = cur.execute("SELECT chat_id FROM settings WHERE chat_type='service'")
    chat_ids = res.fetchall()
    chat_ids = [chat[0] for chat in chat_ids]

    # Get averages for each chat_id
    text = "Average daily riderships across bus services: \n"
    for chat in chat_ids:
        # Get average
        res = cur.execute(f"SELECT date, SUM(riders) FROM ridership WHERE chat_id={chat} GROUP BY date")
        riders = res.fetchall()
        s = sum([r[1] for r in riders])
        l = len(riders)
        avg = s / l

        # Get pickup and destination
        res = cur.execute(f"SELECT pickup, destination FROM settings \
                          WHERE chat_id={chat}")
        data = res.fetchone()
        pickup, destination = data[0], data[1]

        # Add to text
        text = f"{text}\n{pickup} -> {destination}: {avg}"
    
    # Send messages
    await context.bot.send_message(
        chat_id = chat_id,
        text = text
    )


### ERROR
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catches any error and prints it to the command line for debugging."""
    print(f'Update:\n {update}\n caused error:\n {context.error}')


### MAIN
"""
There are two applications running:
 - The Python Telegram Bot application, which handles receiving, processing and sending Telegram updates.
 - The FastAPI application, which sets up the webhook endpoint for Telegram to send updates to.
"""
print('Setting up...') # Logging

# Prepare the database
res = cur.execute("CREATE TABLE IF NOT EXISTS settings (\
                  chat_id INTEGER PRIMARY KEY, \
                  chat_type TEXT NOT NULL, \
                  max_riders INTEGER NOT NULL, \
                  pickup TEXT NOT NULL, \
                  destination TEXT NOT NULL\
                  )") # Create settings table

res = cur.execute("CREATE TABLE IF NOT EXISTS ridership (\
                  book_id INTEGER PRIMARY KEY, \
                  chat_id INTEGER NOT NULL, \
                  date TEXT NOT NULL, \
                  time TEXT NOT NULL, \
                  riders INTEGER NOT NULL\
                  )") # Create ridership table

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
# app = FastAPI(lifespan=lifespan) # Do not run FastAPI code for local dev using polling

# @app.get("/")
# async def index():
#     """Landing page for the bot."""
#     # TODO FUTURE: Add a basic single static page here to explain the bot!
#     return "Hello"

# @app.post("/webhook")
# async def process_update(request: Request):
#     """Updates PTB application when post request received at webhook"""
#     req = await request.json()
#     update = Update.de_json(req, ptb.bot)
#     await ptb.process_update(update)
#     return Response(status_code = HTTPStatus.OK)

# Set up PTB handlers
# Commands (General)
ptb.add_handler(CommandHandler('start', start_command))
ptb.add_handler(CommandHandler('view_settings', view_settings_command))
ptb.add_handler(settings_handler)
ptb.add_handler(CommandHandler('help', help_command))

# Commands (Booking)
ptb.add_handler(CommandHandler('book', book_command))
ptb.add_handler(CallbackQueryHandler(booking_cb_handler, r"^(book|cancel)$")) # Handles callbacks for book command
ptb.add_handler(manage_book_handler)
ptb.add_handler(CommandHandler('cancel_book', cancel_book_command))
ptb.add_handler(CommandHandler('uncancel_book', uncancel_book_command))

# Commands (Broadcasting)
ptb.add_handler(broadcast_handler)
ptb.add_handler(CommandHandler('notify_late', lambda u, c: notify_late(u, c)))
ptb.add_handler(CommandHandler('notify_late_all', lambda u, c: notify_late(u, c, all_chats=True)))

# Commands (Data)
ptb.add_handler(CommandHandler('view_data_summary', view_data_summary_command))

# Messages
# For later development

# Errors
ptb.add_error_handler(error)

# Polling, for dev purposes
print('Polling...')
ptb.run_polling(poll_interval=1, allowed_updates=Update.ALL_TYPES)
    
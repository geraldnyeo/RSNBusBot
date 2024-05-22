"""
Handlers for RSNBusBot
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
    CommandHandler, 
    ConversationHandler, 
    ContextTypes,
    MessageHandler,
    filters
)

import sqlite3

import os
from datetime import datetime, timedelta
from functools import wraps, reduce

from constants import * # Ensure constants.py in same directory

DB_FILEPATH = os.environ['DB_FILEPATH']
PASSWORD = os.environ['PASSWORD']

### HELPER FUNCTIONS
async def get_chat_type(context, chat_id):
    """
    Helper function to get the chat type. 
    Checks if chat is one-on-one or group, then checks if chat is admin/service (for groups).
    Returns "user", "service" or "admin".
    """
    chat = await context.bot.get_chat(chat_id)
    if chat.title == None: # one-on-one
        return "user"
    else:
        con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
        cur = con.cursor()

        res = cur.execute(f"SELECT chat_type FROM settings \
                          WHERE chat_id={chat_id}")
        chat_type = res.fetchone()[0]

        con.close()
        return chat_type.lower()

def permissions_factory(req_type):
    """
    Decorator for commands which can only be run in a group chat, not private chat.
    """
    def permissions(func):
        @wraps(func)
        async def wrapped(update, context, *args, **kwargs):
            chat_id = update.effective_chat.id
            chat_type = await get_chat_type(context, chat_id)

            if chat_type in req_type:
                return await func(update, context, *args, **kwargs)
            else:
                print(f"Command failed as attempted to run in incorrect chat type.")
                return

        return wrapped
    return permissions

def restricted(func):
    """
    Defines decorator which marks commands as restricted.
    Restricted commands can only be run by the group admins.
    """
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

# Password conversation lock
PW = 1000
async def password(update: Update, context: ContextTypes.DEFAULT_TYPE, state, text):
    """
    Password protection for certain commands
    """
    chat_id = update.effective_chat.id

    pw = update.message.text
    if pw != PASSWORD:
        await context.bot.send_message(
            chat_id = chat_id,
            text = CONVERSATION_INVALID_PASSWORD_MSG
        )

        return ConversationHandler.END

    await context.bot.send_message(
        chat_id = chat_id,
        text = text
    )

    return state

# Invalid response catcher
async def invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Invalid response catcher for all Conversation Handlers
    """
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id = chat_id,
        text = CONVERSATION_INVALID_MSG,
    )

# Cancel conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancel fallback function for all Conversation Handlers
    """
    chat_id = update.effective_chat.id

    # Send message
    await context.bot.send_message(
        chat_id = chat_id,
        text = CONVERSATION_CANCEL_MSG,
        reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END

# Timeout converasation
async def timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Timeout function for all Conversation Handlers
    """
    chat_id = update.effective_chat.id

    # Send message
    await context.bot.send_message(
        chat_id = chat_id,
        text = CONVERSATION_TIMEOUT_MSG,
        reply_markup=ReplyKeyboardRemove()
    )

# Clean the schedule table
async def clean_schedule(bus_ids = None):
    """
    Organise the schedule so that repeats are avoided.
    """
    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Get all bus IDs
    if bus_ids == None:
        res = cur.execute("SELECT bus_id FROM buses")
        bus_ids = [i[0] for i in bus_ids]

    for bus_id in bus_ids:
        # Get current schedule for bus ID
        res = cur.execute(f"SELECT start_date, end_date, status FROM schedule \
                                WHERE bus_id={bus_id}")
        schedule = res.fetchall()
        dates_sorted = []
        for i in schedule:
            dt_format = [datetime.strptime(i[0], '%d%m%y'), \
                         datetime.strptime(i[1], '%d%m%y'), \
                        i[2]]
            
            if len(dates_sorted) == 0:
                dates_sorted.append(dt_format)
                continue

            j = 0
            flag = False
            while j < len(dates_sorted):
                entry = dates_sorted[j]

                # overlaps at start
                if dt_format[0] <= entry[0]  and dt_format[1] >= entry[0]:
                    # envelopes
                    if dt_format[1] >= entry[1]:
                        # print("Envelopes")
                        del dates_sorted[j]
                        j -= 1
                    
                    # does not envelope
                    else:
                        if dt_format[2] == entry[2]:
                            # print("Overlap start, same function")
                            dates_sorted[j][0] = dt_format[0]
                        else:
                            # print("Overlap start, swap function")
                            dates_sorted.insert(j, dt_format)
                            dates_sorted[j + 1][0] = dt_format[1] + timedelta(days = 1)

                        flag = True
                        break

                # overlaps at end
                elif dt_format[0] < entry[1] and dt_format[1] >= entry[1]:
                    if dt_format[2] == entry[2]:
                        # print("Overlap end, same function")
                        dt_format[0] = entry[0]
                        del dates_sorted[j]
                        j -= 1
                    else:
                        # print("Overlap end, swap function")
                        dates_sorted[j][1] = dt_format[0] - timedelta(days = 1)

                j += 1

            if not flag:
                dates_sorted.append(dt_format)

        # Update the table
        cur.execute(f"DELETE FROM schedule WHERE bus_id={bus_id}")
        con.commit()
        
        today = datetime.now()
        for i in dates_sorted:
            if today.date() > i[1].date(): # end date exceeded
                continue

            start, end = i[0].strftime('%d%m%y'), i[1].strftime('%d%m%y')
            cur.execute(f"INSERT INTO schedule VALUES \
                        ( \
                            {bus_id}, \
                            '{start}', \
                            '{end}', \
                            {i[2]} \
                        )")
            con.commit()
        
        con.close()


### COMMANDS
## GENERAL / SETTINGS
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    For Users:
    Introduce the bot to users, and allows them to receive their token. 

    For Groups:
    Introduce the bot to users, and sets up data saving:
     - Database Configuration
     - Setup Ephermeral Data (context.bot_data)
    """
    chat_id = update.effective_chat.id

    # Message for Users
    chat = await context.bot.get_chat(chat_id)
    if chat.title == None:
        # Send introduction message
        await context.bot.send_message(
            chat_id = chat_id,
            text = USER_START_MSG,
            reply_markup = ReplyKeyboardRemove() # Remove any unwanted keyboards on start
        )
        return
    
    # Return if unauthorised member attempts to start
    chat_admins = await update.effective_chat.get_administrators()
    user = update.effective_user
    if user not in (admin.user for admin in chat_admins):
        print(f"Unauthorized access denied for {user.username}")
        return
    
    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Add new row for chat into database if required
    # Check if chat has been initialized for settings table
    res = cur.execute(f"SELECT EXISTS (SELECT 1 FROM settings WHERE chat_id={chat_id})")
    exists = res.fetchone()
    exists = exists[0]

    # Initialize settings
    if not exists:
        # New entry for settings
        cur.execute(f"INSERT INTO settings VALUES \
                    ({chat_id}, 'Service', {DEFAULT_MAX_RIDERS}, '', '')")
        con.commit()

        # New entries for buses
        res = cur.execute(f"SELECT MAX(bus_id) FROM buses")
        bus_id = res.fetchone()[0]
        if bus_id == None:
            bus_id = -1
        cur.execute(f"INSERT INTO buses VALUES \
                    ({bus_id + 1}, {chat_id}, '0630'), \
                    ({bus_id + 2}, {chat_id}, '0645')")
        con.commit()

    con.close()

    # Setup automatic processes and chat_data
    if chat_id not in context.bot_data.keys():
        # Initialise the message data structure which the bot will be using.
        payload = {
            chat_id: { # TODO: Swap to using chat_data rather than bot_data
                "initialized": False,
                "bookings": {},
            }
        }
        context.bot_data.update(payload)
        print(context.bot_data)

    # Send introduction message
    await context.bot.send_message(
        chat_id = chat_id,
        text = START_MSG,
        reply_markup = ReplyKeyboardRemove() # Remove any unwanted keyboards on start
    )

    # TODO: Setup constants conversation handler

@permissions_factory("user | service | admin")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Inform the user about the bot's available commands.
    """
    chat_id = update.effective_chat.id

    # Message for Users
    chat = await context.bot.get_chat(chat_id)
    if chat.title == None:
        await context.bot.send_message(
            chat_id = chat_id,
            text = USER_HELP_MSG,
        )
        return

    # Message for Groups
    await update.message.send_message(
        HELP_MSG
    )

@permissions_factory("admin | service")
@restricted
async def view_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows users the current settings.
    """
    chat_id = update.effective_chat.id

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Get database data
    res = cur.execute(f"SELECT max_riders, pickup, destination, chat_type \
                      FROM settings WHERE chat_id={chat_id}")
    settings_data = res.fetchone()
    if settings_data is None:
        print("Unable to retrieve data from database.")
        con.close()
        return
    
    res = cur.execute(f"SELECT bus_id, time FROM buses WHERE chat_id={chat_id}")
    bus_data = res.fetchall()

    con.close()

    # Prepare message
    text = f"{VIEW_SETTINGS_MSG}\nChat ID: {chat_id}"
    settings = ["Max Riders", "Pickup", "Destination", "Chat Type"]
    for i in range(len(settings)):
        text = f"{text}\n{settings[i]}: {settings_data[i]}"
    text = f"{text}\n\nBuses:"
    for i in bus_data:
        text = f"{text}\n - {i[0]}: {i[1]}H"
    
    # Send message
    await context.bot.send_message(
        chat_id = chat_id,
        text = text
    )

SELECT, RIDERS, PICKUP, DESTINATION, CHAT, BUSES = range(0, 6) # states for settings conversation handler

@permissions_factory("admin | service")
@restricted
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Settings Menu
    """
    # Send nessage
    buttons = [
        [KeyboardButton("Max Riders"),
         KeyboardButton("Pickup Location"),
         KeyboardButton("Destination")],
        [KeyboardButton("Chat Type"),
         KeyboardButton("Buses")]
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
        case "Buses":
            await context.bot.send_message(
                chat_id = chat_id,
                text = BUSES_SETTING_MSG,
            )
            return BUSES
        
async def settings_update(update: Update, context: ContextTypes.DEFAULT_TYPE, setting, value):
    """
    Update settings and prompts user to select another setting.
    """
    chat_id = update.effective_chat.id

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Update database
    if type(value) == str: # add quotes to denote string in SQL
        value = f"'{value}'"

    cur.execute(f"UPDATE settings SET \
                {setting}={value} \
                WHERE chat_id={chat_id}")
    con.commit()

    con.close()

    # Send message
    await context.bot.send_message(
        chat_id = chat_id,
        text = UPDATED_SETTINGS_MSG,
        reply_markup = ReplyKeyboardRemove()
    )

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

async def settings_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for chat type"""
    chat_id = update.effective_chat.id

    await settings_update(update, context, "chat_type", update.message.text)
    
    # Remove buses for admin chats
    if update.message.text == "Admin":
        # Connect to DB
        con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
        cur = con.cursor()

        cur.execute(f"DELETE FROM buses WHERE chat_id={chat_id}")
        con.commit()

        con.close()

    return SELECT

async def settings_buses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings for bus timings"""
    chat_id = update.effective_chat.id

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Get data from database
    res = cur.execute(f"SELECT time FROM buses WHERE chat_id = {chat_id}")
    current_buses = res.fetchall()
    current_buses = list(map(lambda x: x[0], current_buses))

    res = cur.execute(f"SELECT MAX(bus_id) FROM buses")
    bus_id = res.fetchone()[0]
    if bus_id == None:
        bus_id = -1

    buses = update.message.text.split("\n")

    # Update database
    new_buses = list(set(buses) - set(current_buses))
    for bus in new_buses: # Add new buses
        cur.execute(f"INSERT INTO buses VALUES \
                    ({bus_id + 1}, {chat_id}, '{bus}')")
        con.commit()
        bus_id += 1
    old_buses = list(set(current_buses) - set(buses))
    for bus in old_buses: # Remove old buses
        cur.execute(f"DELETE FROM buses \
                    WHERE chat_id = {chat_id} \
                    AND time = '{bus}'")
        con.commit()

    con.close()

    # Send message
    await context.bot.send_message(
        chat_id = chat_id,
        text = UPDATED_SETTINGS_MSG,
        reply_markup = ReplyKeyboardRemove()
    )

    return SELECT

settings_handler = ConversationHandler(
    entry_points=[CommandHandler("settings", settings_command)],
    states = {
        SELECT: [MessageHandler(filters.Regex(r"^(Max Riders|Pickup Location|Destination|Chat Type|Buses)$"), settings_select),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        RIDERS: [MessageHandler(filters.Regex(r"^[0-9]+$"), settings_riders),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        PICKUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_pickup),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_destination),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        CHAT: [MessageHandler(filters.Regex(r"^(Admin|Service)$"), settings_chat),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        BUSES: [MessageHandler(filters.Regex(r"^(([01]\d|2[0-3])([0-5]\d))(\n([01]\d|2[0-3])([0-5]\d))*$"), settings_buses),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)],
    },
    fallbacks = [CommandHandler("cancel", cancel)],
    conversation_timeout = 60,
)

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

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

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
        res = cur.execute("SELECT MAX(book_id) FROM ridership")
        book_id = res.fetchone()[0]
        if book_id == None:
            book_id = 0
        else:
            book_id = book_id + 1
    else:
        book_id = chat_data["bookings"][message_id]["book_id"]

    con.close()

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

@permissions_factory("service")
@restricted
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

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Update database
    cur.execute(f"INSERT INTO ridership VALUES \
                ({book_id}, {chat_id}, '{date}', '{t}', 0)")
    con.commit()

    con.close()

async def booking_cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Updates the bot once user has clicked certain options of the booking message.
    """
    query = update.callback_query.data
    message_id = update.callback_query.message.message_id
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Get max_riders from database
    res = cur.execute(f"SELECT max_riders \
                      FROM settings WHERE chat_id={chat_id}")
    data = res.fetchone()
    max_riders = data[0]

    con.close()
    
    # Get user information
    user = {
        'username': update.callback_query.from_user.username,
        'id': update.callback_query.from_user.id
    }
    users = chat_data["bookings"][message_id]['users']
    all_users = reduce(lambda l, msg: l + msg["users"], chat_data["bookings"].values(), [])

    # Handle the callback
    if "book" in query: # "Book" button clicked
        # Check if max users have been reached
        if len(users) == max_riders:
            print(f"Registration failed as maximum number of riders have registered.")
            return
        # Check if user has already booked
        if user in all_users:
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

BOOK_ID, FUNCTION = range(6, 8)

@permissions_factory("admin")
@restricted
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
    
    # Get book_id
    book_id = int(update.message.text)

    # Check if book_id is valid
    target_chat_id = None
    for i, chat in context.bot_data.items():
        for j in chat["bookings"].keys():
            if chat["bookings"][j]["book_id"] == book_id:
                target_chat_id = i
    if target_chat_id == None:
        # Send message
        await context.bot.send_message(
            chat_id = chat_id,
            text = INVALID_BOOK_ID_MSG
        )

        return BOOK_ID
    else:
        # Temporarily save book_id selected by user
        context.user_data["book_id"] = book_id
        context.user_data["target_chat_id"] = target_chat_id
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
        chat_id = chat_id,
        text = MANAGE_FUNCTIONS_MSG,
        reply_markup = reply_markup
    )
        
    return FUNCTION

async def manage_function(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Executes the function chosen.
    """
    # Get book_id's corresponding message_id
    target_chat_id = context.user_data["target_chat_id"]
    bookings = context.bot_data[target_chat_id]["bookings"]
    for i in bookings.keys():
        if bookings[i]["book_id"] == context.user_data["book_id"]:
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
    del context.user_data["target_chat_id"]
    print(context.user_data)

    return ConversationHandler.END

async def manage_close(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id):
    """
    Close registration for the current day. 
    New riders will not be registered. 
    List of registered users will still be stored.
    """
    target_chat_id = context.user_data["target_chat_id"]

    # Remove reply_markup so users cannot register
    await registration_message(context, 
                               target_chat_id, 
                               message_id=message_id,
                               close=True
                               )
    
    # Notif message
    await context.bot.send_message(
        chat_id = target_chat_id,
        text = CLOSE_NOTIF_MSG,
        reply_markup = ReplyKeyboardRemove()
    )

async def manage_reopen(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id):
    """
    Reopen registration for the selected booking. New riders can continue being registered.
    """
    target_chat_id = context.user_data["target_chat_id"]

    # Add back reply_markup so users can register
    await registration_message(context, 
                               target_chat_id,
                               message_id=message_id
                               )
    
    # Notif message
    await context.bot.send_message(
        chat_id = target_chat_id,
        text = REOPEN_NOTIF_MSG,
        reply_markup = ReplyKeyboardRemove(),
    )

async def manage_end(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id):
    """Ends registration"""
    target_chat_id = context.user_data["target_chat_id"]
    chat_data = context.bot_data[target_chat_id]

    # Get date
    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")
    
    # Remove reply_markup so users cannot reply
    await registration_message(context, 
                               target_chat_id, 
                               message_id=message_id,
                               close=True
                               )
    
    # Notif message
    await context.bot.send_message(
        chat_id = target_chat_id,
        text = END_NOTIF_MSG,
        reply_markup = ReplyKeyboardRemove()
    )
    
    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()
    
    # Send tokens
    res = cur.execute(f"SELECT pickup, destination \
                      FROM settings WHERE chat_id={target_chat_id}")
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
        except Exception as e:
            print(f"Failed to send token to user {user['username']} (id: {user['id']}) as user did not initiate conversation with bot.")
            print(e)
    
    # Update database
    book_id = chat_data["bookings"][message_id]["book_id"]
    bookings = chat_data["bookings"][message_id]["bookings"]
    cur.execute(f"UPDATE ridership SET \
                riders={bookings} \
                WHERE book_id={book_id}")
    con.commit()

    con.close()

    # Delete data
    del chat_data["bookings"][message_id]
    payload = {
        target_chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)
    
async def manage_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id):
    """
    Cancels registration for the selected booking (irreversible).
    """
    target_chat_id = context.user_data["target_chat_id"]
    chat_data = context.bot_data[target_chat_id]

    # Remove button functionality
    await registration_message(context, 
                               target_chat_id, 
                               message_id = message_id,
                               close=True
                               )
    
    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()
    
    # Update database
    book_id = chat_data["bookings"][message_id]["book_id"]
    cur.execute(f"DELETE FROM ridership \
                WHERE book_id={book_id}")
    con.commit()

    con.close()

    # Delete data
    del chat_data["bookings"][message_id]
    payload = {
        target_chat_id: chat_data
    }
    context.bot_data.update(payload)
    print(context.bot_data)

    # Notif message
    await context.bot.send_message(
        chat_id = target_chat_id,
        text = CANCEL_NOTIF_MSG,
        reply_markup = ReplyKeyboardRemove()
    )

manage_book_handler = ConversationHandler(
    entry_points = [CommandHandler("manage", manage_command)],
    states = {
        BOOK_ID: [MessageHandler(filters.Regex(r"^[0-9]+$"), manage_book_id),
                  MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        FUNCTION: [MessageHandler(filters.Regex(r"^(Close|Reopen|End|Cancel)$"), manage_function),
                   MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)],
    },
    fallbacks = [CommandHandler("cancel", cancel)],
    conversation_timeout = 60,
)

@permissions_factory("service")
@restricted
async def cancel_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancels automatic registration for the next day
    """
    # TODO: Replace this clause with call of booking cancellation for a range
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")

    # Connect to DB schedule
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Fetch all bus_ids
    res = cur.execute("SELECT bus_id FROM buses \
                      WHERE chat_id={chat_id}")
    bus_ids = res.fetchall()
    bus_ids = [i[0] for i in bus_ids]

    # Add schedule entries
    for i in bus_ids:
        cur.execute(f"INSERT INTO schedule VALUES \
                    ({i}, '{date}', '{date}', 0)")
        con.commit()
    
    con.close()

    # Clean schedule
    await clean_schedule()

    # Notif Message
    text = f"Booking cancelled for {date}"
    await context.bot.send_message(
        chat_id = chat_id,
        text = text
    )

@permissions_factory("service")
@restricted
async def uncancel_book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Uncancels the next day's booking by overwriting the next day to True.
    """
    chat_id = update.effective_chat.id
    chat_data = context.bot_data[chat_id]

    dt = datetime.today() + timedelta(1)
    date = dt.strftime("%d %b %y")

    # Connect to DB schedule
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Fetch all bus_ids
    res = cur.execute("SELECT bus_id FROM buses \
                      WHERE chat_id={chat_id}")
    bus_ids = res.fetchall()
    bus_ids = [i[0] for i in bus_ids]

    # Add schedule entries
    for i in bus_ids:
        cur.execute(f"INSERT INTO schedule VALUES \
                    ({i}, '{date}', '{date}', 1)")
        con.commit()
    
    con.close()

    # Clean schedule
    await clean_schedule()

    # Notif Message
    text = f"Booking uncancelled for {date}"
    await context.bot.send_message(
        chat_id = chat_id,
        text = text
    )


BUS_ID_VIEW = 8

@permissions_factory("admin")
@restricted
async def view_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    View the schedule for the bus
    """
    chat_id = update.effective_chat.id

    await context.bot.send_message(
        chat_id = chat_id,
        text = VIEW_SCHEDULE_MSG,
    )

    return BUS_ID_VIEW

async def view_schedule_bus_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows the schedule for the selected bus ID
    """
    chat_id = update.effective_chat.id

    # Get the bus ID
    bus_id = int(update.message.text)

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Get schedule
    res = cur.execute(f"SELECT start_date, end_date, status FROM schedule \
                      WHERE bus_id={bus_id}")
    schedule = res.fetchall()

    con.close()

    # Print the message
    text = f"Here is the schedule for bus {bus_id}:\n"
    for i in schedule:
        status = "RUNNING"
        if i[2] == 1:
            status = "CANCELLED"
        if i[0] == i[1]:
            text = f"{text}\n{i[0]} {status}"
        else:
            text = f"{text}\n{i[0]}-{i[1]} {status}"
    
    await context.bot.send_message(
        chat_id = chat_id,
        text = text
    )

    return ConversationHandler.END

view_schedule_handler = ConversationHandler(
    entry_points = [CommandHandler("view_schedule", view_schedule_command)],
    states = {
        BUS_ID_VIEW: [MessageHandler(filters.Regex(r"^[0-9]$"), view_schedule_bus_id),
                      MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)]
    },
    fallbacks = [CommandHandler("cancel", cancel)],
    conversation_timeout = 60
)

BUS_ID, OVERWRITE, DATES = range(9, 12)

@permissions_factory("admin")
@restricted
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancel / book buses for selected periods
    Selects bus ID to schedule
    """
    chat_id = update.effective_chat.id

    await context.bot.send_message(
        chat_id = chat_id,
        text = SCHEDULE_MSG,
    )

    return BUS_ID

async def schedule_bus_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Selects function to overwrite with - cancel (0) / book (1)
    """
    chat_id = update.effective_chat.id 

    # Get the bus id
    bus_id = int(update.message.text)

    # Check whether bus id is valid
    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Get all bus ids
    res = cur.execute("SELECT bus_id FROM buses")
    bus_ids = res.fetchall()
    bus_ids = [i[0] for i in bus_ids]

    con.close()

    if bus_id not in bus_ids:
        await context.bot.send_message(
            chat_id = chat_id,
            text = INVALID_BUS_ID_MSG
        )

        return BUS_ID
    
    context.user_data["bus_id"] = bus_id
    print(context.user_data)
    
    buttons = [[
        KeyboardButton("Book"),
        KeyboardButton("Cancel")
    ]]
    reply_markup = ReplyKeyboardMarkup(buttons)
    await context.bot.send_message(
        chat_id = chat_id,
        text = SCHEDULE_FUNCTION_MSG,
        reply_markup = reply_markup
    )

    return OVERWRITE

async def schedule_function(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Gets the date ranges for the forced booking / cancellation.
    """
    chat_id = update.effective_chat.id

    selection = update.message.text
    context.user_data["overwrite"] = selection
    print(context.user_data)

    await context.bot.send_message(
        chat_id = chat_id,
        text = SCHEDULE_DATES_MSG,
        reply_markup = ReplyKeyboardRemove()
    )
    
    return DATES

async def schedule_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Updates the schedule table.
    """
    chat_id = update.effective_chat.id

    dates = update.message.text
    date_ranges = dates.split("\n")

    # Get previous conversation choices
    bus_id = context.user_data["bus_id"]
    overwrite = context.user_data["overwrite"]

    status = None
    if overwrite == "Book":
        status = 0
    elif overwrite == "Cancel":
        status = 1

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    for i in date_ranges:
        if "-" in i: # range
            date_range = i.split("-")
            start_date, end_date = date_range[0], date_range[1]
            try:
                start = datetime.strptime(date_range[0], "%d%m%y")
                end = datetime.strptime(date_range[1], "%d%m%y")
                if start >= end:
                    await context.bot.send_message(
                        chat_id = chat_id,
                        text = INVALID_SCHEDULE_DATE_MSG
                    )
                    return DATES
            except Exception:
                await context.bot.send_message(
                        chat_id = chat_id,
                        text = INVALID_SCHEDULE_DATE_MSG
                )
                return DATES
            cur.execute(f"INSERT INTO schedule VALUES \
                        ({bus_id}, '{start_date}', '{end_date}', {status})")
            con.commit()
        else: # single
            try:
                date = datetime.strptime(i, "%d%m%y")
            except Exception:
                await context.bot.send_message(
                        chat_id = chat_id,
                        text = INVALID_SCHEDULE_DATE_MSG
                )
                return DATES
            cur.execute(f"INSERT INTO schedule VALUES \
                        ({bus_id}, '{i}', '{i}', {status})")
            con.commit()

    con.close()

    await clean_schedule(bus_ids = [bus_id])

    await context.bot.send_message(
        chat_id = chat_id,
        text = UPDATED_SCHEDULE_MSG
    )

    del context.user_data["bus_id"]
    del context.user_data["overwrite"]
    print(context.user_data)

    return ConversationHandler.END

schedule_handler = ConversationHandler(
    entry_points = [CommandHandler("schedule", schedule_command)],
    states = {
        BUS_ID: [MessageHandler(filters.Regex(r"^[0-9]+$"), schedule_bus_id),
                MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        OVERWRITE: [MessageHandler(filters.Regex(r"^(Book|Cancel)$"), schedule_function),
                    MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        DATES: [MessageHandler(filters.Regex(r"^(((0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(\d{2}))(-((0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(\d{2})))*)(\n((0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(\d{2}))(-((0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(\d{2})))*)*$"), schedule_dates),
                MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)]},
    fallbacks = [CommandHandler("cancel", cancel)],
    conversation_timeout = 60
)

async def daily_booking(context: ContextTypes.DEFAULT_TYPE):
    """
    Initiates / cancels daily booking for all chats.
    Cleans up the schedule.
    """
    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Get all buses to send booking messages for
    res = cur.execute("SELECT bus_id, chat_id, time FROM buses")
    buses = res.fetchall()

    date = datetime.today() + timedelta(1)
    
    for bus in buses:
        bus_id, chat_id, t = bus[0], bus[1], bus[2]

        if chat_id not in context.bot_data.keys():
            print(f"Unable to send bookings messages to chat {chat_id} as bot was not started.")
            continue

        # Check for any overwrites
        res = cur.execute(f"SELECT start_date, end_date, status FROM schedule \
                          WHERE bus_id={bus_id}")
        overwrites = res.fetchall()

        flag = False
        for i in overwrites:
            start_date, end_date, status = datetime.strptime(i[0], "%d%m%y"), datetime.strptime(i[1], "%d%m%y"), i[2]
            if date.date() >= start_date.date() and date.date() <= end_date.date():
                print(status)
                if status == 0:
                    await book_job(context, chat_id, t)
                else:
                    print(False)
                    await context.bot.send_message( # TODO: Error message says the bus time will not be running
                        chat_id = chat_id,
                        text = f"Dear all, bus {bus_id} will not be running tomorrow." # OVERWRITE_FALSE_MSG
                    )

                flag = True
                break

        if flag:
            continue
              
        # Check for weekends
        day = date.weekday()
        if day == 5 or day == 6: # Don't send if the next day is Sat or Sun
            return
        
        # Send if it's a regular day
        await book_job(context, chat_id, t)

    con.close()

    # Clean the schedule
    await clean_schedule()

async def book_job(context: ContextTypes.DEFAULT_TYPE, chat_id, t):
    """
    Sends a message to book shuttle bus slots for a day.
    """
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

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Update database
    cur.execute(f"INSERT INTO ridership VALUES \
                ({book_id}, {chat_id}, '{date}', '{t}', 0)")
    con.commit()

    con.close()

async def end_book_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Ends all registrations
    """
    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Get all chats to send booking messages for
    res = cur.execute("SELECT chat_id, pickup, destination, chat_type FROM settings")
    chats = res.fetchall()

    date = datetime.today() + timedelta(1)
    date = date.strftime("%d %b %y")

    for chat in chats:
        chat_id, pickup, destination, chat_type = chat[0], chat[1], chat[2], chat[3]
        chat_data = context.bot_data[chat_id]

        if chat_type == "Admin":
            continue

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
            booking_token = f"Your registration for the shuttle bus from {pickup} to {destination} for {date} has been confirmed."
            for user in chat_data["bookings"][message_id]["users"]:
                try:
                    await context.bot.send_message(
                        chat_id = user["id"],
                        text = booking_token
                    )
                except Exception as e:
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
        
    con.close()
    
## BROADCAST / NOTIFICATION
CONFIRM, SENT = range(12, 14) # States for broadcast conversation handler

@permissions_factory("admin")
@restricted
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
        
        # Connect to DB
        con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
        cur = con.cursor()

        res = cur.execute("SELECT chat_id, chat_type FROM settings")
        data = res.fetchall()

        con.close()

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

broadcast_handler = ConversationHandler(
    entry_points=[CommandHandler("broadcast", broadcast_command)],
    states = {
        CONFIRM: [MessageHandler(filters.TEXT &~filters.COMMAND, broadcast_confirm),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        SENT: [MessageHandler(filters.Regex(r"^(Yes|No)$"), broadcast_sent),
                 MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)],
    },
    fallbacks = [CommandHandler("cancel", cancel)],
    conversation_timeout = 60,
)

@permissions_factory("admin | service")
@restricted
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
@permissions_factory("admin")
@restricted
async def view_data_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a message displaying the ridership stats.
     - Average ridership / day for each service (overall for all bus timings)
    """
    chat_id = update.effective_chat.id

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    res = cur.execute("SELECT chat_id FROM settings WHERE chat_type='service'")
    chat_ids = res.fetchall()
    chat_ids = [chat[0] for chat in chat_ids]

    # Get averages for each chat_id
    text = "Average daily riderships across bus services: \n"
    for chat in chat_ids:
        # Get average
        res = cur.execute(f"SELECT date, SUM(riders) FROM ridership WHERE chat_id={chat} GROUP BY date")
        riders = res.fetchall()

        if len(riders) == 0:
            avg = 0
        else:
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

    con.close()
    
    # Send messages
    await context.bot.send_message(
        chat_id = chat_id,
        text = text
    )

QUERY = 14

@permissions_factory("admin")
@restricted
async def edit_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Allows direct access to DB through sql commands
    Only give access to certain members of admin
    """
    chat_id = update.effective_chat.id

    await context.bot.send_message(
        chat_id = chat_id,
        text = CONVERSATION_ENTER_PASSWORD_MSG
    )

    return PW

async def edit_db_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Executes whatever command is entered by the user, so
    DO NOT USE THIS FUNCTION UNLESS ABSOLUTELY NECESSARY
    """
    chat_id = update.effective_chat.id

    query = update.message.text

    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Attempt to execute
    try:
        res = cur.execute(query)
        con.commit()
        response = res.fetchall()
    except Exception as e:
        response = str(e)
    
    con.close()

    # Output
    await context.bot.send_message(
        chat_id = chat_id,
        text = response
    )

    return ConversationHandler.END


edit_db_handler = ConversationHandler(
    entry_points = [CommandHandler("edit_db", edit_db_command)],
    states = {
        PW: [MessageHandler(filters.TEXT, lambda u, c: password(u, c, QUERY, EDIT_DB_MSG)),
                MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        QUERY: [MessageHandler(filters.TEXT, edit_db_query),
                MessageHandler(filters.ALL & ~filters.COMMAND, invalid)],
        ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)]
    },
    fallbacks = [CommandHandler("cancel", cancel)],
    conversation_timeout = 60
)


### OTHER EVENTS
async def migrate_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles migrations to another chat
    """
    old_chat_id = update.message.migrate_from_chat_id
    new_chat_id = update.message.chat.id

    if old_chat_id == None: # Update for migration TO chat, not FROM chat
        return
    
    # Connect to DB
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db")
    cur = con.cursor()

    # Update databases
    cur.execute(f"UPDATE settings SET chat_id={new_chat_id} \
                WHERE chat_id={old_chat_id}")
    con.commit()

    cur.execute(f"UPDATE buses SET chat_id={new_chat_id} \
                WHERE chat_id={old_chat_id}")
    con.commit()

    cur.execute(f"UPDATE ridership SET chat_id={new_chat_id} \
                WHERE chat_id={old_chat_id}")
    con.commit()

    cur.execute(f"UPDATE schedule SET chat_id={new_chat_id} \
                WHERE chat_id={old_chat_id}")
    con.commit()

    con.close()

    # Update bot_data
    context.bot_data[new_chat_id] = context.bot_data[old_chat_id]
    del context.bot_data[old_chat_id]
    print(context.bot_data)


### ERROR
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catches any error and prints it to the command line for debugging."""
    print(f'Update:\n {update}\n caused error:\n {context.error}')
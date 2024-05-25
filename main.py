"""
RSNBusBot v1.2.1
"""

### IMPORTS
from telegram import (
    Update, 
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler,
    MessageHandler,
    filters
)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from http import HTTPStatus

import os
from datetime import time
import pytz

from setup import * # Ensure setup.py in same directory
from handlers import * # Ensure handlers.py in same directory

### CONSTANTS
# Environment Variables
TOKEN = os.environ['TOKEN']
BOT_USERNAME = os.environ['BOT_USERNAME']
TIMEZONE = os.environ['TIMEZONE']

### MAIN
"""
There are two applications running:
 - The Python Telegram Bot application, which handles receiving, processing and sending Telegram updates.
 - The FastAPI application, which sets up the webhook endpoint for Telegram to send updates to.
"""
setup_db()

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
ptb.add_handler(manage_book_handler)
ptb.add_handler(CommandHandler('cancel_book', cancel_book_command))
ptb.add_handler(CommandHandler('uncancel_book', uncancel_book_command))

# Commands (Scheduling)
ptb.add_handler(view_schedule_handler)
ptb.add_handler(schedule_handler)

# Commands (Broadcasting)
ptb.add_handler(broadcast_handler)
ptb.add_handler(CommandHandler('notify_late', lambda u, c: notify_late(u, c)))
ptb.add_handler(CommandHandler('notify_late_all', lambda u, c: notify_late(u, c, all_chats=True)))

# Commands (Data)
ptb.add_handler(CommandHandler('view_data_summary', view_data_summary_command))
ptb.add_handler(edit_db_handler)

# Messages
# For later development

# Other Events
ptb.add_handler(MessageHandler(filters.StatusUpdate.MIGRATE, migrate_chat))

# Errors
ptb.add_error_handler(error)

# Automatic Processes
ptb.job_queue.run_daily(daily_booking,
                        time=time(hour=17, minute=30, second=0, tzinfo=pytz.timezone(TIMEZONE)), 
                        days=(0, 1, 2, 3, 4, 5, 6)) # MUST be 0 to 6 to work
ptb.job_queue.run_daily(end_book_job,
                        time=time(hour=22, minute=00, second=00, tzinfo=pytz.timezone(TIMEZONE)),
                        days=(0, 1, 2, 3, 4, 5, 6))

# Polling, for dev purposes
# print('Polling...')
# ptb.run_polling(poll_interval=1, allowed_updates=Update.ALL_TYPES)
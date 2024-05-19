"""
Setup for RSNBusBot
"""

import sqlite3

import os

DB_FILEPATH = os.environ['DB_FILEPATH']

def setup_db():
    con = sqlite3.connect(f"{DB_FILEPATH}/rsnbusbot.db") 
    cur = con.cursor()

    print('Setting up...') # Logging

    # Prepare the database
    res = cur.execute("CREATE TABLE IF NOT EXISTS settings (\
                    chat_id INTEGER PRIMARY KEY, \
                    chat_type TEXT NOT NULL, \
                    max_riders INTEGER NOT NULL, \
                    pickup TEXT NOT NULL, \
                    destination TEXT NOT NULL\
                    )") # Create settings table

    res = cur.execute("CREATE TABLE IF NOT EXISTS buses (\
                    bus_id INTEGER PRIMARY KEY, \
                    chat_id INTEGER NOT NULL, \
                    time TEXT NOT NULL \
                    )") # Create buses table

    res = cur.execute("CREATE TABLE IF NOT EXISTS ridership (\
                    book_id INTEGER PRIMARY KEY, \
                    chat_id INTEGER NOT NULL, \
                    date TEXT NOT NULL, \
                    time TEXT NOT NULL, \
                    riders INTEGER NOT NULL\
                    )") # Create ridership table
    
    res = cur.execute("CREATE TABLE IF NOT EXISTS schedule (\
                      bus_id INTEGER NOT NULL, \
                      start_date TEXT NOT NULL, \
                      end_date TEXT NOT NULL, \
                      status INTEGER NOT NULL\
                      )") # Create schedule table
    
    con.close()
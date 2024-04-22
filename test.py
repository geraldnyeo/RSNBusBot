import sqlite3

con = sqlite3.connect("rsnbusbot.db")
cur = con.cursor()

def get():
    print("SETTINGS")
    res = cur.execute("SELECT * FROM settings")
    print(res.fetchall())

    print("")

    print("RIDERSHIP")
    res = cur.execute("SELECT * FROM ridership")
    print(res.fetchall())

    print("")

    print("BUSES")
    res = cur.execute("SELECT * FROM buses")
    print(res.fetchall())

get()
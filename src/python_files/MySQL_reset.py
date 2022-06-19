import mysql.connector
from os import environ

def delete_mysql_tables(debug:bool=False) -> None:
    """
    Delete the database tables (run this if you want to reset the database)

    Args:
        debug (bool): If true, will delete locally, else will delete remotely
    """
    if (debug):
        host = "localhost"
        password = environ["SQL_PASS"]
    else:
        host = "34.143.163.29" # Google Cloud SQL Public address
        password = environ["REMOTE_SQL_PASS"]

    mydb = mysql.connector.connect(
        host=host,
        user="root",
        password=password
    )

    cur = mydb.cursor()
    cur.execute("DROP DATABASE coursefinity")
    mydb.commit()

    mydb.close()

if (__name__ == "__main__"):
    debugPrompt = input("Debug mode? (Y/n): ").lower().strip()
    debugFlag = True if (debugPrompt != "n") else False
    delete_mysql_tables(debug=debugFlag)
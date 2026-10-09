import mysql.connector

DB_HOST = "127.0.0.1"
DB_USER = "root"
DB_PASSWORD = "admin123"
DB_NAME = "hospital_db"


def get_db_connection():
    try:
        return mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )
    except mysql.connector.Error as err:
        print(f"Database connection failed: {err}")
        return None

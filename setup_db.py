from datetime import date, timedelta

import mysql.connector
from werkzeug.security import generate_password_hash

from db_config import DB_HOST, DB_NAME, DB_PASSWORD, DB_USER

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,+
        username VARCHAR(50) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        role ENUM('admin', 'patient') NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS doctors (
        doctor_id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        specialization VARCHAR(100) NOT NULL,
        phone VARCHAR(15),
        room VARCHAR(10)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS patients (
        patient_id VARCHAR(12) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        age INT,
        gender ENUM('Male', 'Female', 'Other'),
        phone VARCHAR(15) NOT NULL,
        condition_desc VARCHAR(255),
        doctor_id INT,
        admitted_on DATE,
        user_id INT,
        FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE SET NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS appointments (
        appointment_id INT AUTO_INCREMENT PRIMARY KEY,
        patient_id VARCHAR(12) NOT NULL,
        doctor_id INT,
        appt_date DATE NOT NULL,
        appt_time TIME NOT NULL,
        purpose VARCHAR(150),
        status ENUM('Scheduled', 'Completed', 'Cancelled') DEFAULT 'Scheduled',
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
        FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS billing (
        bill_id INT AUTO_INCREMENT PRIMARY KEY,
        patient_id VARCHAR(12) NOT NULL,
        treatment VARCHAR(150) NOT NULL,
        treatment_cost DECIMAL(10, 2) NULL,
        consultation_fee DECIMAL(10, 2) DEFAULT 0,
        medicine_charges DECIMAL(10, 2) DEFAULT 0,
        room_charges DECIMAL(10, 2) DEFAULT 0,
        total_amount DECIMAL(10, 2) NOT NULL,
        bill_date DATE NOT NULL,
        status ENUM('Unpaid', 'Paid') DEFAULT 'Unpaid',
        paid_on DATE NULL,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
    )
    """,
]

DOCTORS = [
    ("Dr. Ananya Sharma", "Cardiology", "9811023456", "C-101"),
    ("Dr. Rohan Mehta", "Orthopaedics", "9811034567", "O-204"),
    ("Dr. Kavita Iyer", "General Medicine", "9811045678", "G-002"),
    ("Dr. Arjun Nair", "Neurology", "9811056789", "N-305"),
    ("Dr. Sneha Kapoor", "Paediatrics", "9811067890", "P-110"),
    ("Dr. Vikram Rao", "Dermatology", "9811078901", "D-208"),
]

PATIENTS = [
    ("PAT-1001", "Aarav Gupta", 45, "Male", "9876543210", "Hypertension", 1, -40),
    ("PAT-1002", "Priya Verma", 32, "Female", "9876501234", "Fractured left wrist", 2, -21),
    ("PAT-1003", "Rahul Singh", 58, "Male", "9812345670", "Type 2 Diabetes", 3, -60),
    ("PAT-1004", "Meera Joshi", 27, "Female", "9898989898", "Chronic migraine", 4, -14),
    ("PAT-1005", "Ishaan Malhotra", 8, "Male", "9765432109", "Viral fever", 5, -5),
    ("PAT-1006", "Neha Reddy", 36, "Female", "9700012345", "Atopic eczema", 6, -30),
]

APPOINTMENTS = [
    ("PAT-1001", 1, -30, "10:00", "ECG and BP review", "Completed"),
    ("PAT-1001", 1, 0, "11:30", "Monthly cardiac follow-up", "Scheduled"),
    ("PAT-1002", 2, -18, "09:30", "Cast application", "Completed"),
    ("PAT-1002", 2, 3, "12:00", "X-ray and cast check", "Scheduled"),
    ("PAT-1003", 3, -45, "16:00", "HbA1c test review", "Completed"),
    ("PAT-1003", 3, -7, "15:00", "Diet consultation", "Cancelled"),
    ("PAT-1003", 3, 6, "10:30", "Quarterly diabetes review", "Scheduled"),
    ("PAT-1004", 4, -10, "14:00", "MRI scan discussion", "Completed"),
    ("PAT-1004", 4, 1, "17:00", "Medication review", "Scheduled"),
    ("PAT-1005", 5, -4, "11:00", "Fever assessment", "Completed"),
    ("PAT-1005", 5, 2, "10:00", "Recovery check-up", "Scheduled"),
    ("PAT-1006", 6, -25, "13:00", "Skin patch test", "Completed"),
    ("PAT-1006", 6, 9, "13:30", "Treatment progress review", "Scheduled"),
]

BILLS = [
    ("PAT-1001", "ECG and cardiac consultation", 1800, 800, 650, 0, -30, "Paid"),
    ("PAT-1002", "Fracture reduction and casting", 6500, 700, 900, 2500, -18, "Paid"),
    ("PAT-1002", "Follow-up X-ray", 1200, 0, 0, 0, -2, "Unpaid"),
    ("PAT-1003", "Diabetes panel and consultation", None, 600, 2100, 0, -45, "Paid"),
    ("PAT-1004", "MRI brain scan", 7500, 1000, 1200, 0, -10, "Unpaid"),
    ("PAT-1005", "Paediatric consultation", None, 500, 450, 0, -4, "Unpaid"),
    ("PAT-1006", "Patch test and topical therapy", 2200, 600, 1350, 0, -25, "Paid"),
]


def seed(cursor):
    today = date.today()

    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, 'admin')",
        ("admin", generate_password_hash("admin123")),
    )

    cursor.executemany(
        "INSERT INTO doctors (name, specialization, phone, room) VALUES (%s, %s, %s, %s)",
        DOCTORS,
    )

    for pid, name, age, gender, phone, condition, doctor, offset in PATIENTS:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, 'patient')",
            (pid, generate_password_hash("patient123")),
        )
        cursor.execute(
            """
            INSERT INTO patients
                (patient_id, name, age, gender, phone, condition_desc, doctor_id, admitted_on, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (pid, name, age, gender, phone, condition, doctor,
             today + timedelta(days=offset), cursor.lastrowid),
        )

    for pid, doctor, offset, at, purpose, status in APPOINTMENTS:
        cursor.execute(
            """
            INSERT INTO appointments (patient_id, doctor_id, appt_date, appt_time, purpose, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (pid, doctor, today + timedelta(days=offset), at, purpose, status),
        )

    for pid, treatment, cost, consult, medicine, room, offset, status in BILLS:
        total = (cost or 0) + consult + medicine + room
        billed_on = today + timedelta(days=offset)
        cursor.execute(
            """
            INSERT INTO billing
                (patient_id, treatment, treatment_cost, consultation_fee, medicine_charges,
                 room_charges, total_amount, bill_date, status, paid_on)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (pid, treatment, cost, consult, medicine, room, total, billed_on, status,
             billed_on if status == "Paid" else None),
        )


def setup_database():
    try:
        conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
    except mysql.connector.Error as err:
        print(f"Could not connect to MySQL: {err}")
        return

    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        cursor.execute(f"USE {DB_NAME}")
        for statement in TABLES:
            cursor.execute(statement)

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            seed(cursor)
            conn.commit()
            print("Database created and sample records added.")
        else:
            print("Database already set up. Existing records kept.")

        print("Admin login   : admin / admin123")
        print("Patient login : PAT-1001 / patient123")
    except mysql.connector.Error as err:
        conn.rollback()
        print(f"Setup failed: {err}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    setup_database()

import csv
import os
from datetime import date, datetime, time, timedelta
from functools import wraps

import mysql.connector
from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db_config import get_db_connection
from icons import icon

app = Flask(__name__)
app.secret_key = "mkure-hms-cbse-2026"

HOSPITAL_NAME = "MKure"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDS_DIR = os.path.join(BASE_DIR, "records")
LOG_FILE = os.path.join(RECORDS_DIR, "activity_log.txt")
RECEIPT_DIR = os.path.join(RECORDS_DIR, "receipts")
EXPORT_DIR = os.path.join(RECORDS_DIR, "exports")

os.makedirs(RECEIPT_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

app.jinja_env.globals.update(icon=icon, hospital=HOSPITAL_NAME)


class DatabaseUnavailable(Exception):
    pass


def run_query(sql, params=(), fetch="all"):
    conn = get_db_connection()
    if conn is None:
        raise DatabaseUnavailable()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        if fetch == "one":
            return cursor.fetchone()
        if fetch == "all":
            return cursor.fetchall()
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def write_log(message):
    stamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    user = session.get("username", "system")
    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(f"{stamp} | {user} | {message}\n")


def read_log(limit=60):
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as file:
        lines = file.readlines()
    entries = []
    for line in reversed(lines[-limit:]):
        parts = line.rstrip("\n").split(" | ")
        if len(parts) == 3:
            entries.append({"time": parts[0], "user": parts[1], "message": parts[2]})
    return entries


def list_files(folder):
    files = []
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            stats = os.stat(path)
            files.append({
                "name": name,
                "size": round(stats.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stats.st_mtime),
            })
    return sorted(files, key=lambda f: f["modified"], reverse=True)


def receipt_filename(patient_id, bill_id):
    return f"receipt_{patient_id}_bill{bill_id}.txt"


def create_receipt(bill_id):
    bill = run_query(
        """
        SELECT b.*, p.name, p.phone, d.name AS doctor_name
        FROM billing b
        JOIN patients p ON p.patient_id = b.patient_id
        LEFT JOIN doctors d ON d.doctor_id = p.doctor_id
        WHERE b.bill_id = %s
        """,
        (bill_id,), "one",
    )
    if not bill:
        return None

    def money(value):
        return f"Rs. {float(value or 0):,.2f}"

    def row(label, value):
        return f"  {label:<26}{value:>24}"

    width = 54
    lines = [
        "=" * width,
        HOSPITAL_NAME.upper().center(width),
        "Mumbai".center(width),
        "Phone: 8433552656".center(width),
        "=" * width,
        "PAYMENT RECEIPT".center(width),
        "-" * width,
        row("Receipt No.", f"RCPT-{bill['bill_id']:05d}"),
        row("Patient ID", bill["patient_id"]),
        row("Patient Name", bill["name"]),
        row("Phone", bill["phone"]),
        row("Attending Doctor", bill["doctor_name"] or "-"),
        row("Bill Date", bill["bill_date"].strftime("%d %b %Y")),
        row("Paid On", (bill["paid_on"] or date.today()).strftime("%d %b %Y")),
        "-" * width,
        f"  Treatment: {bill['treatment']}",
        "-" * width,
        row("Treatment Cost", money(bill["treatment_cost"]) if bill["treatment_cost"] is not None else "Not applicable"),
        row("Consultation Fee", money(bill["consultation_fee"])),
        row("Medicine Charges", money(bill["medicine_charges"])),
        row("Room Charges", money(bill["room_charges"])),
        "-" * width,
        row("TOTAL PAID", money(bill["total_amount"])),
        "=" * width,
        "Thank you for choosing us. Get well soon.".center(width),
        f"Generated on {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}".center(width),
        "=" * width,
    ]

    path = os.path.join(RECEIPT_DIR, receipt_filename(bill["patient_id"], bill_id))
    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    return path


def settle_bill(bill_id):
    run_query(
        "UPDATE billing SET status = 'Paid', paid_on = CURDATE() WHERE bill_id = %s AND status = 'Unpaid'",
        (bill_id,), None,
    )
    path = create_receipt(bill_id)
    write_log(f"Bill #{bill_id} settled, receipt saved as {os.path.basename(path)}")


def next_patient_id(cursor):
    cursor.execute("SELECT MAX(CAST(SUBSTRING(patient_id, 5) AS UNSIGNED)) AS last_no FROM patients")
    row = cursor.fetchone()
    return f"PAT-{(row['last_no'] or 1000) + 1}"


def to_amount(value):
    try:
        return round(float(value), 2) if value not in (None, "") else None
    except ValueError:
        return None


def doctor_options():
    return run_query("SELECT doctor_id, name, specialization FROM doctors ORDER BY name")


def patient_options():
    return run_query("SELECT patient_id, name FROM patients ORDER BY patient_id")


def login_required(role):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                flash("Please sign in to continue.", "error")
                return redirect(url_for("login", role=role))
            return view(*args, **kwargs)
        return wrapper
    return decorator


@app.template_filter("inr")
def format_inr(value):
    if value is None:
        return "—"
    whole, fraction = f"{float(value):.2f}".split(".")
    sign = ""
    if whole.startswith("-"):
        sign, whole = "-", whole[1:]
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}₹{whole}.{fraction}"


@app.template_filter("fdate")
def format_date(value, pattern="%d %b %Y"):
    return value.strftime(pattern) if value else "—"


@app.template_filter("ftime")
def format_time(value):
    if value is None:
        return ""
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        value = time(seconds // 3600, (seconds % 3600) // 60)
    return value.strftime("%I:%M %p").lstrip("0")


@app.template_filter("initials")
def initials(name):
    parts = [p for p in (name or "").replace("Dr.", "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper()


@app.context_processor
def inject_today():
    return {"today": date.today()}


@app.errorhandler(DatabaseUnavailable)
def database_unavailable(error):
    return render_template("db_error.html"), 503


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role", "admin")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = run_query(
            "SELECT * FROM users WHERE username = %s AND role = %s",
            (username, role), "one",
        )
        if user and check_password_hash(user["password"], password):
            session.clear()
            session.update(user_id=user["id"], username=user["username"], role=user["role"])
            write_log(f"Signed in to the {role} portal")
            return redirect(url_for("admin_overview" if role == "admin" else "patient_dashboard"))
        flash("Invalid credentials for the selected portal.", "error")
        return render_template("login.html", role=role, username=username)
    return render_template("login.html", role=request.args.get("role", "admin"), username="")


@app.route("/logout")
def logout():
    if session.get("username"):
        write_log("Signed out")
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/admin")
@login_required("admin")
def admin_overview():
    stats = run_query(
        """
        SELECT
            (SELECT COUNT(*) FROM patients) AS patients,
            (SELECT COUNT(*) FROM doctors) AS doctors,
            (SELECT COUNT(*) FROM appointments
              WHERE status = 'Scheduled' AND appt_date >= CURDATE()) AS upcoming,
            (SELECT COUNT(*) FROM appointments
              WHERE status = 'Scheduled' AND appt_date = CURDATE()) AS today,
            (SELECT COALESCE(SUM(total_amount), 0) FROM billing WHERE status = 'Paid') AS collected,
            (SELECT COALESCE(SUM(total_amount), 0) FROM billing WHERE status = 'Unpaid') AS pending,
            (SELECT COUNT(*) FROM billing WHERE status = 'Unpaid') AS unpaid_bills
        """,
        fetch="one",
    )
    total = float(stats["collected"]) + float(stats["pending"])
    stats["collection_rate"] = round(float(stats["collected"]) / total * 100) if total else 0

    upcoming = run_query(
        """
        SELECT a.*, p.name AS patient_name, d.name AS doctor_name, d.specialization
        FROM appointments a
        JOIN patients p ON p.patient_id = a.patient_id
        LEFT JOIN doctors d ON d.doctor_id = a.doctor_id
        WHERE a.status = 'Scheduled' AND a.appt_date >= CURDATE()
        ORDER BY a.appt_date, a.appt_time
        LIMIT 6
        """
    )
    workload = run_query(
        """
        SELECT d.name, d.specialization, COUNT(p.patient_id) AS patients
        FROM doctors d
        LEFT JOIN patients p ON p.doctor_id = d.doctor_id
        GROUP BY d.doctor_id, d.name, d.specialization
        ORDER BY patients DESC, d.name
        """
    )
    peak = max([row["patients"] for row in workload] + [1])
    recent_bills = run_query(
        """
        SELECT b.bill_id, b.patient_id, b.treatment, b.total_amount, b.status, b.bill_date,
               p.name AS patient_name
        FROM billing b
        JOIN patients p ON p.patient_id = b.patient_id
        ORDER BY b.bill_date DESC, b.bill_id DESC
        LIMIT 5
        """
    )
    return render_template(
        "admin/overview.html", active="overview", stats=stats, upcoming=upcoming,
        workload=workload, peak=peak, recent_bills=recent_bills, activity=read_log(6),
    )


@app.route("/admin/patients", methods=["GET", "POST"])
@login_required("admin")
def admin_patients():
    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        conn = get_db_connection()
        if conn is None:
            raise DatabaseUnavailable()
        cursor = conn.cursor(dictionary=True)
        try:
            patient_id = next_patient_id(cursor)
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, 'patient')",
                (patient_id, generate_password_hash(form["password"])),
            )
            user_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO patients
                    (patient_id, name, age, gender, phone, condition_desc, doctor_id, admitted_on, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (patient_id, name, form.get("age") or None, form.get("gender"),
                 form.get("phone", "").strip(), form.get("condition", "").strip(),
                 form.get("doctor_id") or None, form.get("admitted_on") or date.today(), user_id),
            )
            conn.commit()
            write_log(f"Registered patient {patient_id} ({name})")
            flash(f"{name} registered with Patient ID {patient_id}.", "success")
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f"Could not register patient: {err.msg}", "error")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for("admin_patients"))

    search = request.args.get("q", "").strip()
    sql = """
        SELECT p.*, d.name AS doctor_name, d.specialization,
               (SELECT COALESCE(SUM(b.total_amount), 0) FROM billing b
                 WHERE b.patient_id = p.patient_id AND b.status = 'Unpaid') AS dues
        FROM patients p
        LEFT JOIN doctors d ON d.doctor_id = p.doctor_id
    """
    params = ()
    if search:
        like = f"%{search}%"
        sql += """ WHERE p.patient_id LIKE %s OR p.name LIKE %s
                   OR p.phone LIKE %s OR p.condition_desc LIKE %s"""
        params = (like, like, like, like)
    sql += " ORDER BY p.patient_id"
    patients = run_query(sql, params)
    return render_template(
        "admin/patients.html", active="patients", patients=patients,
        search=search, doctors=doctor_options(),
    )


@app.route("/admin/patients/<patient_id>", methods=["GET", "POST"])
@login_required("admin")
def admin_patient_detail(patient_id):
    if request.method == "POST":
        form = request.form
        run_query(
            "UPDATE patients SET phone = %s, condition_desc = %s, doctor_id = %s WHERE patient_id = %s",
            (form.get("phone", "").strip(), form.get("condition", "").strip(),
             form.get("doctor_id") or None, patient_id),
            None,
        )
        write_log(f"Updated record of patient {patient_id}")
        flash("Patient record updated.", "success")
        return redirect(url_for("admin_patient_detail", patient_id=patient_id))

    patient = run_query(
        """
        SELECT p.*, d.name AS doctor_name, d.specialization, d.phone AS doctor_phone
        FROM patients p
        LEFT JOIN doctors d ON d.doctor_id = p.doctor_id
        WHERE p.patient_id = %s
        """,
        (patient_id,), "one",
    )
    if not patient:
        abort(404)
    appointments = run_query(
        """
        SELECT a.*, d.name AS doctor_name
        FROM appointments a
        LEFT JOIN doctors d ON d.doctor_id = a.doctor_id
        WHERE a.patient_id = %s
        ORDER BY a.appt_date DESC, a.appt_time DESC
        """,
        (patient_id,),
    )
    bills = run_query(
        "SELECT * FROM billing WHERE patient_id = %s ORDER BY bill_date DESC, bill_id DESC",
        (patient_id,),
    )
    totals = {
        "billed": sum(float(b["total_amount"]) for b in bills),
        "paid": sum(float(b["total_amount"]) for b in bills if b["status"] == "Paid"),
    }
    totals["due"] = totals["billed"] - totals["paid"]
    return render_template(
        "admin/patient_detail.html", active="patients", patient=patient,
        appointments=appointments, bills=bills, totals=totals, doctors=doctor_options(),
    )


@app.route("/admin/patients/<patient_id>/delete", methods=["POST"])
@login_required("admin")
def admin_delete_patient(patient_id):
    patient = run_query("SELECT name, user_id FROM patients WHERE patient_id = %s", (patient_id,), "one")
    if patient:
        if patient["user_id"]:
            run_query("DELETE FROM users WHERE id = %s", (patient["user_id"],), None)
        run_query("DELETE FROM patients WHERE patient_id = %s", (patient_id,), None)
        write_log(f"Removed patient {patient_id} ({patient['name']})")
        flash(f"Patient {patient_id} and related records removed.", "success")
    return redirect(url_for("admin_patients"))


@app.route("/admin/appointments", methods=["GET", "POST"])
@login_required("admin")
def admin_appointments():
    if request.method == "POST":
        form = request.form
        try:
            run_query(
                """
                INSERT INTO appointments (patient_id, doctor_id, appt_date, appt_time, purpose)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (form["patient_id"], form.get("doctor_id") or None, form["appt_date"],
                 form["appt_time"], form.get("purpose", "").strip()),
                None,
            )
            write_log(f"Scheduled appointment for {form['patient_id']} on {form['appt_date']}")
            flash("Appointment scheduled.", "success")
        except mysql.connector.Error as err:
            flash(f"Could not schedule appointment: {err.msg}", "error")
        return redirect(request.referrer or url_for("admin_appointments"))

    view = request.args.get("view", "upcoming")
    filters = {
        "upcoming": ("a.status = 'Scheduled' AND a.appt_date >= CURDATE()", "a.appt_date, a.appt_time"),
        "past": ("(a.appt_date < CURDATE() OR a.status <> 'Scheduled')", "a.appt_date DESC, a.appt_time DESC"),
        "all": ("1 = 1", "a.appt_date DESC, a.appt_time DESC"),
    }
    if view not in filters:
        view = "upcoming"
    where, order = filters[view]
    appointments = run_query(
        f"""
        SELECT a.*, p.name AS patient_name, p.phone AS patient_phone,
               d.name AS doctor_name, d.specialization
        FROM appointments a
        JOIN patients p ON p.patient_id = a.patient_id
        LEFT JOIN doctors d ON d.doctor_id = a.doctor_id
        WHERE {where}
        ORDER BY {order}
        """
    )
    counts = run_query(
        """
        SELECT
            COALESCE(SUM(status = 'Scheduled' AND appt_date >= CURDATE()), 0) AS upcoming,
            COALESCE(SUM(appt_date < CURDATE() OR status <> 'Scheduled'), 0) AS past,
            COUNT(*) AS all_count
        FROM appointments
        """,
        fetch="one",
    )
    return render_template(
        "admin/appointments.html", active="appointments", appointments=appointments,
        view=view, counts=counts, patients=patient_options(), doctors=doctor_options(),
    )


@app.route("/admin/appointments/<int:appointment_id>/<action>", methods=["POST"])
@login_required("admin")
def admin_update_appointment(appointment_id, action):
    status = {"complete": "Completed", "cancel": "Cancelled"}.get(action)
    if not status:
        abort(404)
    run_query(
        "UPDATE appointments SET status = %s WHERE appointment_id = %s",
        (status, appointment_id), None,
    )
    write_log(f"Appointment #{appointment_id} marked {status.lower()}")
    flash(f"Appointment marked as {status.lower()}.", "success")
    return redirect(request.referrer or url_for("admin_appointments"))


@app.route("/admin/billing", methods=["GET", "POST"])
@login_required("admin")
def admin_billing():
    if request.method == "POST":
        form = request.form
        treatment_cost = to_amount(form.get("treatment_cost"))
        consultation = to_amount(form.get("consultation_fee")) or 0
        medicine = to_amount(form.get("medicine_charges")) or 0
        room = to_amount(form.get("room_charges")) or 0
        total = (treatment_cost or 0) + consultation + medicine + room
        if total <= 0:
            flash("The bill total must be greater than zero.", "error")
        else:
            try:
                bill_id = run_query(
                    """
                    INSERT INTO billing
                        (patient_id, treatment, treatment_cost, consultation_fee,
                         medicine_charges, room_charges, total_amount, bill_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURDATE())
                    """,
                    (form["patient_id"], form.get("treatment", "").strip(), treatment_cost,
                     consultation, medicine, room, total),
                    None,
                )
                write_log(f"Raised bill #{bill_id} of Rs. {total:,.2f} for {form['patient_id']}")
                flash(f"Bill #{bill_id} raised for {format_inr(total)}.", "success")
            except mysql.connector.Error as err:
                flash(f"Could not create bill: {err.msg}", "error")
        return redirect(request.referrer or url_for("admin_billing"))

    status = request.args.get("status", "all")
    sql = """
        SELECT b.*, p.name AS patient_name
        FROM billing b
        JOIN patients p ON p.patient_id = b.patient_id
    """
    params = ()
    if status in ("Paid", "Unpaid"):
        sql += " WHERE b.status = %s"
        params = (status,)
    else:
        status = "all"
    sql += " ORDER BY b.bill_date DESC, b.bill_id DESC"
    bills = run_query(sql, params)
    summary = run_query(
        """
        SELECT
            COALESCE(SUM(CASE WHEN status = 'Paid' THEN total_amount END), 0) AS collected,
            COALESCE(SUM(CASE WHEN status = 'Unpaid' THEN total_amount END), 0) AS pending,
            COUNT(*) AS bills,
            COALESCE(SUM(status = 'Unpaid'), 0) AS unpaid
        FROM billing
        """,
        fetch="one",
    )
    return render_template(
        "admin/billing.html", active="billing", bills=bills, status=status,
        summary=summary, patients=patient_options(),
    )


@app.route("/admin/billing/<int:bill_id>/paid", methods=["POST"])
@login_required("admin")
def admin_mark_paid(bill_id):
    settle_bill(bill_id)
    flash(f"Bill #{bill_id} marked as paid. Receipt saved to file.", "success")
    return redirect(request.referrer or url_for("admin_billing"))


@app.route("/admin/doctors", methods=["GET", "POST"])
@login_required("admin")
def admin_doctors():
    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        if not name.lower().startswith("dr"):
            name = f"Dr. {name}"
        run_query(
            "INSERT INTO doctors (name, specialization, phone, room) VALUES (%s, %s, %s, %s)",
            (name, form.get("specialization", "").strip(), form.get("phone", "").strip(),
             form.get("room", "").strip()),
            None,
        )
        write_log(f"Added doctor {name}")
        flash(f"{name} added to the staff list.", "success")
        return redirect(url_for("admin_doctors"))

    doctors = run_query(
        """
        SELECT d.*,
               (SELECT COUNT(*) FROM patients p WHERE p.doctor_id = d.doctor_id) AS patients,
               (SELECT COUNT(*) FROM appointments a WHERE a.doctor_id = d.doctor_id
                  AND a.status = 'Scheduled' AND a.appt_date >= CURDATE()) AS upcoming
        FROM doctors d
        ORDER BY d.name
        """
    )
    return render_template("admin/doctors.html", active="doctors", doctors=doctors)


@app.route("/admin/records")
@login_required("admin")
def admin_records():
    return render_template(
        "admin/records.html", active="records", logs=read_log(80),
        receipts=list_files(RECEIPT_DIR), exports=list_files(EXPORT_DIR),
    )


@app.route("/admin/export/<kind>")
@login_required("admin")
def admin_export(kind):
    if kind == "patients":
        headers = ["Patient ID", "Name", "Age", "Gender", "Phone", "Condition", "Doctor", "Admitted On"]
        rows = run_query(
            """
            SELECT p.patient_id, p.name, p.age, p.gender, p.phone, p.condition_desc,
                   d.name AS doctor_name, p.admitted_on
            FROM patients p LEFT JOIN doctors d ON d.doctor_id = p.doctor_id
            ORDER BY p.patient_id
            """
        )
    elif kind == "billing":
        headers = ["Bill ID", "Patient ID", "Patient", "Treatment", "Treatment Cost",
                   "Consultation", "Medicines", "Room", "Total", "Bill Date", "Status"]
        rows = run_query(
            """
            SELECT b.bill_id, b.patient_id, p.name, b.treatment, b.treatment_cost,
                   b.consultation_fee, b.medicine_charges, b.room_charges,
                   b.total_amount, b.bill_date, b.status
            FROM billing b JOIN patients p ON p.patient_id = b.patient_id
            ORDER BY b.bill_id
            """
        )
    else:
        abort(404)

    filename = f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(os.path.join(EXPORT_DIR, filename), "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        for record in rows:
            writer.writerow(list(record.values()))
    write_log(f"Exported {len(rows)} {kind} records to {filename}")
    return send_from_directory(EXPORT_DIR, filename, as_attachment=True)


@app.route("/admin/files/<folder>/<path:filename>")
@login_required("admin")
def admin_file(folder, filename):
    directories = {"receipts": RECEIPT_DIR, "exports": EXPORT_DIR}
    if folder not in directories:
        abort(404)
    return send_from_directory(directories[folder], filename, as_attachment=True)


@app.route("/patient")
@login_required("patient")
def patient_dashboard():
    patient = run_query(
        """
        SELECT p.*, d.name AS doctor_name, d.specialization, d.phone AS doctor_phone, d.room
        FROM patients p
        LEFT JOIN doctors d ON d.doctor_id = p.doctor_id
        WHERE p.user_id = %s
        """,
        (session["user_id"],), "one",
    )
    if not patient:
        session.clear()
        flash("Your patient record could not be found.", "error")
        return redirect(url_for("login", role="patient"))

    pid = patient["patient_id"]
    upcoming = run_query(
        """
        SELECT a.*, d.name AS doctor_name, d.specialization, d.room
        FROM appointments a LEFT JOIN doctors d ON d.doctor_id = a.doctor_id
        WHERE a.patient_id = %s AND a.status = 'Scheduled' AND a.appt_date >= CURDATE()
        ORDER BY a.appt_date, a.appt_time
        """,
        (pid,),
    )
    history = run_query(
        """
        SELECT a.*, d.name AS doctor_name, d.specialization
        FROM appointments a LEFT JOIN doctors d ON d.doctor_id = a.doctor_id
        WHERE a.patient_id = %s AND NOT (a.status = 'Scheduled' AND a.appt_date >= CURDATE())
        ORDER BY a.appt_date DESC, a.appt_time DESC
        """,
        (pid,),
    )
    bills = run_query(
        "SELECT * FROM billing WHERE patient_id = %s ORDER BY bill_date DESC, bill_id DESC",
        (pid,),
    )
    due = sum(float(b["total_amount"]) for b in bills if b["status"] == "Unpaid")
    paid = sum(float(b["total_amount"]) for b in bills if b["status"] == "Paid")
    return render_template(
        "patient/dashboard.html", patient=patient, upcoming=upcoming,
        history=history, bills=bills, due=due, paid=paid,
    )


@app.route("/patient/pay/<int:bill_id>", methods=["POST"])
@login_required("patient")
def patient_pay(bill_id):
    bill = run_query(
        """
        SELECT b.bill_id FROM billing b
        JOIN patients p ON p.patient_id = b.patient_id
        WHERE b.bill_id = %s AND p.user_id = %s AND b.status = 'Unpaid'
        """,
        (bill_id, session["user_id"]), "one",
    )
    if bill:
        settle_bill(bill_id)
        flash("Payment successful. Your receipt is ready to download.", "success")
    else:
        flash("This bill is not available for payment.", "error")
    return redirect(url_for("patient_dashboard"))


@app.route("/receipt/<int:bill_id>")
def download_receipt(bill_id):
    role = session.get("role")
    if role not in ("admin", "patient"):
        return redirect(url_for("login"))
    bill = run_query(
        """
        SELECT b.bill_id, b.patient_id, b.status, p.user_id
        FROM billing b JOIN patients p ON p.patient_id = b.patient_id
        WHERE b.bill_id = %s
        """,
        (bill_id,), "one",
    )
    if not bill or bill["status"] != "Paid":
        abort(404)
    if role == "patient" and bill["user_id"] != session.get("user_id"):
        abort(403)
    filename = receipt_filename(bill["patient_id"], bill_id)
    if not os.path.exists(os.path.join(RECEIPT_DIR, filename)):
        create_receipt(bill_id)
    return send_from_directory(RECEIPT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)

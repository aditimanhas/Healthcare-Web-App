import os
import sqlite3
import pandas as pd
import random

from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "healthcare_secret")


# ---------------- DATABASE ----------------
def connect_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect_db()

    # USERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    # PATIENTS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patients(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            age INTEGER,
            phone TEXT,
            email TEXT,
            blood_group TEXT,
            symptoms TEXT,
            disease TEXT
        )
    """)

    # APPOINTMENTS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS appointments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            doctor TEXT,
            date TEXT,
            time TEXT,
            booking_id TEXT
        )
    """)

    # CONTACTS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            message TEXT
        )
    """)

    # ADMIN
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")

    admin = conn.execute(
        "SELECT * FROM admin WHERE username=?",
        (admin_username,)
    ).fetchone()

    if not admin:
        conn.execute(
            "INSERT INTO admin(username, password) VALUES(?, ?)",
            (admin_username, generate_password_hash(admin_password))
        )
    else:
        conn.execute(
            "UPDATE admin SET password=? WHERE username=?",
            (generate_password_hash(admin_password), admin_username)
        )

    conn.commit()
    conn.close()


# ---------------- LOAD DATA ----------------
symptoms_df = pd.read_csv("dataset.csv")
precautions_df = pd.read_csv("symptom_precaution.csv")

symptoms_df.columns = symptoms_df.columns.str.strip().str.lower()
precautions_df.columns = precautions_df.columns.str.strip().str.lower()

symptoms_df["disease"] = symptoms_df["disease"].astype(str).str.strip().str.lower()
precautions_df["disease"] = precautions_df["disease"].astype(str).str.strip().str.lower()

for col in symptoms_df.columns[1:]:
    symptoms_df[col] = symptoms_df[col].astype(str).str.strip().str.lower()

all_symptoms = []
for col in symptoms_df.columns[1:]:
    for symptom in symptoms_df[col].dropna():
        symptom = str(symptom).strip().lower()
        if symptom and symptom != "nan" and symptom not in all_symptoms:
            all_symptoms.append(symptom)

all_symptoms.sort()
blood_groups = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]


# ---------------- HOME ----------------
@app.route('/')
def home():
    return render_template('index.html')


# ---------------- CONTACT ----------------
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        country_code = request.form.get('country_code')
        phone = request.form.get('phone')
        message = request.form.get('message')

        full_phone = f"{country_code} {phone}"

        conn = connect_db()
        conn.execute(
            "INSERT INTO contacts(name, email, phone, message) VALUES(?,?,?,?)",
            (name, email, full_phone, message)
        )
        conn.commit()
        conn.close()

        return render_template(
            'contact_success.html',
            name=name,
            phone=full_phone
        )

    return render_template('contact.html')


# ---------------- SIGNUP ----------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None

    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = connect_db()
        try:
            conn.execute(
                "INSERT INTO users(fullname, email, password) VALUES(?, ?, ?)",
                (fullname, email, password)
            )
            conn.commit()
            conn.close()
            return redirect('/signin')
        except sqlite3.IntegrityError:
            conn.close()
            error = "Email already registered"

    return render_template('signup.html', error=error)


# ---------------- SIGNIN ----------------
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    error = None

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = connect_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user'] = user['fullname']

            next_page = session.pop('next_page', None)
            if next_page:
                return redirect(next_page)

            return redirect('/dashboard')
        else:
            error = "Invalid email or password"

    return render_template('signin.html', error=error)


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/signin')


# ---------------- DASHBOARD ----------------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        session['next_page'] = '/dashboard'
        return redirect('/signin')
    return render_template('dashboard.html', user=session['user'])


# ---------------- DISEASE FORM ----------------
@app.route('/disease')
def disease():
    if 'user' not in session:
        session['next_page'] = '/disease'
        return redirect('/signin')

    return render_template(
        'disease_form.html',
        symptoms=all_symptoms,
        blood_groups=blood_groups
    )


# ---------------- PREDICT ----------------
@app.route('/predict', methods=['POST'])
def predict():
    if 'user' not in session:
        session['next_page'] = '/disease'
        return redirect('/signin')

    name = request.form['name']
    age = request.form['age']
    phone = request.form['phone']
    email = request.form['email']
    blood_group = request.form['blood_group']
    symptoms = [s.strip().lower() for s in request.form.getlist('symptoms')]

    best_match = None
    max_match = 0

    for _, row in symptoms_df.iterrows():
        row_symptoms = []
        for col in symptoms_df.columns[1:]:
            value = str(row[col]).strip().lower()
            if value and value != "nan":
                row_symptoms.append(value)

        match_count = len(set(symptoms) & set(row_symptoms))
        if match_count > max_match:
            max_match = match_count
            best_match = row["disease"]

    disease_name = best_match if best_match else "common cold"

    conn = connect_db()
    conn.execute("""
        INSERT INTO patients(name, age, phone, email, blood_group, symptoms, disease)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, age, phone, email, blood_group, ", ".join(symptoms), disease_name))
    conn.commit()
    conn.close()

    precautions = []
    row = precautions_df[precautions_df["disease"] == disease_name]

    if not row.empty:
        for col in precautions_df.columns[1:]:
            value = str(row.iloc[0][col]).strip()
            if value and value.lower() != "nan":
                precautions.append(value)

    return render_template(
        'result.html',
        name=name,
        disease=disease_name.title(),
        symptoms=symptoms,
        precautions=precautions
    )


# ---------------- APPOINTMENT ----------------
@app.route('/appointment')
def appointment():
    return render_template('appointment.html')


@app.route('/book', methods=['GET', 'POST'])
def book():
    if request.method == 'POST':
        name = request.form['name']
        doctor = request.form['doctor']
        date = request.form['date']
        time = request.form['time']

        booking_id = "APT" + str(random.randint(1000, 9999))

        conn = connect_db()
        conn.execute(
            "INSERT INTO appointments(name, doctor, date, time, booking_id) VALUES(?,?,?,?,?)",
            (name, doctor, date, time, booking_id)
        )
        conn.commit()
        conn.close()

        return render_template(
            'submit_appointment.html',
            name=name,
            doctor=doctor,
            date=date,
            time=time,
            booking_id=booking_id
        )

    return redirect('/appointment')


# ---------------- ADMIN LOGIN ----------------
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if 'admin' in session:
        return redirect('/admin')

    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = connect_db()
        admin = conn.execute(
            "SELECT * FROM admin WHERE username=?",
            (username,)
        ).fetchone()
        conn.close()

        if admin and check_password_hash(admin['password'], password):
            session['admin'] = True
            return redirect('/admin')
        else:
            error = "Invalid Admin Login"

    return render_template('admin_login.html', error=error)


# ---------------- ADMIN PANEL ----------------
@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect('/admin_login')

    conn = connect_db()

    users = conn.execute("SELECT * FROM users").fetchall()
    patients = conn.execute("SELECT * FROM patients").fetchall()
    appointments = conn.execute("SELECT * FROM appointments").fetchall()
    contacts = conn.execute("SELECT * FROM contacts").fetchall()

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    total_appointments = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    total_contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]

    conn.close()

    return render_template(
        'admin.html',
        users=users,
        patients=patients,
        appointments=appointments,
        contacts=contacts,
        total_users=total_users,
        total_patients=total_patients,
        total_appointments=total_appointments,
        total_contacts=total_contacts
    )


# ---------------- RUN ----------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
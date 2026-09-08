from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY", "change-this-secret-key-before-production"
)

DATABASE = "database.db"


# ---------------- DATABASE CONNECTION ---------------- #


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")

    return conn


# ---------------- CREATE DATABASE ---------------- #


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS exams(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            duration INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS questions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_answer TEXT NOT NULL,

            FOREIGN KEY(exam_id)
            REFERENCES exams(id)
            ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS results(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            exam_date TEXT NOT NULL,

            UNIQUE(user_id, exam_id),

            FOREIGN KEY(user_id)
            REFERENCES users(id),

            FOREIGN KEY(exam_id)
            REFERENCES exams(id)
        )
    """)

    conn.commit()

    # Default Admin Account

    admin = conn.execute(
        "SELECT * FROM users WHERE email=?", ("admin@bbs.com",)
    ).fetchone()

    if not admin:
        password = generate_password_hash("ompatel@123")
        conn.execute(
            "UPDATE users SET password = ? WHERE email = ? AND role = ?",
            (generate_password_hash("ompatel@123"), "admin@bbs.com", "admin"),
        )

        conn.execute(
            """
            INSERT INTO users(name,email,password,role)
            VALUES(?,?,?,?)
        """,
            ("Administrator", "admin@bbs.com", password, "admin"),
        )

        conn.commit()

    conn.close()


# ---------------- LOGIN REQUIRED ---------------- #


def login_required(f):

    @wraps(f)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            flash("Please login first.")

            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return wrapper


# ---------------- ADMIN REQUIRED ---------------- #


def admin_required(f):

    @wraps(f)
    def wrapper(*args, **kwargs):

        if session.get("role") != "admin":
            flash("Admin access required.")

            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return wrapper


# ---------------- HOME ---------------- #


@app.route("/")
def index():

    return render_template("index.html")


# ---------------- REGISTER ---------------- #


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        name = request.form["name"].strip()

        email = request.form["email"].strip().lower()

        password = request.form["password"]

        if not name or not email or not password:
            flash("All fields are required.")

            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:
            conn.execute(
                """
                INSERT INTO users(name,email,password,role)
                VALUES(?,?,?,?)
            """,
                (name, email, hashed_password, "student"),
            )

            conn.commit()

            flash("Registration successful. Please login.")

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Email already registered.")

        finally:
            conn.close()

    return render_template("register.html")


# ---------------- LOGIN ---------------- #


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        email = request.form["email"].strip().lower()

        password = request.form["password"]

        conn = get_db()

        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()

            session["user_id"] = user["id"]

            session["name"] = user["name"]

            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# ---------------- LOGOUT ---------------- #


@app.route("/logout")
def logout():

    session.clear()

    flash("Logged out successfully.")

    return redirect(url_for("login"))


# =====================================================
# STUDENT SECTION
# =====================================================


# ---------------- STUDENT DASHBOARD ---------------- #


@app.route("/student")
@login_required
def student_dashboard():

    if session.get("role") != "student":
        return redirect(url_for("admin_dashboard"))

    conn = get_db()

    exams = conn.execute(
        """
        SELECT
            exams.*,

            (
                SELECT COUNT(*)
                FROM questions
                WHERE questions.exam_id = exams.id
            ) AS question_count,

            (
                SELECT COUNT(*)
                FROM results
                WHERE results.exam_id = exams.id
                AND results.user_id = ?
            ) AS attempted

        FROM exams

        ORDER BY exams.id DESC

    """,
        (session["user_id"],),
    ).fetchall()

    conn.close()

    return render_template("student_dashboard.html", exams=exams)


# ---------------- START EXAM ---------------- #


@app.route("/exam/<int:exam_id>")
@login_required
def exam(exam_id):

    if session.get("role") != "student":
        return redirect(url_for("index"))

    conn = get_db()

    previous = conn.execute(
        """
        SELECT *
        FROM results
        WHERE user_id=? AND exam_id=?
    """,
        (session["user_id"], exam_id),
    ).fetchone()

    if previous:
        conn.close()

        flash("You have already attempted this exam.")

        return redirect(url_for("student_dashboard"))

    exam_data = conn.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()

    if not exam_data:
        conn.close()

        flash("Exam not found.")

        return redirect(url_for("student_dashboard"))

    questions = conn.execute(
        """
        SELECT *
        FROM questions
        WHERE exam_id=?
        ORDER BY id
    """,
        (exam_id,),
    ).fetchall()

    conn.close()

    if len(questions) == 0:
        flash("No questions available in this exam.")

        return redirect(url_for("student_dashboard"))

    return render_template("exam.html", exam=exam_data, questions=questions)


# ---------------- SUBMIT EXAM ---------------- #


@app.route("/submit_exam/<int:exam_id>", methods=["POST"])
@login_required
def submit_exam(exam_id):

    if session.get("role") != "student":
        return redirect(url_for("index"))

    conn = get_db()

    previous = conn.execute(
        """
        SELECT *
        FROM results
        WHERE user_id=? AND exam_id=?
    """,
        (session["user_id"], exam_id),
    ).fetchone()

    if previous:
        conn.close()

        flash("Exam already submitted.")

        return redirect(url_for("student_dashboard"))

    questions = conn.execute(
        """
        SELECT *
        FROM questions
        WHERE exam_id=?
    """,
        (exam_id,),
    ).fetchall()

    score = 0

    total = len(questions)

    for question in questions:
        answer = request.form.get(f"question_{question['id']}")

        if answer == question["correct_answer"]:
            score += 1

    exam_date = datetime.now().strftime("%d-%m-%Y %H:%M")

    try:
        conn.execute(
            """
            INSERT INTO results(
                user_id,
                exam_id,
                score,
                total,
                exam_date
            )

            VALUES(?,?,?,?,?)

        """,
            (session["user_id"], exam_id, score, total, exam_date),
        )

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()

        flash("Exam already submitted.")

        return redirect(url_for("student_dashboard"))

    conn.close()

    return redirect(url_for("result", exam_id=exam_id))


# ---------------- RESULT ---------------- #


@app.route("/result/<int:exam_id>")
@login_required
def result(exam_id):

    conn = get_db()

    result_data = conn.execute(
        """
        SELECT
            results.*,
            exams.title

        FROM results

        JOIN exams
        ON results.exam_id = exams.id

        WHERE
            results.user_id=?
            AND results.exam_id=?

    """,
        (session["user_id"], exam_id),
    ).fetchone()

    conn.close()

    if not result_data:
        flash("Result not found.")

        return redirect(url_for("student_dashboard"))

    percentage = 0

    if result_data["total"] > 0:
        percentage = (result_data["score"] / result_data["total"]) * 100

    return render_template(
        "result.html", result=result_data, percentage=round(percentage, 2)
    )


# ---------------- MY RESULTS ---------------- #


@app.route("/my_results")
@login_required
def my_results():

    if session.get("role") != "student":
        return redirect(url_for("index"))

    conn = get_db()

    results = conn.execute(
        """
        SELECT
            results.*,
            exams.title

        FROM results

        JOIN exams
        ON results.exam_id = exams.id

        WHERE results.user_id=?

        ORDER BY results.id DESC

    """,
        (session["user_id"],),
    ).fetchall()

    conn.close()

    return render_template("my_results.html", results=results)


# =====================================================
# ADMIN SECTION
# =====================================================


# ---------------- ADMIN DASHBOARD ---------------- #


@app.route("/admin")
@admin_required
def admin_dashboard():

    conn = get_db()

    exams = conn.execute("""
        SELECT
            exams.*,

            (
                SELECT COUNT(*)
                FROM questions
                WHERE questions.exam_id = exams.id
            ) AS question_count

        FROM exams

        ORDER BY exams.id DESC

    """).fetchall()

    student_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM users
        WHERE role='student'
    """).fetchone()["count"]

    result_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM results
    """).fetchone()["count"]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        exams=exams,
        student_count=student_count,
        result_count=result_count,
    )


# ---------------- CREATE EXAM ---------------- #


@app.route("/create_exam", methods=["GET", "POST"])
@admin_required
def create_exam():

    if request.method == "POST":
        title = request.form["title"].strip()

        duration = request.form["duration"]

        if not title:
            flash("Exam title is required.")

            return redirect(url_for("create_exam"))

        try:
            duration = int(duration)

            if duration <= 0:
                raise ValueError

        except ValueError:
            flash("Duration must be a positive number.")

            return redirect(url_for("create_exam"))

        conn = get_db()

        cursor = conn.execute(
            """
            INSERT INTO exams(title,duration)
            VALUES(?,?)
        """,
            (title, duration),
        )

        conn.commit()

        exam_id = cursor.lastrowid

        conn.close()

        flash("Exam created successfully.")

        return redirect(url_for("add_question", exam_id=exam_id))

    return render_template("create_exam.html")


# ---------------- ADD QUESTION ---------------- #


@app.route("/add_question/<int:exam_id>", methods=["GET", "POST"])
@admin_required
def add_question(exam_id):

    conn = get_db()

    exam_data = conn.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()

    if not exam_data:
        conn.close()

        flash("Exam not found.")

        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        question = request.form["question"].strip()

        option_a = request.form["option_a"].strip()

        option_b = request.form["option_b"].strip()

        option_c = request.form["option_c"].strip()

        option_d = request.form["option_d"].strip()

        correct_answer = request.form["correct_answer"]

        if not all([question, option_a, option_b, option_c, option_d]):
            conn.close()

            flash("Please fill all fields.")

            return redirect(url_for("add_question", exam_id=exam_id))

        conn.execute(
            """
            INSERT INTO questions(
                exam_id,
                question,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_answer
            )

            VALUES(?,?,?,?,?,?,?)

        """,
            (exam_id, question, option_a, option_b, option_c, option_d, correct_answer),
        )

        conn.commit()

        flash("Question added successfully.")

    question_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM questions
        WHERE exam_id=?
    """,
        (exam_id,),
    ).fetchone()["count"]

    conn.close()

    return render_template(
        "add_question.html", exam=exam_data, question_count=question_count
    )


# ---------------- MANAGE QUESTIONS ---------------- #


@app.route("/manage_questions/<int:exam_id>")
@admin_required
def manage_questions(exam_id):

    conn = get_db()

    exam_data = conn.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()

    questions = conn.execute(
        """
        SELECT *
        FROM questions
        WHERE exam_id=?
        ORDER BY id
    """,
        (exam_id,),
    ).fetchall()

    conn.close()

    return render_template("manage_questions.html", exam=exam_data, questions=questions)


# ---------------- DELETE QUESTION ---------------- #


@app.route("/delete_question/<int:question_id>/<int:exam_id>", methods=["POST"])
@admin_required
def delete_question(question_id, exam_id):

    conn = get_db()

    conn.execute(
        """
        DELETE FROM questions
        WHERE id=?
    """,
        (question_id,),
    )

    conn.commit()

    conn.close()

    flash("Question deleted.")

    return redirect(url_for("manage_questions", exam_id=exam_id))


# ---------------- DELETE EXAM ---------------- #


@app.route("/delete_exam/<int:exam_id>", methods=["POST"])
@admin_required
def delete_exam(exam_id):

    conn = get_db()

    # Delete results first
    conn.execute("DELETE FROM results WHERE exam_id=?", (exam_id,))

    # Delete questions
    conn.execute("DELETE FROM questions WHERE exam_id=?", (exam_id,))

    # Delete exam
    conn.execute("DELETE FROM exams WHERE id=?", (exam_id,))

    conn.commit()

    conn.close()

    flash("Exam deleted successfully.")

    return redirect(url_for("admin_dashboard"))


# ---------------- ADMIN RESULTS ---------------- #


@app.route("/admin_results")
@admin_required
def admin_results():

    conn = get_db()

    results = conn.execute("""
        SELECT
            results.*,
            users.name,
            users.email,
            exams.title

        FROM results

        JOIN users
        ON results.user_id = users.id

        JOIN exams
        ON results.exam_id = exams.id

        ORDER BY results.id DESC

    """).fetchall()

    conn.close()

    return render_template("admin_results.html", results=results)


# ---------------- RUN APP ---------------- #

# Initialize database when the application starts
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

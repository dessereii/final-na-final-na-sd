from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response
import sqlite3, json
from datetime import datetime
import os
import io
import csv
from io import BytesIO
from fpdf import FPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter



app = Flask(__name__)
app.secret_key = 'your_secret_key'
DB_NAME = 'database.db'

# ------------------ Database Setup ------------------
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            email TEXT,
                            password TEXT NOT NULL,
                            role TEXT NOT NULL,
                            student_number TEXT,
                            admin_email TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS attendance (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            student_number TEXT,
                            status TEXT,
                            timestamp TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS quizzes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT,
                            assigned_to TEXT,
                            deadline TEXT,
                            questions TEXT,
                            type TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS quiz_responses (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            student_number TEXT,
                            quiz_id INTEGER,
                            answers TEXT,
                            score REAL)''')
        cursor.execute("""CREATE TABLE IF NOT EXISTS exams (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT NOT NULL,
                            description TEXT,
                            questions TEXT NOT NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS assigned_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER,
    student_number TEXT,
    FOREIGN KEY (exam_id) REFERENCES exams(id)
)
""")
    cursor.execute("""
CREATE TABLE IF NOT EXISTS exam_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_number TEXT,
    exam_id INTEGER,
    answers TEXT,
    score INTEGER,
    FOREIGN KEY (exam_id) REFERENCES exams(id)
)
""")

init_db()

# ------------------ Routes ------------------
@app.route('/')
def select_role():
    return render_template('select_role.html')

@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if request.method == 'POST':
        email_or_number = request.form['email']
        password = request.form['password']
        
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            if role == 'student':
                cursor.execute("SELECT * FROM users WHERE student_number=? AND password=? AND role='student'", (email_or_number, password))
            else:
                cursor.execute("SELECT * FROM users WHERE email=? AND password=? AND role='admin'", (email_or_number, password))
            user = cursor.fetchone()
            if user:
                session['user_id'] = user[0]
                session['role'] = user[4].strip().lower()
                print("Logged in. Session now:", dict(session))  # Debug
                return redirect(url_for('admin_home') if role == 'admin' else url_for('student_home'))
            else:
                flash('Invalid credentials')

    return render_template('login.html', role=role)


@app.route('/signup/<role>', methods=['GET', 'POST'])
def signup(role):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form.get('email')
        student_number = request.form.get('student_number')
        admin_email = request.form.get('admin_email')
        password = request.form['password']

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO users (name, email, password, role, student_number, admin_email)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (name, email, password, role, student_number, admin_email))
            conn.commit()
        return redirect(url_for('login', role=role))

    return render_template('signup.html', role=role)

@app.route('/student/home')
def student_home():
    if session.get('role') != 'student':
        return redirect('/')
    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()
    return render_template('student_home.html', user=user)

@app.route('/admin/home')
def admin_home():
    if session.get('role') != 'admin':
        return redirect('/')
    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()
    return render_template('admin_home.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/student/attendance', methods=['GET', 'POST'])
def student_attendance():
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        if request.method == 'POST':
            status = request.form['status']
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO attendance (student_number, status, timestamp) VALUES (?, ?, ?)",
                           (student_number, status, timestamp))
            conn.commit()
            flash('Attendance recorded.')

        cursor.execute("SELECT status, timestamp FROM attendance WHERE student_number=? ORDER BY timestamp DESC", 
                       (student_number,))
        records = cursor.fetchall()
    
    return render_template('student_attendance.html', student_number=student_number, records=records)

@app.route('/student/attendance/export/<filetype>')
def export_student_attendance(filetype):
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]
        cursor.execute("SELECT status, timestamp FROM attendance WHERE student_number=?", (student_number,))
        records = cursor.fetchall()

    if filetype == 'csv':
        filename = f"{student_number}_attendance.csv"
        filepath = os.path.join('exports', filename)
        os.makedirs('exports', exist_ok=True)
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Status', 'Timestamp'])
            writer.writerows(records)
        return send_file(filepath, as_attachment=True)

    elif filetype == 'pdf':
        filename = f"{student_number}_attendance.pdf"
        filepath = os.path.join('exports', filename)
        os.makedirs('exports', exist_ok=True)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, f"Attendance Records - {student_number}", ln=True, align='C')
        pdf.ln(10)
        for status, timestamp in records:
            pdf.cell(200, 10, f"{status} - {timestamp}", ln=True)
        pdf.output(filepath)
        return send_file(filepath, as_attachment=True)

@app.route('/admin/attendance', methods=['GET', 'POST'])
def admin_attendance():
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, student_number, status, timestamp FROM attendance ORDER BY timestamp DESC")
        records = cursor.fetchall()
    
    return render_template('admin_attendance.html', records=records)

@app.route('/admin/attendance/edit/<int:record_id>', methods=['POST'])
def edit_attendance(record_id):
    new_status = request.form['status']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE attendance SET status=? WHERE id=?", (new_status, record_id))
        conn.commit()
    flash("Attendance updated.")
    return redirect(url_for('admin_attendance'))

@app.route('/admin/attendance/delete/<int:record_id>')
def delete_attendance(record_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attendance WHERE id=?", (record_id,))
        conn.commit()
    flash("Attendance deleted.")
    return redirect(url_for('admin_attendance'))

@app.route('/admin/attendance/export/<filetype>')
def export_admin_attendance(filetype):
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number, status, timestamp FROM attendance ORDER BY timestamp DESC")
        records = cursor.fetchall()

    if filetype == 'csv':
        filename = "all_attendance.csv"
        filepath = os.path.join('exports', filename)
        os.makedirs('exports', exist_ok=True)
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Student Number', 'Status', 'Timestamp'])
            writer.writerows(records)
        return send_file(filepath, as_attachment=True)

    elif filetype == 'pdf':
        filename = "all_attendance.pdf"
        filepath = os.path.join('exports', filename)
        os.makedirs('exports', exist_ok=True)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, "All Attendance Records", ln=True, align='C')
        pdf.ln(10)
        for sn, status, ts in records:
            pdf.cell(200, 10, f"{sn} - {status} - {ts}", ln=True)
        pdf.output(filepath)
        return send_file(filepath, as_attachment=True)
    
@app.route('/student/quizzes')
def student_quizzes():
    if session.get('role') != 'student':
        return redirect('/')
    
    student_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (student_id,))
        student_number = cursor.fetchone()[0]
        
        cursor.execute("SELECT * FROM quizzes WHERE assigned_to=? ORDER BY id DESC", (student_number,))
        quizzes = cursor.fetchall()

    return render_template('student_quizzes.html', quizzes=quizzes)

@app.route('/student/quiz/<int:quiz_id>', methods=['GET', 'POST'])
def take_quiz(quiz_id):
    if session.get('role') != 'student':
        return redirect('/')

    student_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (student_id,))
        student_number = cursor.fetchone()[0]

        if request.method == 'POST':
            answers = {}
            score = 0
            cursor.execute("SELECT questions FROM quizzes WHERE id=?", (quiz_id,))
            questions = json.loads(cursor.fetchone()[0])

            for i, q in enumerate(questions):
                ans = request.form.get(f'q{i}')
                answers[f'q{i}'] = ans
                if q['type'] == 'mcq' and ans == q['answer']:
                    score += 1  # 1 pt per correct MCQ

            cursor.execute('''INSERT INTO quiz_responses (student_number, quiz_id, answers, score)
                              VALUES (?, ?, ?, ?)''',
                           (student_number, quiz_id, json.dumps(answers), score))
            conn.commit()
            flash("Quiz submitted successfully.")
            return redirect(url_for('student_quizzes'))

        cursor.execute("SELECT title, questions FROM quizzes WHERE id=?", (quiz_id,))
        title, q_json = cursor.fetchone()
        questions = json.loads(q_json)

    return render_template('take_quiz.html', title=title, questions=questions)

@app.route('/student/quiz_results')
def student_quiz_results():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT qr.id, q.title, qr.score, qr.answers
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=?
        ''', (student_number,))
        records = cursor.fetchall()

    return render_template('student_quiz_results.html', records=records)

@app.route('/student/export_quiz_results/csv')
def export_quiz_results_csv():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=?
        ''', (student_number,))
        records = cursor.fetchall()

    output = make_response()
    writer = csv.writer(output)
    writer.writerow(['Quiz Title', 'Score'])
    writer.writerows(records)

    output.headers["Content-Disposition"] = "attachment; filename=quiz_results.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/student/export_quiz_results/pdf')
def export_quiz_results_pdf():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=?
        ''', (student_number,))
        records = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Quiz Results", ln=True, align='C')
    pdf.ln(10)

    for row in records:
        pdf.cell(200, 10, txt=f"{row[0]} - Score: {row[1]}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin1'))
    response.headers['Content-Disposition'] = 'attachment; filename=quiz_results.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response

@app.route('/admin/quizzes', methods=['GET', 'POST'])
def admin_manage_quizzes():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        duration = request.form['duration']
        c.execute('INSERT INTO quizzes (title, duration) VALUES (?, ?)', (title, duration))
        conn.commit()

    c.execute('SELECT * FROM quizzes')
    quizzes = c.fetchall()
    conn.close()
    return render_template('admin_manage_quizzes.html', quizzes=quizzes)

@app.route('/admin/quiz_submissions')
def admin_quiz_submissions():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT qr.id, qr.student_number, q.title, qr.answers, qr.score, qr.quiz_id
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE q.type = 'quiz'
        ''')
        records = cursor.fetchall()

    return render_template('admin_quiz_submissions.html', records=records)

@app.route('/admin/grade_quiz/<int:response_id>', methods=['GET', 'POST'])
def grade_quiz(response_id):
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        if request.method == 'POST':
            score = float(request.form['score'])
            cursor.execute("UPDATE quiz_responses SET score=? WHERE id=?", (score, response_id))
            conn.commit()
            flash("Score updated!")
            return redirect(url_for('admin_quiz_submissions'))

        cursor.execute("SELECT qr.answers, q.title FROM quiz_responses qr JOIN quizzes q ON qr.quiz_id = q.id WHERE qr.id=?", (response_id,))
        data = cursor.fetchone()

    return render_template('grade_quiz.html', data=data, response_id=response_id)

@app.route('/admin/export_quiz_results/csv')
def admin_export_quiz_csv():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT qr.student_number, q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE q.type = 'quiz'
        ''')
        records = cursor.fetchall()

    output = make_response()
    writer = csv.writer(output)
    writer.writerow(['Student Number', 'Quiz Title', 'Score'])
    writer.writerows(records)

    output.headers["Content-Disposition"] = "attachment; filename=quiz_report.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/admin/export_quiz_results/pdf')
def admin_export_quiz_pdf():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT qr.student_number, q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE q.type = 'quiz'
        ''')
        records = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Quiz Results Report", ln=True, align='C')
    pdf.ln(10)

    for row in records:
        pdf.cell(200, 10, txt=f"{row[0]} | {row[1]} | Score: {row[2]}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin1'))
    response.headers['Content-Disposition'] = 'attachment; filename=quiz_report.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response




@app.route('/student/exams')
def student_exams():
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute("SELECT * FROM quizzes WHERE assigned_to=? AND type='exam'", (student_number,))
        exams = cursor.fetchall()
    
    return render_template('student_exams.html', exams=exams)

@app.route('/student/take_exam')
def student_exams_to_take():
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]
        
        # Get exams assigned to this student that they haven't taken yet
        cursor.execute("""
            SELECT q.id, q.title FROM quizzes q
            WHERE q.type='exam'
        """)
        
        available_exams = cursor.fetchall()
    
    return render_template('exams_to_take.html', exams=available_exams)

@app.route('/student/exam/<int:exam_id>', methods=['GET', 'POST'])
def take_exam(exam_id):
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute("SELECT * FROM quizzes WHERE id=?", (exam_id,))
        exam = cursor.fetchone()

        if request.method == 'POST':
            submitted_answers = {}
            score = 0
            questions = json.loads(exam[4])  # questions field
            for i, q in enumerate(questions):
                ans = request.form.get(f'q{i}')
                submitted_answers[f'q{i}'] = ans
                if q['type'] == 'mcq' and ans == q['answer']:
                    score += 1

            cursor.execute('''INSERT INTO quiz_responses (student_number, quiz_id, answers, score)
                              VALUES (?, ?, ?, ?)''',
                           (student_number, exam_id, json.dumps(submitted_answers), score))
            conn.commit()
            flash("Exam submitted.")
            return redirect(url_for('student_exam_history'))

    questions = json.loads(exam[4])
    return render_template('take_exam.html', exam=exam, questions=questions)

@app.route('/student/exam/history')
def student_exam_history():
    if session.get('role') != 'student':
        return redirect('/')
    
    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''SELECT quizzes.title, quiz_responses.score, quiz_responses.answers
                          FROM quiz_responses 
                          JOIN quizzes ON quiz_responses.quiz_id = quizzes.id
                          WHERE quiz_responses.student_number=? AND quizzes.type='exam' ''', 
                          (student_number,))
        records = cursor.fetchall()

    return render_template('student_exam_history.html', records=records)

@app.route('/admin/create_exam', methods=['GET', 'POST'])
def create_exam():
    if session.get('role') != 'admin':
        return redirect('/')

    if request.method == 'POST':
        title = request.form['title']
        assigned_to = request.form['assigned_to']
        deadline = request.form['deadline']
        quiz_type = request.form['type']

        questions = []
        for i in range(1, 101):
            q_text = request.form.get(f'q{i}')
            q_type = request.form.get(f'q{i}_type')
            if q_text and q_type:
                question = {'question': q_text, 'type': q_type}
                if q_type == 'mcq':
                    options = [
                        request.form.get(f'q{i}_opt1'),
                        request.form.get(f'q{i}_opt2'),
                        request.form.get(f'q{i}_opt3'),
                        request.form.get(f'q{i}_opt4')
                    ]
                    question['options'] = options
                    question['answer'] = request.form.get(f'q{i}_correct')
                questions.append(question)

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO quizzes (title, assigned_to, deadline, questions, type)
                              VALUES (?, ?, ?, ?, ?)''',
                           (title, assigned_to, deadline, json.dumps(questions), quiz_type))
            conn.commit()
        flash("Quiz/Exam created successfully.")
        return redirect(url_for('admin_home'))

    return render_template('create_exam.html')

@app.route('/student/exam_results')
def student_exam_results():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT qr.id, q.title, qr.score, qr.answers
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=? AND q.type='exam'
        ''', (student_number,))
        records = cursor.fetchall()

    return render_template('student_exam_results.html', records=records)

@app.route('/student/export_exam_results/csv')
def export_exam_results_csv():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=? AND q.type='exam'
        ''', (student_number,))
        records = cursor.fetchall()

    output = make_response()
    writer = csv.writer(output)
    writer.writerow(['Exam Title', 'Score'])
    writer.writerows(records)

    output.headers["Content-Disposition"] = "attachment; filename=exam_results.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/student/export_exam_results/pdf')
def export_exam_results_pdf():
    if session.get('role') != 'student':
        return redirect('/')

    user_id = session['user_id']  # Changed from session['user'] to session['user_id']
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT student_number FROM users WHERE id=?", (user_id,))
        student_number = cursor.fetchone()[0]

        cursor.execute('''
            SELECT q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            WHERE qr.student_number=? AND q.type='exam'
        ''', (student_number,))
        records = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Exam Results", ln=True, align='C')
    pdf.ln(10)

    for row in records:
        pdf.cell(200, 10, txt=f"{row[0]} - Score: {row[1]}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin1'))
    response.headers['Content-Disposition'] = 'attachment; filename=exam_results.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response


@app.route('/admin/grade_short_answers')
def grade_short_answers():
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT qr.id, qr.student_number, q.title, qr.answers, q.questions 
            FROM quiz_responses qr 
            JOIN quizzes q ON qr.quiz_id = q.id
        ''')
        responses = cursor.fetchall()

    # Filter responses that contain short answer questions
    ungraded = []
    for row in responses:
        response_id, student_number, title, answers_json, questions_json = row
        answers = json.loads(answers_json)
        questions = json.loads(questions_json)

        if any(q['type'] == 'short' for q in questions):
            ungraded.append((response_id, student_number, title, questions, answers))

    return render_template('admin_grade.html', submissions=ungraded)

@app.route('/admin/submit_grades/<int:response_id>', methods=['POST'])
def submit_grades(response_id):
    if session.get('role') != 'admin':
        return redirect('/')
        
    scores = []
    total_score = 0

    for key in request.form:
        if key.startswith("score_"):
            score = float(request.form[key])
            scores.append(score)
            total_score += score

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE quiz_responses SET score=? WHERE id=?", (total_score, response_id))
        conn.commit()

    flash("Scores submitted successfully.")
    return redirect(url_for('grade_short_answers'))

# ---------------------- EXAM MANAGEMENT (ADMIN) ----------------------

@app.route('/admin/manage_exams')
def admin_manage_exams():
    if session.get('role') != 'admin':
        return redirect('/')
        
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row  # <-- This line makes rows dict-like
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM exams")
        exams = cursor.fetchall()
    return render_template('admin_manage_exams.html', exams=exams)

@app.route('/admin/export_exam_results/csv')
def admin_export_exam_results_csv():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.name, u.student_number, q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            JOIN users u ON qr.student_number = u.student_number
            WHERE q.type='exam'
        ''')
        records = cursor.fetchall()

    output = make_response()
    writer = csv.writer(output)
    writer.writerow(['Student Name', 'Student Number', 'Exam Title', 'Score'])
    writer.writerows(records)

    output.headers["Content-Disposition"] = "attachment; filename=all_exam_results.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/admin/export_exam_results/pdf')
def admin_export_exam_results_pdf():
    if session.get('role') != 'admin':
        return redirect('/')

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.name, u.student_number, q.title, qr.score
            FROM quiz_responses qr
            JOIN quizzes q ON qr.quiz_id = q.id
            JOIN users u ON qr.student_number = u.student_number
            WHERE q.type='exam'
        ''')
        records = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="All Students - Exam Results", ln=True, align='C')
    pdf.ln(10)

    for row in records:
        name, student_number, title, score = row
        pdf.cell(200, 10, txt=f"{name} ({student_number}) - {title} - Score: {score}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin1'))
    response.headers['Content-Disposition'] = 'attachment; filename=all_exam_results.pdf'
    response.headers['Content-Type'] = 'application/pdf'
    return response

@app.route('/admin/exam_submissions')
def admin_exam_submissions():
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # First, let's check the structure of the exam_responses table
        cursor.execute("PRAGMA table_info(exam_responses)")
        columns = cursor.fetchall()
        column_names = [col['name'] for col in columns]
        
        # Debug: Print column names to console
        print("Exam responses table columns:", column_names)
        
        # Adjust the query based on your actual table structure
        # For now, just get all exam responses
        cursor.execute("SELECT * FROM exam_responses")
        records = cursor.fetchall()
        
        # Debug: Print first record structure
        if records:
            print("First record keys:", records[0].keys())
    
    return render_template('exam_responses.html', records=records)

@app.route('/admin/grade_exam/<int:response_id>')
def grade_exam(response_id):
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT er.id, u.name, e.title, er.answers, e.questions, e.correct_answers, er.exam_id
            FROM exam_responses er
            JOIN users u ON er.student_id = u.id
            JOIN exams e ON er.exam_id = e.id
            WHERE er.id = ?
        ''', (response_id,))
        
        response = cursor.fetchone()
    
    if not response:
        flash('Exam response not found', 'error')
        return redirect(url_for('admin_exam_submissions'))
    
    # Pass this data to the grade_exam template
    return render_template('grade_exam.html', response=response)

@app.route('/admin/submit_exam_grade/<int:response_id>', methods=['POST'])
def submit_exam_grade(response_id):
    if session.get('role') != 'admin':
        return redirect('/')
    
    with sqlite3.connect(DB_NAME) as conn:
        # Get the exam questions count
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.questions
            FROM exam_responses er
            JOIN exams e ON er.exam_id = e.id
            WHERE er.id = ?
        ''', (response_id,))
        
        result = cursor.fetchone()
        if not result:
            flash('Exam response not found', 'error')
            return redirect(url_for('admin_exam_submissions'))
        
        # Calculate total score
        import json
        questions = json.loads(result[0])
        total_points = 0
        
        for i in range(len(questions)):
            points = float(request.form.get(f'points{i}', 0))
            total_points += points
        
        # Update the response with the score
        cursor.execute('''
            UPDATE exam_responses
            SET score = ?
            WHERE id = ?
        ''', (total_points, response_id))
        
        conn.commit()
    
    flash('Exam graded successfully!', 'success')
    return redirect(url_for('admin_exam_submissions'))

if __name__ == '__main__':
    if not os.path.exists(DB_NAME):
        init_db()
    app.run(debug=True)
# ─────────────────────────────────────────────────────────────────
#  CityCare  –  app.py  (FINAL: AI chatbot + email + feedback)

# ─────────────────────────────────────────────────────────────────

from flask import Flask, session, render_template, request, jsonify, redirect, url_for, flash
import mysql.connector
import os
import uuid

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import datetime
from functools import wraps

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests as http_requests

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import nltk
nltk.download('punkt', quiet=True)


# new added
import os, uuid
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── App setup ──────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "citycare_secret_2024"
app.config['UPLOAD_FOLDER'] = './static/pictures/'

# ── Email config ───────────────────────────────────────────────────
# HOW TO ENABLE:
#   1. Go to myaccount.google.com → Security → 2-Step Verification (enable it)
#   2. Search "App Passwords" in your Google account
#   3. Generate one for "Mail" — copy the 16-char password
#   4. Paste your Gmail and that password below, set EMAIL_ENABLED = True
EMAIL_SENDER   = "your_gmail@gmail.com"
EMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"   # 16-char app password (no spaces)
EMAIL_ENABLED  = False                    # ← change to True after filling above

# ── Anthropic AI config ────────────────────────────────────────────
# HOW TO ENABLE:
#   1. Go to console.anthropic.com → API Keys → Create key
#   2. Paste the key below (starts with sk-ant-)
#   3. Set AI_ENABLED = True
ANTHROPIC_API_KEY = "sk-ant-your-key-here"
AI_ENABLED        = False                 # ← change to True after filling above

# ══════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════

def database():
    con = mysql.connector.connect(
        user="root",
        password="root",
        host="localhost",
        port="3306",
        database="waste_management_system"
    )
    return con, con.cursor(dictionary=True)
def create_staff_notification(staff_id, title, message, complaint_id=None):
    con, cur = database()
    cur.execute("""
        INSERT INTO staff_notifications (staff_id, type, title, message, complaint_id)
        VALUES (%s, %s, %s, %s, %s)
    """, (staff_id, 'assignment', title, message, complaint_id))
    con.commit()
    con.close()

# ══════════════════════════════════════════════════════════════════
#  PRIORITY ENGINE
# ══════════════════════════════════════════════════════════════════

from datetime import datetime

SEVERITY_MAP = {'Critical': 10, 'High': 7, 'Medium': 4, 'Low': 1}

def compute_priority(severity, created_at, area, con, cur):
    sev_score = SEVERITY_MAP.get(severity, 4)

    # ✅ FIX: Convert string → datetime
    if created_at and isinstance(created_at, str):
        try:
            created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print("Date conversion error:", created_at, e)
            created_at = None

    waiting_days = min((datetime.now() - created_at).days, 30) if created_at else 0

    cur.execute(
        "SELECT COUNT(*) FROM complaints WHERE location=%s AND status!='resolved'", (area,)
    )
    result = cur.fetchone()
    area_load = min(list(result.values())[0], 10)

    return round((sev_score * 0.50) + (waiting_days * 0.30) + (area_load * 0.20), 2)

def recalculate_all_priorities():
    con, cur = database()
    cur.execute(
        "SELECT complaint_id, severity, created_at, location "
        "FROM complaints WHERE status != 'resolved'"
    )
    for cid, sev, created_at, loc in cur.fetchall():
        score = compute_priority(sev, created_at, loc, con, cur)
        cur.execute(
            "UPDATE complaints SET priority_score=%s, severity_score=%s WHERE complaint_id=%s",
            (score, SEVERITY_MAP.get(sev, 4), cid)
        )
    con.commit()
    con.close()

def suggest_staff(con, cur):
    cur.execute(
        "SELECT id, name FROM staff_accounts "
        "WHERE available=1 ORDER BY current_load ASC, RAND() LIMIT 1"
    )
    r = cur.fetchone()
    return (r['id'], r['name']) if r else (None, "Unassigned")

# ══════════════════════════════════════════════════════════════════
#  EMAIL NOTIFICATION
# ══════════════════════════════════════════════════════════════════

def send_status_email(to_email, user_name, complaint_id, category, location, new_status):
    if not EMAIL_ENABLED or not to_email:
        return False
    try:
        colors = {
            'resolved':   '#1e8449',
            'verified':   '#1a6ebf',
            'processing': '#6b30b5',
            'pending':    '#e67e22'
        }
        color = colors.get(new_status.lower(), '#1a4d2e')

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;">
          <div style="background:#0d1f13;padding:24px 32px;border-radius:12px 12px 0 0;">
            <h2 style="color:#fff;margin:0;">
              <span style="color:#52b788;">CITY</span>CARE
            </h2>
          </div>
          <div style="background:#fff;padding:32px;border:1px solid #d0e8d8;
                      border-top:none;border-radius:0 0 12px 12px;">
            <p style="font-size:16px;color:#1b2d23;">Hi <b>{user_name}</b>,</p>
            <p style="color:#5a7a65;line-height:1.7;">
              Your complaint <b>#{complaint_id}</b>
              ({category} at {location}) has been updated.
            </p>
            <div style="background:#f0f6f2;border-radius:10px;padding:20px;
                        margin:20px 0;text-align:center;">
              <p style="margin:0 0 8px;font-size:13px;color:#5a7a65;
                        text-transform:uppercase;">New Status</p>
              <span style="background:{color};color:#fff;padding:8px 24px;
                           border-radius:50px;font-size:16px;font-weight:700;">
                {new_status.capitalize()}
              </span>
            </div>
            {"<p style='color:#52b788;font-weight:600;'>Your complaint is resolved! Please log in to CityCare and leave feedback.</p>" if new_status.lower()=='resolved' else ""}
            <p style="color:#5a7a65;font-size:14px;margin-top:12px;">
              Log in to CityCare to track your complaint.
            </p>
            <p style="margin-top:24px;font-size:13px;color:#aaa;">
              &mdash; The CityCare Team
            </p>
          </div>
        </div>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"CityCare: Complaint #{complaint_id} → {new_status.capitalize()}"
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = to_email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[Email error] {e}")
        return False

# ══════════════════════════════════════════════════════════════════
#  AI CHATBOT  (Anthropic Claude)
# ══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are the CityCare AI Assistant — a helpful, friendly assistant for a
smart civic waste management platform serving urban residents in India.

Your role is to help citizens with:
1. Waste management advice — composting, recycling, segregation, hazardous/medical waste disposal
2. How to use the CityCare platform — submitting/tracking complaints, understanding priority scores
3. General civic sanitation awareness and best practices
4. Explaining waste categories (Organic, Hazardous, Liquid, Domestic)
5. Environmental awareness and sustainability tips

Guidelines:
- Keep answers concise, practical, and friendly
- Use simple language — many users may not be tech-savvy
- Reference Indian context where relevant (BBMP, municipal corporations, Swachh Bharat, etc.)
- When relevant, remind users they can submit a complaint directly on CityCare
- If asked unrelated questions, politely redirect to waste/civic topics
- Never make up specific local bylaws or government schemes without being sure"""


def ask_claude(user_message, conversation_history):
    """Call Anthropic Claude API with full conversation history for context."""
    if not AI_ENABLED:
        return None
    try:
        messages = conversation_history + [{"role": "user", "content": user_message}]
        response = http_requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 600,
                "system": SYSTEM_PROMPT,
                "messages": messages
            },
            timeout=20
        )
        if response.status_code == 200:
            return response.json()["content"][0]["text"]
        print(f"[Anthropic error] {response.status_code}: {response.text}")
        return None
    except Exception as e:
        print(f"[Claude exception] {e}")
        return None

# ══════════════════════════════════════════════════════════════════
#  PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/logout")
def logout():
    session.clear()
    return render_template("index.html")

# ══════════════════════════════════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════════════════════════════════

@app.route("/admin")
def admin():
    return render_template("admin.html")
# @app.route("/admin")
# def admin():
#     return redirect('/adminhome')
@app.route('/admin_loginchk', methods=['POST'])
def admin_loginchk():
    uid = request.form['uid']
    pwd = request.form['pwd']

    if uid == 'admin' and pwd == 'admin':
        session['admin'] = uid
        return redirect(url_for('adminhome'))
    else:
        return render_template('admin.html', msg2="Invalid")

@app.route("/adminhome")
def adminhome():
    if 'admin' not in session:
        return redirect(url_for('admin'))
 
    con, cur = database()
 
    # ── Total complaints ──────────────────────────────────────
    cur.execute("SELECT COUNT(*) AS cnt FROM complaints")
    total = cur.fetchone()['cnt']
 
    # ── Pending ───────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE status = 'pending'")
    pending = cur.fetchone()['cnt']
 
    # ── Resolved ──────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE status = 'resolved'")
    resolved = cur.fetchone()['cnt']
 
    # ── Critical + High count ─────────────────────────────────
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE severity IN ('Critical','High')"
    )
    critical_count = cur.fetchone()['cnt']
 
    # ── Average resolution time (days) ────────────────────────
    cur.execute(
        """SELECT ROUND(AVG(DATEDIFF(resolved_at, created_at)), 1) AS avg_d
           FROM complaints
           WHERE status = 'resolved' AND resolved_at IS NOT NULL"""
    )
    avg_row        = cur.fetchone()
    avg_resolution = avg_row['avg_d'] if avg_row and avg_row['avg_d'] else 0
 
    # ── Unassigned Critical/High (for AI alert) ───────────────
    cur.execute(
        """SELECT COUNT(*) AS cnt FROM complaints
           WHERE severity IN ('Critical','High')
             AND (assigned_staff IS NULL OR assigned_staff = '')"""
    )
    unassigned_critical = cur.fetchone()['cnt']
 
    # ── Pending staff approvals ───────────────────────────────
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM staff_accounts WHERE is_approved = 0"
    )
    pending_approvals = cur.fetchone()['cnt']
 
    # ── Active approved staff count ───────────────────────────
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM staff_accounts WHERE is_approved = 1 AND is_active = 1"
    )
    active_staff_count = cur.fetchone()['cnt']
 
    # ── Complaints ordered by priority (for table) ────────────
    cur.execute(
        """SELECT c.complaint_id, c.user_name, c.category,
                  c.location, c.status, c.severity,
                  c.priority_score, c.assigned_staff,
                  c.created_at, c.staff_id
           FROM complaints c
           ORDER BY c.priority_score DESC
           LIMIT 50"""
    )
    complaints = cur.fetchall()
 
    # ── Category distribution (for donut chart) ───────────────
    cur.execute(
        """SELECT category, COUNT(*) AS cnt
           FROM complaints
           GROUP BY category
           ORDER BY cnt DESC"""
    )
    cat_data = [(r['category'] or 'Unknown', r['cnt']) for r in cur.fetchall()]
 
    # ── Hotspot areas (top 5 locations by complaint count) ────
    cur.execute(
        """SELECT location, COUNT(*) AS cnt
           FROM complaints
           WHERE location IS NOT NULL AND location != ''
           GROUP BY location
           ORDER BY cnt DESC
           LIMIT 5"""
    )
    hotspots = [(r['location'], r['cnt']) for r in cur.fetchall()]
 
    # ── Staff status list (from staff_accounts – new table) ───
    # Shows approved staff with their current active task load
    cur.execute(
        """SELECT sa.id, sa.name, sa.designation, sa.zone,
                  sa.performance_score, sa.avg_rating,
                  COUNT(c.complaint_id) AS active_load
           FROM staff_accounts sa
           LEFT JOIN complaints c
             ON c.staff_id = sa.id
             AND c.status NOT IN ('resolved', 'Resolved')
           WHERE sa.is_approved = 1 AND sa.is_active = 1
           GROUP BY sa.id, sa.name, sa.designation,
                    sa.zone, sa.performance_score, sa.avg_rating
           ORDER BY active_load ASC, sa.performance_score DESC
           LIMIT 8"""
    )
    staff_list = cur.fetchall()
 
    con.close()
 
    return render_template(
        'admin_home.html',
        total              = total,
        pending            = pending,
        resolved           = resolved,
        critical_count     = critical_count,
        avg_resolution     = avg_resolution,
        unassigned_critical= unassigned_critical,
        pending_approvals  = pending_approvals,
        active_staff_count = active_staff_count,
        complaints         = complaints,
        cat_data           = cat_data,
        hotspots           = hotspots,
        staff_list         = staff_list,
    )
@app.route("/add_questions2", methods=["GET", "POST"])
def add_questions2():
    con, cur = database()
    cur.execute(
        "INSERT INTO questions(question,answer) VALUES (%s,%s)",
        (request.form['qns'], request.form['ans'])
    )
    con.commit()
    cur.execute("SELECT qid, question, answer FROM questions ORDER BY qid DESC")
    all_qa = cur.fetchall()
    con.close()
    return render_template("add_questions.html", msg="Entry added!", all_qa=all_qa)

@app.route("/edit_question/<int:qid>")
def edit_question(qid):
    con, cur = database()
    cur.execute("SELECT qid, question, answer FROM questions WHERE qid=%s", (qid,))
    edit_qa = cur.fetchone()
    cur.execute("SELECT qid, question, answer FROM questions ORDER BY qid DESC")
    all_qa = cur.fetchall()
    con.close()
    return render_template("add_questions.html", edit_qa=edit_qa, all_qa=all_qa)

@app.route("/update_question", methods=["POST"])
def update_question():
    con, cur = database()
    cur.execute(
        "UPDATE questions SET question=%s, answer=%s WHERE qid=%s",
        (request.form['qns'], request.form['ans'], request.form['qid'])
    )
    con.commit()
    cur.execute("SELECT qid, question, answer FROM questions ORDER BY qid DESC")
    all_qa = cur.fetchall()
    con.close()
    return render_template("add_questions.html", msg="Entry updated!", all_qa=all_qa)

@app.route("/delete_question/<int:qid>")
def delete_question(qid):
    con, cur = database()
    cur.execute("DELETE FROM questions WHERE qid=%s", (qid,))
    con.commit()
    cur.execute("SELECT qid, question, answer FROM questions ORDER BY qid DESC")
    all_qa = cur.fetchall()
    con.close()
    return render_template("add_questions.html", msg2="Entry deleted.", all_qa=all_qa)

# ── Complaints ─────────────────────────────────────────────────────
@app.route("/view_complaints")
def view_complaints():
    recalculate_all_priorities()
    con, cur = database()
    cur.execute(
        "SELECT complaint_id, user_name, userid, phone_number, category, "
        "location, adddress, waste_image, status, severity, priority_score, "
        "assigned_staff, created_at FROM complaints ORDER BY priority_score DESC"
    )
    values = cur.fetchall()
    cur.execute("SELECT id, name FROM staff_accounts WHERE available=1")
    staff_list = cur.fetchall()
    con.close()
    return render_template("view_complaints2.html", rawdata=values, staff_list=staff_list)

@app.route("/update_status/<cid>")
def update_status(cid):
    con, cur = database()
    cur.execute(
        "SELECT id, name FROM staff_accounts WHERE available=1 ORDER BY current_load ASC"
    )
    staff_list = cur.fetchall()
    con.close()
    return render_template("status_update.html", id=cid, staff_list=staff_list)

@app.route("/update_status2", methods=["GET", "POST"])
def update_status2():
    cid   = request.form["id"]
    sts   = request.form.get('status')
    sid   = request.form.get('staff_id')
    sname = request.form.get('staff_name', '')

    con, cur = database()

    # Get user email for notification
    cur.execute(
        "SELECT c.userid, u.email, u.user_name, c.category, c.location "
        "FROM complaints c JOIN users u ON c.userid = u.userid "
        "WHERE c.complaint_id = %s", (cid,)
    )
    row = cur.fetchone()
    user_email = user_name = category = location = None
    if row:
        _, user_email, user_name, category, location = row

    rc = ", resolved_at=NOW()" if sts == 'resolved' else ""

    if sid:
        cur.execute(
            f"UPDATE complaints SET status=%s, assigned_staff=%s, staff_id=%s{rc} "
            f"WHERE complaint_id=%s",
            (sts, sname, sid, cid)
        )
        if sts == 'resolved':
            cur.execute(
                "UPDATE staff_accounts SET current_load=GREATEST(current_load-1,0) "
                "WHERE id=%s", (sid,)
            )
        else:
            cur.execute(
                "UPDATE staff_accounts SET current_load=current_load+1 WHERE id=%s", (sid,)
            )
    else:
        cur.execute(
            f"UPDATE complaints SET status=%s{rc} WHERE complaint_id=%s", (sts, cid)
        )

    con.commit()

    # Send email notification
    if user_email:
        send_status_email(user_email, user_name, cid, category, location, sts)

    cur.execute(
        "SELECT complaint_id, user_name, userid, phone_number, category, "
        "location, adddress, waste_image, status, severity, priority_score, "
        "assigned_staff, created_at FROM complaints ORDER BY priority_score DESC"
    )
    values = cur.fetchall()
    cur.execute("SELECT id, name FROM staff_accounts WHERE available=1")
    staff_list = cur.fetchall()
    con.close()

    return render_template(
        "view_complaints2.html", msg="Status updated!",
        rawdata=values, staff_list=staff_list
    )

# @app.route("/auto_assign/<int:cid>")
# def auto_assign(cid):
#     con, cur = database()
#     staff_id, staff_name = suggest_staff(con, cur)
#     if staff_id:
#         cur.execute(
#             "UPDATE complaints SET assigned_staff=%s, staff_id=%s WHERE complaint_id=%s",
#             (staff_name, staff_id, cid)
#         )
#         cur.execute(
#             "UPDATE staff_accounts SET current_load=current_load+1 WHERE staff_id=%s", (staff_id,)
#         )
#         con.commit()
#     con.close()
#     return redirect('/view_complaints')

# ── Admin Feedback view ────────────────────────────────────────────
@app.route("/admin_feedback")
def admin_feedback():
    con, cur = database()
    cur.execute(
        "SELECT f.feedback_id, f.complaint_id, f.userid, f.rating, f.comment, "
        "f.submitted_at, c.category, c.location "
        "FROM feedback f JOIN complaints c ON f.complaint_id = c.complaint_id "
        "ORDER BY f.submitted_at DESC"
    )
    feedbacks = cur.fetchall()
    cur.execute("SELECT AVG(rating) FROM feedback WHERE rating IS NOT NULL")
    ar = cur.fetchone()[0]
    avg_rating = round(ar, 1) if ar else "N/A"
    con.close()
    return render_template("admin_feedback.html", feedbacks=feedbacks, avg_rating=avg_rating)

@app.route("/api/analytics")
def api_analytics():
    con, cur = database()
    cur.execute("SELECT category, COUNT(*) FROM complaints GROUP BY category")
    cat_raw = cur.fetchall()
    cur.execute(
        "SELECT location, COUNT(*) FROM complaints WHERE status!='resolved' "
        "GROUP BY location ORDER BY COUNT(*) DESC LIMIT 6"
    )
    area_raw = cur.fetchall()
    cur.execute("SELECT severity, COUNT(*) FROM complaints GROUP BY severity")
    sev_raw = cur.fetchall()
    cur.execute(
        "SELECT DATE(created_at) as d, COUNT(*) "
        "FROM complaints GROUP BY d ORDER BY d DESC LIMIT 7"
    )
    trend_raw = cur.fetchall()
    con.close()
    return jsonify({
        "categories": [{"label": r[0], "value": r[1]} for r in cat_raw],
        "areas":      [{"label": r[0], "value": r[1]} for r in area_raw],
        "severities": [{"label": r[0], "value": r[1]} for r in sev_raw],
        "trend":      [{"date": str(r[0]), "count": r[1]} for r in trend_raw],
    })

# ══════════════════════════════════════════════════════════════════
#  USER
# ══════════════════════════════════════════════════════════════════

@app.route("/user")
def user():
    return render_template("user.html")

@app.route("/user_signup")
def user_signup():
    return render_template("user_reg.html")

@app.route("/user_register", methods=["GET", "POST"])
def user_register():
    if request.method == "POST":
        name = request.form['name']
        uid  = request.form['usid']
        pwd  = request.form['pwd']
        mail = request.form['email']
        mno  = request.form['phno']

        con, cur = database()

        # ✅ FIXED: use alias + dictionary access
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE userid=%s",
            (uid,)
        )
        result = cur.fetchone()

        if result['cnt'] > 0:
            con.close()
            return render_template("user_reg.html", msg="Already exists!")

        # Insert new user
        cur.execute(
            "INSERT INTO users (user_name, userid, email, passwrd, phno) VALUES (%s,%s,%s,%s,%s)",
            (name, uid, mail, pwd, mno)
        )

        con.commit()
        con.close()

        return render_template("user.html", msg="Registered Successfully! Login here.")

    # ✅ GET request
    return render_template("user_reg.html")

@app.route("/user_loginchk", methods=["GET", "POST"])
def user_loginchk():
    if request.method == "POST":
        uid = request.form.get("userid")
        pwd = request.form.get("pwd")

        con, cur = database()

        # ✅ use passwrd (your actual column)
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE userid=%s AND passwrd=%s",
            (uid, pwd)
        )

        result = cur.fetchone()

        if result['cnt'] > 0:
            session['uid'] = uid
            con.close()
            return redirect("/userhome")

        con.close()
        return render_template("user.html", msg2="Invalid Credentials")

    return render_template("user.html")

@app.route("/userhome")
def userhome():
    uid = session.get('uid')
    if not uid:
        return redirect('/user')

    con, cur = database()

    # Total complaints
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE userid=%s",
        (uid,)
    )
    total = cur.fetchone()['cnt']

    # Pending complaints
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE userid=%s AND status='pending'",
        (uid,)
    )
    pending = cur.fetchone()['cnt']

    # Resolved complaints
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE userid=%s AND status='resolved'",
        (uid,)
    )
    resolved = cur.fetchone()['cnt']

    # Average resolution time
    cur.execute(
        """SELECT AVG(DATEDIFF(resolved_at, created_at)) AS avg_d
           FROM complaints
           WHERE userid=%s AND resolved_at IS NOT NULL""",
        (uid,)
    )
    avg_row = cur.fetchone()
    ar = avg_row['avg_d']
    avg_days = round(ar, 1) if ar else "N/A"

    # Latest complaint
    cur.execute(
        """SELECT category, location, status, priority_score, created_at
           FROM complaints
           WHERE userid=%s
           ORDER BY created_at DESC
           LIMIT 1""",
        (uid,)
    )
    latest = cur.fetchone()

    con.close()

    return render_template(
        "user_home.html",
        total=total,
        pending=pending,
        resolved=resolved,
        avg_days=avg_days,
        latest=latest
    )

@app.route("/create_complaint")
def create_complaint():
    return render_template("create_complaint.html")

@app.route("/complaint_store", methods=["GET", "POST"])
def complaint_store():
    uid = session.get('uid')
    if not uid:
        return redirect('/user')
    con, cur = database()
    cur.execute("SELECT * FROM users WHERE userid=%s", (uid,))
    user_row = cur.fetchone()
    name, mno = user_row['user_name'], user_row['phno']
    category = request.form['type']
    location = request.form['area'].strip().title()
    addr     = request.form['address']
    severity = request.form.get('severity', 'Medium')
    file     = request.files['pic']
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    sev_score  = SEVERITY_MAP.get(severity, 4)
    created_at = datetime.now()
    priority   = compute_priority(severity, created_at, location, con, cur)
    staff_id, staff_name = suggest_staff(con, cur)
    if staff_id:
        create_staff_notification(
        staff_id,
        "New Complaint Assigned",
        f"You have been assigned a complaint in {location}",
        None
    )
    cur.execute(
        "INSERT INTO complaints "
        "(user_name,userid,phone_number,category,location,adddress,"
        "waste_image,status,severity,severity_score,priority_score,"
        "assigned_staff,staff_id,created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (name, uid, mno, category, location, addr, filename,
         'pending', severity, sev_score, priority, staff_name, staff_id, created_at)
    )
    if staff_id:
        cur.execute(
            "UPDATE staff_accounts SET current_load=current_load+1 WHERE id=%s", (staff_id,)
        )
    con.commit()
    con.close()
    return render_template("create_complaint.html", msg="Complaint submitted successfully!")

@app.route("/view_complaints_user")
def view_complaints_user():
    uid = session.get('uid')
    if not uid:
        return redirect('/user')
    con, cur = database()
    # JOIN feedback so we know if feedback already exists (col 13 = rating)
    cur.execute(
        "SELECT c.complaint_id, c.user_name, c.userid, c.phone_number, c.category, "
        "c.location, c.adddress, c.waste_image, c.status, c.severity, c.priority_score, "
        "c.assigned_staff, c.created_at, f.rating "
        "FROM complaints c "
        "LEFT JOIN feedback f ON c.complaint_id = f.complaint_id "
        "WHERE c.userid=%s ORDER BY c.priority_score DESC",
        (uid,)
    )
    values = cur.fetchall()
    con.close()
    return render_template("view_complaints.html", rawdata=values)

@app.route("/complaint_update/<cid>")
def complaint_update(cid):
    con, cur = database()
    cur.execute("SELECT * FROM complaints WHERE complaint_id=%s", (cid,))
    row = cur.fetchone()
    con.close()
    return render_template(
        "complaint_upadte.html",
        id=cid,
        category=row[4],
        location=row[5],
        address=row[6],
        severity=row[9] if row[9] else 'Medium'
    )

@app.route("/complaint_update2", methods=["POST", "GET"])
def complaint_update2():
    cid      = request.form['id']
    category = request.form['category']
    location = request.form['location']
    address  = request.form['address']
    severity = request.form.get('severity', 'Medium')
    file     = request.files['pic']
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    sev_score = SEVERITY_MAP.get(severity, 4)
    con, cur  = database()
    cur.execute("SELECT created_at FROM complaints WHERE complaint_id=%s", (cid,))
    row = cur.fetchone()
    created_at = row[0] if row else datetime.now()
    priority   = compute_priority(severity, created_at, location, con, cur)
    cur.execute(
        "UPDATE complaints SET category=%s, location=%s, adddress=%s, waste_image=%s, "
        "severity=%s, severity_score=%s, priority_score=%s WHERE complaint_id=%s",
        (category, location, address, filename, severity, sev_score, priority, cid)
    )
    con.commit()
    cur.execute(
        "SELECT c.complaint_id, c.user_name, c.userid, c.phone_number, c.category, "
        "c.location, c.adddress, c.waste_image, c.status, c.severity, c.priority_score, "
        "c.assigned_staff, c.created_at, f.rating "
        "FROM complaints c "
        "LEFT JOIN feedback f ON c.complaint_id = f.complaint_id "
        "WHERE c.userid=%s ORDER BY c.priority_score DESC",
        (session.get('uid'),)
    )
    rslt = cur.fetchall()
    con.close()
    return render_template("view_complaints.html", msg="Complaint updated!", rawdata=rslt)

@app.route("/complaint_delete/<cid>")
def complaint_delete(cid):
    uid = session.get('uid')
    con, cur = database()
    cur.execute("SELECT staff_id FROM complaints WHERE complaint_id=%s", (cid,))
    row = cur.fetchone()
    if row and row[0]:
        cur.execute(
            "UPDATE staff_accounts SET current_load=GREATEST(current_load-1,0) "
            "WHERE id=%s", (row['staff_id'],)
        )
    cur.execute("DELETE FROM feedback WHERE complaint_id=%s", (cid,))
    cur.execute("DELETE FROM complaints WHERE complaint_id=%s", (cid,))
    con.commit()
    cur.execute(
        "SELECT c.complaint_id, c.user_name, c.userid, c.phone_number, c.category, "
        "c.location, c.adddress, c.waste_image, c.status, c.severity, c.priority_score, "
        "c.assigned_staff, c.created_at, f.rating "
        "FROM complaints c "
        "LEFT JOIN feedback f ON c.complaint_id = f.complaint_id "
        "WHERE c.userid=%s ORDER BY c.priority_score DESC",
        (uid,)
    )
    rslt = cur.fetchall()
    con.close()
    return render_template("view_complaints.html", rawdata=rslt, msg2="Complaint deleted.")

# ── Feedback ───────────────────────────────────────────────────────
@app.route("/submit_feedback/<int:cid>")
def submit_feedback(cid):
    if not session.get('uid'):
        return redirect('/user')
    return render_template("feedback.html", complaint_id=cid)

@app.route("/submit_feedback2", methods=["POST"])
def submit_feedback2():
    uid          = session.get('uid')
    complaint_id = request.form['complaint_id']
    rating       = request.form['rating']
    comment      = request.form.get('comment', '')
    con, cur = database()
    cur.execute(
        "INSERT INTO feedback (complaint_id, userid, rating, comment) "
        "VALUES (%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE rating=%s, comment=%s",
        (complaint_id, uid, rating, comment, rating, comment)
    )
    con.commit()
    con.close()
    return redirect('/view_complaints_user')

# ══════════════════════════════════════════════════════════════════
#  CHATBOT  (Claude AI with TF-IDF fallback)
# ══════════════════════════════════════════════════════════════════

@app.route("/chatbot")
def chatbot():
    return render_template("chatbot2.html", ai_enabled=AI_ENABLED)

@app.route('/ask', methods=['POST'])
def ask_question():
    data     = request.json
    message  = data.get('question', '').strip()
    history  = data.get('history', [])   # list of {role, content} dicts

    if not message:
        return jsonify({"answer": "Please ask a valid question.", "source": "error"})

    # Try Claude AI first
    if AI_ENABLED:
        ai_answer = ask_claude(message, history[-10:])  # send last 10 turns for context
        if ai_answer:
            return jsonify({"answer": ai_answer, "source": "ai"})

    # Fallback: TF-IDF database match
    return jsonify({"answer": find_best_match(message.lower()), "source": "db"})

_qa_data = None

def fetch_data():
    global _qa_data
    con, cur = database()
    cur.execute("SELECT question, answer FROM questions")
    _qa_data = cur.fetchall()
    con.close()

def find_best_match(user_question):
    global _qa_data
    if _qa_data is None:
        fetch_data()
    if not _qa_data:
        return "No knowledge base entries yet. The admin can add Q&A entries."
    questions  = [r[0] for r in _qa_data]
    answers    = [r[1] for r in _qa_data]
    vectorizer = TfidfVectorizer().fit_transform(questions + [user_question])
    vectors    = vectorizer.toarray()
    sim        = cosine_similarity([vectors[-1]], vectors[:-1])
    idx        = sim.argmax()
    if sim[0][idx] > 0.5:
        return answers[idx]
    return ("I'm not sure about that. Try asking about waste categories, "
            "recycling, composting, or how to use CityCare.")
























# ================================================================
#  CityCare  –  app_additions.py
#  Paste ALL of this into your existing app.py
#  Compatible with: MySQL, your database() helper, your schema
# ================================================================
#
#  ADD THESE IMPORTS at the very top of your app.py
#  (only add the ones you don't already have)
# ================================================================
#
#   import os
#   import uuid
#   from datetime import datetime
#   from functools import wraps
#   from werkzeug.security import generate_password_hash, check_password_hash
#   from werkzeug.utils import secure_filename
#   import smtplib
#   from email.mime.text import MIMEText
#   from email.mime.multipart import MIMEMultipart
#
# ================================================================
#  ADD THESE CONFIG LINES right after app = Flask(__name__)
# ================================================================
#
#   app.config['MAIL_USERNAME'] = 'your@gmail.com'       # your Gmail
#   app.config['MAIL_PASSWORD'] = 'your_app_password'    # Gmail App Password
#   app.config['UPLOAD_FOLDER'] = os.path.join('static', 'pictures')
#   os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
#
# ================================================================

ALLOWED_EXTS = {'png', 'jpg', 'jpeg', 'webp'}


# ────────────────────────────────────────────────────────────────
#  HELPER FUNCTIONS
# ────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTS


def staff_login_required(f):
    """Decorator: redirects to staff login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'staff_id' not in session:
            flash('Please log in as staff.', 'danger')
            return redirect(url_for('staff_login'))
        return f(*args, **kwargs)
    return decorated


def send_email_notification(to_email, subject, html_body):
    """Send an HTML email via Gmail SMTP. Silently skips if not configured."""
    try:
        mail_user = app.config.get('MAIL_USERNAME', '')
        mail_pass = app.config.get('MAIL_PASSWORD', '')
        if not mail_user or not mail_pass:
            return  # SMTP not configured – skip silently

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"CityCare <{mail_user}>"
        msg['To']      = to_email
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(mail_user, mail_pass)
            server.sendmail(mail_user, to_email, msg.as_string())
    except Exception as e:
        print(f"[Email] Failed to send to {to_email}: {e}")


def create_staff_notification(staff_id, title, message,
                               notif_type='system', complaint_id=None):
    """
    Insert a notification row into staff_notifications.
    If the staff member's notify_pref includes email, also send an email.
    """
    con, cur = database()
    cur.execute(
        """INSERT INTO staff_notifications
               (staff_id, type, title, message, complaint_id)
           VALUES (%s, %s, %s, %s, %s)""",
        (staff_id, notif_type, title, message, complaint_id)
    )
    con.commit()

    # Fetch staff to check notification preference
    cur.execute(
        "SELECT name, email, notify_pref FROM staff_accounts WHERE id = %s",
        (staff_id,)
    )
    staff = cur.fetchone()
    con.close()

    if staff and staff['notify_pref'] in ('email', 'both'):
        link_html = (
            f"<a href='http://yoursite.com/staff/complaint/{complaint_id}' "
            f"style='display:inline-block;background:#1a4d2e;color:#fff;"
            f"padding:10px 20px;border-radius:8px;text-decoration:none;"
            f"font-weight:600;margin-top:12px;'>View Complaint</a>"
            if complaint_id else ""
        )
        html = f"""
        <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:20px;">
          <div style="background:#0d1f13;padding:20px 24px;border-radius:12px 12px 0 0;">
            <h2 style="color:#52b788;margin:0;font-size:20px;">CityCare Notification</h2>
          </div>
          <div style="background:#f8fdf9;padding:24px;border:1px solid #d0e8d8;
                      border-radius:0 0 12px 12px;">
            <h3 style="color:#1b2d23;margin-top:0;">{title}</h3>
            <p style="color:#5a7a65;line-height:1.6;">{message}</p>
            {link_html}
          </div>
        </div>"""
        send_email_notification(staff['email'], f"CityCare: {title}", html)


def recalculate_staff_score(staff_id):
    """
    Performance score formula (0–100):
      Base  : 50
      +2    per resolved complaint   (capped at +30 total)
      +5    per Critical resolved
      +3    per High resolved
      -2    per complaint pending > 7 days
      +0–20 from citizen rating  (avg_rating / 5.0 * 20)
    """
    con, cur = database()

    # Resolved complaints for this staff member
    cur.execute(
        """SELECT severity FROM complaints
           WHERE  staff_id= %s AND status = 'Resolved'""",
        (staff_id,)
    )
    resolved = cur.fetchall()

    base  = 50
    bonus = min(len(resolved) * 2, 30)
    for r in resolved:
        sev = (r['severity'] or '').lower()
        if sev == 'critical':
            bonus += 5
        elif sev == 'high':
            bonus += 3

    # Overdue penalty: pending complaints older than 7 days
    cur.execute(
        """SELECT COUNT(*) AS cnt FROM complaints
           WHERE  staff_id= %s
             AND status = 'Pending'
             AND DATEDIFF(NOW(), created_at) > 7""",
        (staff_id,)
    )
    row     = cur.fetchone()
    penalty = (row['cnt'] if row else 0) * 2

    # Rating contribution
    cur.execute(
        "SELECT avg_rating FROM staff_accounts WHERE id = %s",
        (staff_id,)
    )
    sa           = cur.fetchone()
    rating_bonus = ((sa['avg_rating'] if sa else 0) / 5.0) * 20

    score = max(0, min(100, int(base + bonus - penalty + rating_bonus)))

    cur.execute(
        "UPDATE staff_accounts SET performance_score = %s WHERE id = %s",
        (score, staff_id)
    )
    con.commit()
    con.close()
    return score

@app.route('/auto_assign_all')
def auto_assign_all():
    if 'admin' not in session:
        return redirect(url_for('login'))
 
    con, cur = database()
    cur.execute(
        """SELECT complaint_id FROM complaints
           WHERE (assigned_staff IS NULL OR assigned_staff = '')
             AND status != 'resolved'"""
    )
    unassigned = cur.fetchall()
    con.close()
 
    count = 0
    for row in unassigned:
        result = auto_assign_complaint(row['complaint_id'])
        if result:
            count += 1
 
    if count:
        flash(f'{count} complaint(s) auto-assigned successfully.', 'success')
    else:
        flash('No unassigned complaints found, or no approved staff available.', 'warning')
 
    return redirect(url_for('adminhome'))
def auto_assign_complaint(complaint_id):
    """
    Smart auto-assign logic:
      1. Fetch the complaint's location.
      2. Find approved, active staff whose zone matches the location.
      3. Among matches, pick the one with the fewest active (non-Resolved) complaints.
      4. Fallback: least-loaded staff overall.
      5. Update complaints.assigned_staff + .
      6. Send in-app + email notification to the chosen staff member.
    """
    con, cur = database()

    cur.execute(
        "SELECT * FROM complaints WHERE complaint_id = %s",
        (complaint_id,)
    )
    complaint = cur.fetchone()

    if not complaint:
        con.close()
        return None

    location = (complaint['location'] or '').lower()

    # All active, approved staff with their current active workload
    cur.execute(
        """SELECT sa.id, sa.name, sa.zone, sa.email,
                  COUNT(c.complaint_id) AS active_count
           FROM staff_accounts sa
           LEFT JOIN complaints c
             ON c.staff_id = sa.id
             AND c.status != 'Resolved'
           WHERE sa.is_active = 1 AND sa.is_approved = 1
           GROUP BY sa.id, sa.name, sa.zone, sa.email
           ORDER BY active_count ASC"""
    )
    all_staff = cur.fetchall()

    if not all_staff:
        con.close()
        return None

    # Zone match: any word in the staff's zone appears in the complaint location
    zone_matched = []
    for s in all_staff:
        words = [w.strip() for w in s['zone'].lower().split(',') if len(w.strip()) > 2]
        if any(w in location for w in words):
            zone_matched.append(s)

    chosen = zone_matched[0] if zone_matched else all_staff[0]

    # Assign
    cur.execute(
        """UPDATE complaints
           SET assigned_staff = %s,  = %s
           WHERE complaint_id = %s""",
        (chosen['name'], chosen['id'], complaint_id)
    )
    con.commit()
    con.close()

    # Notify
    cat      = complaint.get('category', 'Issue')
    loc      = complaint.get('location', '')
    priority = complaint.get('priority_score', 0) or 0
    create_staff_notification(
        staff_id     = chosen['id'],
        title        = f"New Complaint Assigned: #{complaint_id}",
        message      = (f"A {cat} complaint in {loc} has been assigned to you. "
                        f"Priority score: {priority}. "
                        f"Please log in to review and begin work."),
        notif_type   = 'assignment',
        complaint_id = complaint_id
    )
    return chosen['id']


# ================================================================
#  STAFF AUTH ROUTES
# ================================================================

@app.route('/staff/register', methods=['GET', 'POST'])
def staff_register():
    if request.method == 'POST':
        name   = request.form.get('name', '').strip()
        emp_id = request.form.get('employee_id', '').strip()
        email  = request.form.get('email', '').strip().lower()
        phone  = request.form.get('phone', '').strip()
        dept   = request.form.get('department', '')
        desig  = request.form.get('designation', '')
        zone   = request.form.get('zone', '').strip()
        notify = request.form.get('notify_pref', 'both')
        pw     = request.form.get('password', '')
        pw2    = request.form.get('confirm_password', '')

        if pw != pw2:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('staff_register'))

        con, cur = database()
        cur.execute(
            """SELECT id FROM staff_accounts
               WHERE email = %s OR employee_id = %s""",
            (email, emp_id)
        )
        if cur.fetchone():
            con.close()
            flash('Email or Employee ID already registered.', 'danger')
            return redirect(url_for('staff_register'))

        cur.execute(
            """INSERT INTO staff_accounts
                   (name, employee_id, email, phone,
                    department, designation, zone,
                    notify_pref, password_hash)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (name, emp_id, email, phone,
             dept, desig, zone,
             notify, generate_password_hash(pw))
        )
        con.commit()
        con.close()
        flash('Registration successful! Please wait for admin approval.', 'success')
        return redirect(url_for('staff_login'))

    return render_template('staff_register.html')


@app.route('/staff/login', methods=['GET', 'POST'])
def staff_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')

        con, cur = database()
        cur.execute(
            "SELECT * FROM staff_accounts WHERE email = %s",
            (email,)
        )
        staff = cur.fetchone()
        con.close()

        if not staff or not check_password_hash(staff['password_hash'], pw):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('staff_login'))
        if not staff['is_approved']:
            flash('Your account is pending admin approval.', 'danger')
            return redirect(url_for('staff_login'))

        session['staff_id']   = staff['id']
        session['staff_name'] = staff['name']
        return redirect(url_for('staff_home'))

    return render_template('staff_login.html')


@app.route('/staff/logout')
def staff_logout():
    session.pop('staff_id', None)
    session.pop('staff_name', None)
    return redirect(url_for('staff_login'))


# ================================================================
#  STAFF DASHBOARD ROUTES
# ================================================================

@app.route('/staff/home')
@staff_login_required
def staff_home():
    staff_id = session['staff_id']
    con, cur = database()

    # Staff profile
    cur.execute(
        "SELECT * FROM staff_accounts WHERE id = %s",
        (staff_id,)
    )
    staff_data = cur.fetchone()

    # Active complaints assigned to this staff member
    cur.execute(
        """SELECT c.*, u.user_name AS user_name, u.phno AS user_phone
           FROM complaints c
           LEFT JOIN users u ON c.userid = u.userid
           WHERE c.staff_id = %s
             AND c.status != 'Resolved'
           ORDER BY c.priority_score DESC
           LIMIT 10""",
        (staff_id,)
    )
    complaints = cur.fetchall()

    # Stats
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE  staff_id = %s",
        (staff_id,)
    )
    total_assigned = cur.fetchone()['cnt']

    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE staff_id = %s AND status = 'Resolved'",
        (staff_id,)
    )
    total_resolved = cur.fetchone()['cnt']

    cur.execute(
    "SELECT COUNT(*) AS cnt FROM complaints WHERE staff_id = %s AND status = 'In Progress'",
    (staff_id,)
    )
    total_inprogress = cur.fetchone()['cnt']

    # Recent notifications
    cur.execute(
        """SELECT * FROM staff_notifications
           WHERE staff_id = %s
           ORDER BY created_at DESC
           LIMIT 5""",
        (staff_id,)
    )
    notifications = cur.fetchall()

    cur.execute(
        "SELECT COUNT(*) AS cnt FROM staff_notifications WHERE staff_id = %s AND is_read = 0",
        (staff_id,)
    )
    unread_count = cur.fetchone()['cnt']

    con.close()

    stats = {
        'assigned':   total_assigned,
        'resolved':   total_resolved,
        'inprogress': total_inprogress,
    }

    return render_template(
        'staff_home.html',
        staff_data=staff_data,
        complaints=complaints,
        stats=stats,
        notifications=notifications,
        unread_count=unread_count
    )


@app.route('/staff/complaints')
@staff_login_required
def staff_complaints():
    staff_id   = session['staff_id']
    status_filter = request.args.get('status', 'all')
    con, cur   = database()

    if status_filter == 'all':
        cur.execute(
            """SELECT c.*, u.user_name AS user_name, u.phno AS user_phone
               FROM complaints c
               LEFT JOIN users u ON c.userid = u.userid
               WHERE c.staff_id = %s
               ORDER BY c.priority_score DESC""",
            (staff_id,)
        )
    else:
        cur.execute(
            """SELECT c.*, u.user_name AS user_name, u.phno AS user_phone
               FROM complaints c
               LEFT JOIN users u ON c.userid = u.userid
               WHERE c.staff_id = %s AND c.status = %s
               ORDER BY c.priority_score DESC""",
            (staff_id, status_filter)
        )
    complaints = cur.fetchall()
    con.close()

    return render_template(
        'staff/staff_complaints_list.html',
        complaints=complaints,
        status_filter=status_filter
    )


@app.route('/staff/complaint/<int:complaint_id>', methods=['GET'])
@staff_login_required
def staff_manage_complaint(complaint_id):
    staff_id = session['staff_id']
    con, cur = database()

    cur.execute(
        """SELECT c.*, u.user_name AS user_name, u.phno AS user_phone
           FROM complaints c
           LEFT JOIN users u ON c.userid = u.userid
           WHERE c.complaint_id = %s AND c.staff_id = %s""",
        (complaint_id, staff_id)
    )
    complaint = cur.fetchone()

    if not complaint:
        con.close()
        flash('Complaint not found or not assigned to you.', 'danger')
        return redirect(url_for('staff_complaints'))

    cur.execute(
        """SELECT * FROM complaint_photos
           WHERE complaint_id = %s
           ORDER BY uploaded_at ASC""",
        (complaint_id,)
    )
    photos = cur.fetchall()

    cur.execute(
        """SELECT * FROM complaint_activity
           WHERE complaint_id = %s
           ORDER BY created_at DESC""",
        (complaint_id,)
    )
    activity = cur.fetchall()

    con.close()

    return render_template(
        'staff_complaint.html',
        complaint=complaint,
        photos=photos,
        activity=activity
    )


@app.route('/staff/complaint/<int:complaint_id>/update', methods=['POST'])
@staff_login_required
def staff_update_complaint(complaint_id):
    staff_id   = session['staff_id']
    new_status = request.form.get('status', 'Pending')
    notes      = request.form.get('notes', '').strip()

    con, cur = database()

    cur.execute(
        """SELECT * FROM complaints
           WHERE complaint_id = %s AND  = %s""",
        (complaint_id, staff_id)
    )
    complaint = cur.fetchone()

    if not complaint:
        con.close()
        flash('Not authorised.', 'danger')
        return redirect(url_for('staff_complaints'))

    old_status = complaint['status'] or 'Pending'

    # Update status (and resolved_at if resolving)
    if new_status == 'Resolved':
        cur.execute(
            """UPDATE complaints
               SET status = %s, resolved_at = %s
               WHERE complaint_id = %s""",
            (new_status, datetime.now(), complaint_id)
        )
    else:
        cur.execute(
            "UPDATE complaints SET status = %s WHERE complaint_id = %s",
            (new_status, complaint_id)
        )

    # Activity log
    cur.execute(
        """INSERT INTO complaint_activity
               (complaint_id, staff_id, action, notes)
           VALUES (%s, %s, %s, %s)""",
        (complaint_id, staff_id,
         f"Status changed: {old_status} → {new_status}",
         notes)
    )

    # Photo uploads (before & after)
    def save_photos(file_key, photo_type):
        files = request.files.getlist(file_key)
        for f in files[:5]:
            if f and f.filename and allowed_file(f.filename):
                ext      = f.filename.rsplit('.', 1)[1].lower()
                filename = f"{photo_type}_{complaint_id}_{uuid.uuid4().hex[:8]}.{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                f.save(save_path)
                cur.execute(
                    """INSERT INTO complaint_photos
                           (complaint_id, staff_id, filename, photo_type)
                       VALUES (%s, %s, %s, %s)""",
                    (complaint_id, staff_id, filename, photo_type)
                )

    save_photos('before_photos', 'before')
    save_photos('after_photos',  'after')

    con.commit()
    con.close()

    if new_status == 'Resolved':
        recalculate_staff_score(staff_id)

    flash(f'Complaint updated to "{new_status}".', 'success')
    return redirect(url_for('staff_manage_complaint', complaint_id=complaint_id))


@app.route('/staff/notifications')
@staff_login_required
def staff_notifications():
    staff_id = session['staff_id']
    con, cur = database()

    cur.execute(
        """SELECT * FROM staff_notifications
           WHERE staff_id = %s
           ORDER BY created_at DESC""",
        (staff_id,)
    )
    notifications = cur.fetchall()

    # Mark all as read
    cur.execute(
        "UPDATE staff_notifications SET is_read = 1 WHERE staff_id = %s",
        (staff_id,)
    )
    con.commit()
    con.close()

    return render_template('staff_notifications.html',
                           notifications=notifications)


@app.route('/staff/notifications/mark_read', methods=['POST'])
@staff_login_required
def staff_mark_all_read():
    con, cur = database()
    cur.execute(
        "UPDATE staff_notifications SET is_read = 1 WHERE staff_id = %s",
        (session['staff_id'],)
    )
    con.commit()
    con.close()
    return redirect(url_for('staff_notifications'))


# ================================================================
#  STAFF PUBLIC PROFILE  (accessible by anyone – citizens / voters)
# ================================================================

@app.route('/staff/profile/<int:staff_id>')
def staff_profile(staff_id):
    con, cur = database()

    cur.execute(
        "SELECT * FROM staff_accounts WHERE id = %s AND is_active = 1",
        (staff_id,)
    )
    staff = cur.fetchone()

    if not staff:
        con.close()
        return "Staff profile not found.", 404

    # Resolved complaints (most recent first)
    cur.execute(
        """SELECT c.complaint_id, c.category, c.location,
                  c.severity, c.resolved_at,
                  ca.notes
           FROM complaints c
           LEFT JOIN complaint_activity ca
             ON ca.complaint_id = c.complaint_id
             AND ca.staff_id = %s
             AND ca.action LIKE '%%Resolved%%'
           WHERE c.staff_id = %s
             AND c.status = 'Resolved'
           ORDER BY c.resolved_at DESC""",
        (staff_id, staff_id)
    )
    resolved_complaints = cur.fetchall()

    # Citizen reviews / ratings
    cur.execute(
        """SELECT sr.*, c.category, c.complaint_id AS cid
           FROM staff_ratings sr
           JOIN complaints c ON c.complaint_id = sr.complaint_id
           WHERE sr.staff_id = %s
           ORDER BY sr.created_at DESC""",
        (staff_id,)
    )
    reviews = cur.fetchall()

    # Category breakdown ✅ FIXED
    cur.execute(
        """SELECT category, COUNT(*) AS cnt
           FROM complaints
           WHERE staff_id = %s AND status = 'Resolved'
           GROUP BY category
           ORDER BY cnt DESC""",
        (staff_id,)
    )
    cat_rows = cur.fetchall()
    max_cat  = cat_rows[0]['cnt'] if cat_rows else 1

    # Avg days to resolve ✅ FIXED
    cur.execute(
        """SELECT ROUND(AVG(DATEDIFF(resolved_at, created_at)), 1) AS avg_d
           FROM complaints
           WHERE staff_id = %s
             AND status = 'Resolved'
             AND resolved_at IS NOT NULL""",
        (staff_id,)
    )
    avg_days_row = cur.fetchone()
    avg_days     = avg_days_row['avg_d'] if avg_days_row and avg_days_row['avg_d'] else 0

    # Critical / High resolved count ✅ FIXED
    cur.execute(
        """SELECT COUNT(*) AS cnt FROM complaints
           WHERE staff_id = %s
             AND status = 'Resolved'
             AND severity IN ('Critical','High')""",
        (staff_id,)
    )
    critical_resolved = cur.fetchone()['cnt']

    # Zone rank (rank by performance_score within same zone)
    cur.execute(
        """SELECT id FROM staff_accounts
           WHERE zone = %s AND is_active = 1
           ORDER BY performance_score DESC""",
        (staff['zone'],)
    )
    zone_rows  = cur.fetchall()
    zone_ids   = [r['id'] for r in zone_rows]
    zone_rank  = zone_ids.index(staff_id) + 1 if staff_id in zone_ids else 0
    zone_total = len(zone_ids)

    con.close()

    stats = {
        'resolved':          len(resolved_complaints),
        'avg_days':          avg_days,
        'critical_resolved': critical_resolved,
        'categories':        [(r['category'], r['cnt']) for r in cat_rows],
        'max_cat':           max_cat,
        'zone_rank':         zone_rank,
        'zone_total':        zone_total,
    }

    return render_template(
        'staff_profile.html',
        staff=staff,
        stats=stats,
        resolved_complaints=resolved_complaints,
        reviews=reviews
    )


# ================================================================
#  CITIZEN: RATE STAFF AFTER COMPLAINT IS RESOLVED
# ================================================================

@app.route('/rate_staff/<int:complaint_id>', methods=['POST'])
def rate_staff(complaint_id):
    if 'userid' not in session:          # matches your existing session key
        return redirect(url_for('login'))

    rating  = request.form.get('rating', 0)
    comment = request.form.get('comment', '').strip()

    try:
        rating = int(rating)
    except (TypeError, ValueError):
        rating = 0

    if not (1 <= rating <= 5):
        flash('Please select a rating between 1 and 5.', 'danger')
        return redirect(url_for('userhome'))

    con, cur = database()

    # Complaint must belong to the logged-in user and be Resolved
    cur.execute(
        """SELECT * FROM complaints
           WHERE complaint_id = %s
             AND userid = %s
             AND status = 'Resolved'""",
        (complaint_id, session['userid'])
    )
    complaint = cur.fetchone()

    if not complaint or not complaint['']:
        con.close()
        flash('Cannot rate this complaint.', 'danger')
        return redirect(url_for('userhome'))

    # Prevent duplicate rating
    cur.execute(
        "SELECT id FROM staff_ratings WHERE complaint_id = %s",
        (complaint_id,)
    )
    if cur.fetchone():
        con.close()
        flash('You have already rated this complaint.', 'warning')
        return redirect(url_for('userhome'))

    staff_id = complaint['']

    cur.execute(
        """INSERT INTO staff_ratings
               (complaint_id, staff_id, userid, rating, comment)
           VALUES (%s, %s, %s, %s, %s)""",
        (complaint_id, staff_id, session['userid'], rating, comment)
    )

    # Update avg_rating on staff_accounts
    cur.execute(
        """SELECT AVG(rating) AS avg_r, COUNT(*) AS cnt
           FROM staff_ratings
           WHERE staff_id = %s""",
        (staff_id,)
    )
    avg_row = cur.fetchone()
    cur.execute(
        """UPDATE staff_accounts
           SET avg_rating = %s, total_ratings = %s
           WHERE id = %s""",
        (round(float(avg_row['avg_r']), 2), avg_row['cnt'], staff_id)
    )
    con.commit()
    con.close()

    recalculate_staff_score(staff_id)
    flash('Thank you for your rating!', 'success')
    return redirect(url_for('userhome'))


# ================================================================
#  ADMIN: STAFF MANAGEMENT
# ================================================================

@app.route('/admin/staff')
def admin_staff_list():
    if 'admin' not in session:
        return redirect(url_for('login'))
 
    con, cur = database()
    cur.execute(
        """SELECT sa.*,
               COUNT(CASE WHEN c.status NOT IN ('resolved','Resolved') THEN 1 END)
                   AS active_complaints,
               COUNT(CASE WHEN c.status IN ('resolved','Resolved') THEN 1 END)
                   AS resolved_complaints
           FROM staff_accounts sa
           LEFT JOIN complaints c ON c.staff_id = sa.id
           GROUP BY sa.id
           ORDER BY sa.is_approved ASC, sa.performance_score DESC"""
    )
    staff_list = cur.fetchall()
 
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM staff_accounts WHERE is_approved = 0"
    )
    pending_approvals = cur.fetchone()['cnt']
 
    con.close()
    return render_template(
        'admin_staff_list.html',
        staff_list        = staff_list,
        pending_approvals = pending_approvals
    )


@app.route('/admin/staff/approve/<int:staff_id>')
def admin_approve_staff(staff_id):
    if 'admin' not in session:
        return redirect(url_for('login'))
 
    con, cur = database()
    cur.execute(
        "UPDATE staff_accounts SET is_approved = 1 WHERE id = %s",
        (staff_id,)
    )
    con.commit()
 
    # Fetch staff to notify (after commit so data is fresh)
    cur.execute(
        "SELECT id, name, email, notify_pref FROM staff_accounts WHERE id = %s",
        (staff_id,)
    )
    staff = cur.fetchone()
    con.close()
 
    if staff:
        create_staff_notification(
            staff_id   = staff_id,
            title      = "Account Approved!",
            message    = (
                "Your CityCare staff account has been approved by the admin. "
                "You can now log in and start receiving complaint assignments."
            ),
            notif_type = 'system'
        )
    flash('Staff member approved successfully.', 'success')
    return redirect(url_for('admin_staff_list'))

@app.route('/admin/staff/reject/<int:staff_id>')
def admin_reject_staff(staff_id):
    if 'admin' not in session:
        return redirect(url_for('login'))
 
    con, cur = database()
    cur.execute(
        "UPDATE staff_accounts SET is_active = 0 WHERE id = %s",
        (staff_id,)
    )
    con.commit()
    con.close()
    flash('Staff member rejected/deactivated.', 'success')
    return redirect(url_for('admin_staff_list'))
# ================================================================
#  UPDATED auto_assign ROUTE  (replaces your existing one)
# ================================================================

@app.route('/auto_assign/<int:complaint_id>')
def auto_assign(complaint_id):
    if 'admin' not in session:
        return redirect(url_for('login'))
 
    assigned_id = auto_assign_complaint(complaint_id)
    if assigned_id:
        flash(f'Complaint #{complaint_id} auto-assigned successfully.', 'success')
    else:
        flash(
            'No approved active staff found. '
            'Please approve staff members first via Staff Management.',
            'warning'
        )
    return redirect(url_for('adminhome'))
if __name__ == '__main__':
    app.run(host="localhost", port=5678, debug=True)



































# # ── EMAIL CONFIG (add to your config / .env) ──────────────────
# # MAIL_SERVER   = 'smtp.gmail.com'
# # MAIL_PORT     = 587
# # MAIL_USERNAME = 'your@gmail.com'
# # MAIL_PASSWORD = 'your_app_password'   # Gmail App Password
# # ─────────────────────────────────────────────────────────────
 
# UPLOAD_FOLDER  = os.path.join('static', 'pictures')
# ALLOWED_EXTS   = {'png', 'jpg', 'jpeg', 'webp'}
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
 
# # ── HELPERS ───────────────────────────────────────────────────
 
# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTS
 
# def staff_login_required(f):
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         if 'staff_id' not in session:
#             flash('Please log in as staff.', 'danger')
#             return redirect(url_for('staff_login'))
#         return f(*args, **kwargs)
#     return decorated
 
 
# def send_email_notification(to_email, subject, html_body):
#     """Send an HTML email. Silently fails if SMTP not configured."""
#     try:
#         mail_user = app.config.get('MAIL_USERNAME')
#         mail_pass = app.config.get('MAIL_PASSWORD')
#         if not mail_user or not mail_pass:
#             return  # SMTP not configured
 
#         msg = MIMEMultipart('alternative')
#         msg['Subject'] = subject
#         msg['From']    = f"CityCare <{mail_user}>"
#         msg['To']      = to_email
#         msg.attach(MIMEText(html_body, 'html'))
 
#         with smtplib.SMTP('smtp.gmail.com', 587) as server:
#             server.starttls()
#             server.login(mail_user, mail_pass)
#             server.sendmail(mail_user, to_email, msg.as_string())
#     except Exception as e:
#         print(f"[Email] Failed: {e}")
 
# def create_staff_notification(staff_id, title, message, notif_type='system', complaint_id=None):
#     """Insert a notification row and optionally email the staff member."""
#     con, cur = database()   
#     cur.execute(
#         "INSERT INTO staff_notifications (staff_id, type, title, message, complaint_id) VALUES (?,?,?,?,?)",
#         (staff_id, notif_type, title, message, complaint_id)
#     )
#     con.commit()
#     con.close()
 
#     # Also send email if staff prefers it
#     staff = cur.execute("SELECT * FROM staff_accounts WHERE id=?", (staff_id,)).fetchone()
#     con.close()
#     if staff and staff['notify_pref'] in ('email', 'both'):
#         html = f"""
#         <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:20px;">
#           <div style="background:#0d1f13;padding:20px 24px;border-radius:12px 12px 0 0;">
#             <h2 style="color:#52b788;margin:0;font-size:20px;">CityCare Notification</h2>
#           </div>
#           <div style="background:#f8fdf9;padding:24px;border:1px solid #d0e8d8;border-radius:0 0 12px 12px;">
#             <h3 style="color:#1b2d23;margin-top:0;">{title}</h3>
#             <p style="color:#5a7a65;line-height:1.6;">{message}</p>
#             {"<a href='http://yoursite.com/staff/complaints/" + str(complaint_id) + "' style='display:inline-block;background:#1a4d2e;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:600;'>View Complaint</a>" if complaint_id else ""}
#           </div>
#         </div>"""
#         send_email_notification(staff['email'], f"CityCare: {title}", html)
 
# def recalculate_staff_score(staff_id):
#     """
#     Performance score formula:
#       Base: 50
#       +2 per resolved complaint (max +30)
#       +5 per Critical resolved
#       +3 per High resolved
#       -2 per complaint pending > 7 days
#       Rating multiplier: avg_rating / 5.0 * 20
#     Score clamped to 0–100.
#     """
#     con, cur = database()

#     cur.execute(
#         "SELECT severity FROM complaints WHERE =%s AND status='Resolved'",
#         (staff_id,)
#     )

#     resolved = cur.fetchall()

#     con.close()
 
#     base = 50
#     bonus = min(len(resolved) * 2, 30)
#     for r in resolved:
#         sev = (r['severity'] or '').lower()
#         if sev == 'critical': bonus += 5
#         elif sev == 'high':   bonus += 3
 
#     # Pending too long penalty
#     overdue = cur.execute(
#         """SELECT COUNT(*) as cnt FROM complaints
#            WHERE =? AND status='Pending'
#            AND CAST(julianday('now') - julianday(created_at) AS INT) > 7""",
#         (staff_id,)
#     ).fetchone()
#     penalty = (overdue['cnt'] or 0) * 2
 
#     # Rating contribution
#     staff = cur.execute("SELECT avg_rating FROM staff_accounts WHERE id=?", (staff_id,)).fetchone()
#     rating_bonus = ((staff['avg_rating'] or 0) / 5.0) * 20
 
#     score = max(0, min(100, int(base + bonus - penalty + rating_bonus)))
#     cur.execute("UPDATE staff_accounts SET performance_score=? WHERE id=?", (score, staff_id))
#     con.commit()
#     con.close()
#     return score
 
# def auto_assign_complaint(complaint_id):
#     """
#     Smart auto-assign:
#     1. Find staff in the same zone as the complaint location (substring match)
#     2. Among matching staff, pick the one with FEWEST active (non-resolved) complaints
#     3. If no zone match, fall back to least-loaded active staff overall
#     """
#     con, cur = database()

#     cur.execute(
#         "SELECT * FROM complaints WHERE complaint_id=%s",
#         (complaint_id,)
#     )

#     complaint = cur.fetchone()

#     if not complaint:
#         con.close()
#         return None

#     location = (complaint['location'] or '').lower()

#     con.close()
 
#     # All approved, active staff with their active workload
#     all_staff = cur.execute("""
#         SELECT sa.id, sa.name, sa.zone, sa.email,
#                COUNT(c.id) as active_count
#         FROM staff_accounts sa
#         LEFT JOIN complaints c
#           ON c. = sa.id AND c.status != 'Resolved'
#         WHERE sa.is_active=1 AND sa.is_approved=1
#         GROUP BY sa.id
#         ORDER BY active_count ASC
#     """).fetchall()
 
#     if not all_staff:
#         con.close()
#         return None
 
#     # 1. Zone match
#     zone_matched = [s for s in all_staff if any(
#         word in location for word in s['zone'].lower().split(',')
#         if len(word.strip()) > 2
#     )]
 
#     chosen = zone_matched[0] if zone_matched else all_staff[0]
 
#     # Update complaint
#     cur.execute(
#         "UPDATE complaints SET assigned_staff=?, =? WHERE id=?",
#         (chosen['name'], chosen['id'], complaint_id)
#     )
#     con.commit()
#     con.close()
 
#     # Notify staff
#     cat = complaint['category'] if 'category' in complaint.keys() else 'Issue'
#     loc = complaint['location'] if 'location' in complaint.keys() else ''
#     create_staff_notification(
#         staff_id     = chosen['id'],
#         title        = f"New Complaint Assigned: #{complaint_id}",
#         message      = f"A {cat} complaint in {loc} has been assigned to you. Priority score: {complaint['priority_score'] or 0}. Please review and begin work.",
#         notif_type   = 'assignment',
#         complaint_id = complaint_id
#     )
#     return chosen['id']
 
 
# # ================================================================
# # STAFF AUTH ROUTES
# # ================================================================
 
# @app.route('/staff/register', methods=['GET','POST'])
# def staff_register():
#     if request.method == 'POST':
#         name     = request.form.get('name','').strip()
#         emp_id   = request.form.get('employee_id','').strip()
#         email    = request.form.get('email','').strip().lower()
#         phone    = request.form.get('phone','').strip()
#         dept     = request.form.get('department','')
#         desig    = request.form.get('designation','')
#         zone     = request.form.get('zone','').strip()
#         notify   = request.form.get('notify_pref','both')
#         pw       = request.form.get('password','')
#         pw2      = request.form.get('confirm_password','')
 
#         if pw != pw2:
#             flash('Passwords do not match.', 'danger')
#             return redirect(url_for('staff_register'))
 
#         con, cur = database()

#         cur.execute(
#             "SELECT id FROM staff_accounts WHERE email=%s OR employee_id=%s",
#             (email, emp_id)
#         )

#         existing = cur.fetchone()

#         if existing:
#             con.close()
#             flash('Email or Employee ID already registered.', 'danger')
#             return redirect(url_for('staff_register'))
 
#         cur.execute(
#             """INSERT INTO staff_accounts
#                (name, employee_id, email, phone, department, designation, zone, notify_pref, password_hash)
#                VALUES (?,?,?,?,?,?,?,?,?)""",
#             (name, emp_id, email, phone, dept, desig, zone, notify, generate_password_hash(pw))
#         )
#         con.commit()
#         con.close()
#         flash('Registration successful! Await admin approval.', 'success')
#         return redirect(url_for('staff_login'))
 
#     return render_template('staff_register.html')
 
 
# @app.route('/staff/login', methods=['GET','POST'])
# def staff_login():
#     if request.method == 'POST':
#         email = request.form.get('email','').strip().lower()
#         pw    = request.form.get('password','')
 
#         con, cur = database()

#         cur.execute(
#             "SELECT * FROM staff_accounts WHERE email=%s",
#             (email,)
#         )

#         staff = cur.fetchone()

#         con.close()
 
#         if not staff or not check_password_hash(staff['password_hash'], pw):
#             flash('Invalid email or password.', 'danger')
#             return redirect(url_for('staff_login'))
#         if not staff['is_approved']:
#             flash('Your account is pending admin approval.', 'danger')
#             return redirect(url_for('staff_login'))
 
#         session['staff_id']   = staff['id']
#         session['staff_name'] = staff['name']
#         return redirect(url_for('staff_home'))
 
#     return render_template('staff_login.html')
 
 
# @app.route('/staff/logout')
# def staff_logout():
#     session.pop('staff_id', None)
#     session.pop('staff_name', None)
#     return redirect(url_for('staff_login'))
 
 
# # ================================================================
# # STAFF DASHBOARD ROUTES
# # ================================================================
 
# @app.route('/staff/home')
# @staff_login_required
# def staff_home():
#     staff_id = session['staff_id']
#     con, cur = database()

#     cur.execute(
#         "SELECT * FROM staff_accounts WHERE id=%s",
#         (staff_id,)
#     )
#     staff_data = cur.fetchone()

#     cur.execute(
#         """SELECT c.*, u.user_name as user_name, u.phno as user_phone
#         FROM complaints c
#         LEFT JOIN users u ON c.userid = u.userid
#         WHERE c.=%s AND c.status != 'Resolved'
#         ORDER BY c.priority_score DESC LIMIT 10""",
#         (staff_id,)
#     )
#     complaints = cur.fetchall()

#     con.close()
 
#     stats = {
#         'assigned':   cur.execute("SELECT COUNT(*) FROM complaints WHERE =?", (staff_id,)).fetchone()[0],
#         'resolved':   cur.execute("SELECT COUNT(*) FROM complaints WHERE =? AND status='Resolved'", (staff_id,)).fetchone()[0],
#         'inprogress': cur.execute("SELECT COUNT(*) FROM complaints WHERE =? AND status='In Progress'", (staff_id,)).fetchone()[0],
#     }
 
#     notifications = cur.execute(
#         "SELECT * FROM staff_notifications WHERE staff_id=? ORDER BY created_at DESC LIMIT 5",
#         (staff_id,)
#     ).fetchall()
#     unread_count = cur.execute(
#         "SELECT COUNT(*) FROM staff_notifications WHERE staff_id=? AND is_read=0",
#         (staff_id,)
#     ).fetchone()[0]
 
#     con.close()
#     return render_template('staff_home.html',
#         staff_data=staff_data, complaints=complaints,
#         stats=stats, notifications=notifications, unread_count=unread_count
#     )
 
 
# @app.route('/staff/complaints')
# @staff_login_required
# def staff_complaints():
#     staff_id = session['staff_id']
#     con, cur = database()

#     cur.execute(
#         """SELECT c.*, u.user_name as user_name, u.phno as user_phone
#            FROM complaints c
#            LEFT JOIN users u ON c.userid = u.userid
#            WHERE c.=%s
#            ORDER BY c.priority_score DESC""",
#         (staff_id,)
#     )
#     complaints = cur.fetchall()

#     con.close()
#     return render_template('staff_complaints_list.html', complaints=complaints)
 
 
# @app.route('/staff/complaint/<int:complaint_id>', methods=['GET'])
# @staff_login_required
# def staff_manage_complaint(complaint_id):
#     staff_id = session['staff_id']
#     con, cur = database()

#     cur.execute(
#         """SELECT c.*, u.user_name as user_name, u.phno as user_phone
#            FROM complaints c
#            LEFT JOIN users u ON c.userid = u.userid
#            WHERE c.complaint_id=%s AND c.=%s""",
#         (complaint_id, staff_id)
#     )
#     complaint = cur.fetchone()
 
#     if not complaint:
#         flash('Complaint not found or not assigned to you.', 'danger')
#         con.close()
#         return redirect(url_for('staff_complaints'))
 
#     photos   = cur.execute("SELECT * FROM complaint_photos WHERE complaint_id=? ORDER BY uploaded_at", (complaint_id,)).fetchall()
#     activity = cur.execute("SELECT * FROM complaint_activity WHERE complaint_id=? ORDER BY created_at DESC", (complaint_id,)).fetchall()
#     con.close()
 
#     return render_template('staff_complaint.html',
#         complaint=complaint, photos=photos, activity=activity
#     )
 
 
# @app.route('/staff/complaint/<int:complaint_id>/update', methods=['POST'])
# @staff_login_required
# def staff_update_complaint(complaint_id):
#     staff_id = session['staff_id']
#     new_status = request.form.get('status')
#     notes      = request.form.get('notes', '').strip()

#     con, cur = database()

#     cur.execute(
#         "SELECT * FROM complaints WHERE complaint_id=%s AND =%s",
#         (complaint_id, staff_id)
#     )
#     complaint = cur.fetchone()

#     if not complaint:
#         con.close()
#         flash('Not authorized.', 'danger')
#         return redirect(url_for('staff_complaints'))

#     old_status = complaint['status'] or 'Pending'
 
#     # Update complaint status
#     resolved_at = datetime.now() if new_status == 'Resolved' else None
#     if resolved_at:
#         cur.execute(
#             "UPDATE complaints SET status=?, resolved_at=? WHERE id=?",
#             (new_status, resolved_at, complaint_id)
#         )
#     else:
#         cur.execute("UPDATE complaints SET status=? WHERE id=?", (new_status, complaint_id))
 
#     # Log activity
#     action = f"Status changed: {old_status} → {new_status}"
#     cur.execute(
#         "INSERT INTO complaint_activity (complaint_id, staff_id, action, notes) VALUES (?,?,?,?)",
#         (complaint_id, staff_id, action, notes)
#     )
 
#     # Handle photo uploads
#     def save_photos(file_key, photo_type):
#         files = request.files.getlist(file_key)
#         for f in files[:5]:
#             if f and f.filename and allowed_file(f.filename):
#                 ext      = f.filename.rsplit('.', 1)[1].lower()
#                 filename = f"{photo_type}_{complaint_id}_{uuid.uuid4().hex[:8]}.{ext}"
#                 f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
#                 cur.execute(
#                     "INSERT INTO complaint_photos (complaint_id, staff_id, filename, photo_type) VALUES (?,?,?,?)",
#                     (complaint_id, staff_id, filename, photo_type)
#                 )
 
#     save_photos('before_photos', 'before')
#     save_photos('after_photos',  'after')
#     con.commit()
 
#     # Recalculate score if resolved
#     if new_status == 'Resolved':
#         recalculate_staff_score(staff_id)
 
#     con.close()
#     flash(f'Complaint updated to "{new_status}".', 'success')
#     return redirect(url_for('staff_manage_complaint', complaint_id=complaint_id))
 
 
# @app.route('/staff/notifications')
# @staff_login_required
# def staff_notifications():
#     staff_id = session['staff_id']
#     con, cur = database()

#     cur.execute(
#         "SELECT * FROM staff_notifications WHERE staff_id=%s ORDER BY created_at DESC",
#         (staff_id,)
#     )
#     notifications = cur.fetchall()

#     # Mark all as read
#     cur.execute(
#         "UPDATE staff_notifications SET is_read=1 WHERE staff_id=%s",
#         (staff_id,)
#     )
#     con.commit()

#     con.close()
#     return render_template('staff_notifications.html', notifications=notifications)
 
 
# @app.route('/staff/notifications/mark_read', methods=['POST'])
# @staff_login_required
# def staff_mark_all_read():
#     con, cur = database()

#     cur.execute(
#         "UPDATE staff_notifications SET is_read=1 WHERE staff_id=%s",
#         (session['staff_id'],)
#     )
#     con.commit()

#     con.close()
#     return redirect(url_for('staff_notifications'))
 
 
# @app.route('/staff/profile/<int:staff_id>')
# def staff_profile(staff_id):
#     con, cur = database()

#     cur.execute(
#         "SELECT * FROM staff_accounts WHERE id=%s AND is_active=1",
#         (staff_id,)
#     )
#     staff = cur.fetchone()

#     if not staff:
#         con.close()
#         return "Staff not found", 404
 
#     resolved_complaints = cur.execute(
#         """SELECT c.*, ca.notes as notes, c.resolved_at
#            FROM complaints c
#            LEFT JOIN complaint_activity ca ON ca.complaint_id = c.id AND ca.staff_id=?
#            WHERE c.=? AND c.status='Resolved'
#            ORDER BY c.resolved_at DESC""",
#         (staff_id, staff_id)
#     ).fetchall()
 
#     reviews = cur.execute(
#         "SELECT * FROM staff_ratings WHERE staff_id=? ORDER BY created_at DESC",
#         (staff_id,)
#     ).fetchall()
 
#     # Category breakdown
#     cat_raw = cur.execute(
#         """SELECT category, COUNT(*) as cnt FROM complaints
#            WHERE =? AND status='Resolved'
#            GROUP BY category ORDER BY cnt DESC""",
#         (staff_id,)
#     ).fetchall()
#     max_cat = cat_raw[0]['cnt'] if cat_raw else 1
 
#     # Avg resolution days
#     avg_days_row = cur.execute(
#         """SELECT ROUND(AVG(julianday(resolved_at) - julianday(created_at)),1) as avg_d
#            FROM complaints
#            WHERE =? AND status='Resolved' AND resolved_at IS NOT NULL""",
#         (staff_id,)
#     ).fetchone()
#     avg_days = avg_days_row['avg_d'] if avg_days_row['avg_d'] else 0
 
#     critical_resolved = cur.execute(
#         "SELECT COUNT(*) as cnt FROM complaints WHERE =? AND status='Resolved' AND severity IN ('Critical','High')",
#         (staff_id,)
#     ).fetchone()['cnt']
 
#     # Zone rank
#     zone_staff = cur.execute(
#         """SELECT id, performance_score FROM staff_accounts
#            WHERE zone=? AND is_active=1 ORDER BY performance_score DESC""",
#         (staff['zone'],)
#     ).fetchall()
#     zone_ids = [s['id'] for s in zone_staff]
#     zone_rank  = zone_ids.index(staff_id) + 1 if staff_id in zone_ids else 0
#     zone_total = len(zone_ids)
 
#     con.close()
 
#     stats = {
#         'resolved':         len(resolved_complaints),
#         'avg_days':         avg_days,
#         'critical_resolved': critical_resolved,
#         'categories':       [(r['category'], r['cnt']) for r in cat_raw],
#         'max_cat':          max_cat,
#         'zone_rank':        zone_rank,
#         'zone_total':       zone_total,
#     }
 
#     return render_template('staff_profile.html',
#         staff=staff, stats=stats,
#         resolved_complaints=resolved_complaints, reviews=reviews
#     )
 
 
# # ================================================================
# # CITIZEN: RATE STAFF AFTER RESOLUTION
# # ================================================================
 
# @app.route('/rate_staff/<int:complaint_id>', methods=['POST'])
# def rate_staff(complaint_id):
#     """Called from the user's complaint detail view after it's marked Resolved."""
#     if 'user_id' not in session:
#         return redirect(url_for('login'))

#     rating  = int(request.form.get('rating', 0))
#     comment = request.form.get('comment', '').strip()
#     if not (1 <= rating <= 5):
#         flash('Invalid rating.', 'danger')
#         return redirect(url_for('userhome'))

#     con, cur = database()

#     cur.execute(
#         "SELECT * FROM complaints WHERE complaint_id=%s AND userid=%s",
#         (complaint_id, session['user_id'])
#     )
#     complaint = cur.fetchone()

#     if not complaint or not complaint['']:
#         con.close()
#         flash('Cannot rate this complaint.', 'danger')
#         return redirect(url_for('userhome'))
 
#     # Prevent double rating
#     existing = cur.execute("SELECT id FROM staff_ratings WHERE complaint_id=?", (complaint_id,)).fetchone()
#     if existing:
#         con.close()
#         flash('You have already rated this complaint.', 'warning')
#         return redirect(url_for('userhome'))
 
#     staff_id = complaint['']
#     cur.execute(
#         "INSERT INTO staff_ratings (complaint_id, staff_id, user_id, rating, comment) VALUES (?,?,?,?,?)",
#         (complaint_id, staff_id, session['user_id'], rating, comment)
#     )
 
#     # Recalculate avg rating
#     avg = cur.execute(
#         "SELECT AVG(rating) as avg_r, COUNT(*) as cnt FROM staff_ratings WHERE staff_id=?",
#         (staff_id,)
#     ).fetchone()
#     cur.execute(
#         "UPDATE staff_accounts SET avg_rating=?, total_ratings=? WHERE id=?",
#         (round(avg['avg_r'], 2), avg['cnt'], staff_id)
#     )
#     con.commit()
#     con.close()
 
#     recalculate_staff_score(staff_id)
#     flash('Thank you for your rating!', 'success')
#     return redirect(url_for('userhome'))
 
 
# # ================================================================
# # ADMIN: APPROVE STAFF + AUTO-ASSIGN ROUTE UPDATES
# # ================================================================
 
# @app.route('/admin/staff')
# def admin_staff_list():
#     """Admin page to view and approve staff."""
#     if 'admin' not in session:
#         return redirect(url_for('login'))

#     con, cur = database()

#     cur.execute(
#         """SELECT sa.*,
#                COUNT(CASE WHEN c.status != 'Resolved' THEN 1 END) as active_complaints,
#                COUNT(CASE WHEN c.status = 'Resolved' THEN 1 END) as resolved_complaints
#            FROM staff_accounts sa
#            LEFT JOIN complaints c ON c. = sa.id
#            GROUP BY sa.id
#            ORDER BY sa.performance_score DESC"""
#     )
#     staff_list = cur.fetchall()

#     con.close()
#     return render_template('admin/admin_staff_list.html', staff_list=staff_list)
 
 
# @app.route('/admin/staff/approve/<int:staff_id>')
# def admin_approve_staff(staff_id):
#     if 'admin' not in session:
#         return redirect(url_for('login'))

#     con, cur = database()

#     cur.execute(
#         "UPDATE staff_accounts SET is_approved=1 WHERE id=%s",
#         (staff_id,)
#     )
#     con.commit()

#     cur.execute(
#         "SELECT * FROM staff_accounts WHERE id=%s",
#         (staff_id,)
#     )
#     staff = cur.fetchone()

#     con.close()

#     if staff:
#         create_staff_notification(
#             staff_id   = staff_id,
#             title      = "Account Approved!",
#             message    = "Your CityCare staff account has been approved. You can now log in and start receiving complaints.",
#             notif_type = 'system'
#         )

#     flash('Staff member approved.', 'success')
#     return redirect(url_for('admin_staff_list'))
 
 
# @app.route('/auto_assign/<int:complaint_id>')
# def auto_assign(complaint_id):
#     """Existing route — now calls smart auto_assign_complaint()."""
#     if 'admin' not in session:
#         return redirect(url_for('login'))
#     assigned_id = auto_assign_complaint(complaint_id)
#     if assigned_id:
#         flash(f'Complaint #{complaint_id} auto-assigned successfully.', 'success')
#     else:
#         flash('No available staff found for auto-assign.', 'warning')
#     return redirect(url_for('adminhome'))
 
 
# # ================================================================
# # STAFF COMPLAINTS LIST PAGE (simple template data)
# # ================================================================
 
# # Add this template as templates/staff/staff_complaints_list.html
# # (A simple version is included below as a string for reference,
# #  but save it as a proper file.)
 
# STAFF_COMPLAINTS_LIST_HTML = """
# {% extends "staff/staff_base.html" %}
# {% block content %}
# <!-- Same card grid as staff_home but showing all complaints with filter tabs -->
# {% endblock %}
# """
# # NOTE: For the complaints list page, reuse the same card layout
# # from staff_home.html but show all assigned complaints with
# # status filter tabs (All / Pending / In Progress / Resolved).
# # ══════════════════════════════════════════════════════════════════
# if __name__ == '__main__':
#     app.run(host="localhost", debug=True, port=5678)
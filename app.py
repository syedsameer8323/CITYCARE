# ─────────────────────────────────────────────────────────────────
#  CityCare  –  app.py  (FINAL: AI chatbot + email + feedback)
# ─────────────────────────────────────────────────────────────────

from flask import Flask, session, render_template, request, jsonify, redirect
import mysql.connector, os
from werkzeug.utils import secure_filename
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests as http_requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import nltk
nltk.download('punkt', quiet=True)

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
        user="root", password="root",
        port="3306", host="localhost",
        database="waste_management_system"
    )
    return con, con.cursor()

# ══════════════════════════════════════════════════════════════════
#  PRIORITY ENGINE
# ══════════════════════════════════════════════════════════════════

SEVERITY_MAP = {'Critical': 10, 'High': 7, 'Medium': 4, 'Low': 1}

def compute_priority(severity, created_at, area, con, cur):
    sev_score    = SEVERITY_MAP.get(severity, 4)
    waiting_days = min((datetime.now() - created_at).days, 30) if created_at else 0
    cur.execute(
        "SELECT COUNT(*) FROM complaints WHERE location=%s AND status!='resolved'", (area,)
    )
    area_load = min(cur.fetchone()[0], 10)
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
        "SELECT staff_id, staff_name FROM staff "
        "WHERE available=1 ORDER BY current_load ASC LIMIT 1"
    )
    r = cur.fetchone()
    return (r[0], r[1]) if r else (None, "Unassigned")

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

# @app.route("/admin")
# def admin():
#     return render_template("admin.html")
@app.route("/admin")
def admin():
    return redirect('/adminhome')
@app.route("/admin_loginchk", methods=["GET", "POST"])
def admin_loginchk():
    if request.form['uid'] == 'admin' and request.form['pwd'] == 'admin':
        return redirect('/adminhome')
    return render_template("admin.html", msg2="fail")

@app.route("/adminhome")
def adminhome():
    recalculate_all_priorities()
    con, cur = database()

    cur.execute("SELECT COUNT(*) FROM complaints")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM complaints WHERE status='pending'")
    pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM complaints WHERE status='resolved'")
    resolved = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM complaints WHERE status IN ('verified','Verfied')")
    verified = cur.fetchone()[0]
    cur.execute(
        "SELECT AVG(DATEDIFF(resolved_at, created_at)) "
        "FROM complaints WHERE resolved_at IS NOT NULL"
    )
    r = cur.fetchone()[0]
    avg_resolution = round(r, 1) if r else "N/A"
    cur.execute(
        "SELECT COUNT(*) FROM complaints "
        "WHERE severity IN ('Critical','High') AND status != 'resolved'"
    )
    critical_count = cur.fetchone()[0]
    cur.execute(
        "SELECT complaint_id, user_name, category, location, status, "
        "severity, priority_score, assigned_staff, created_at "
        "FROM complaints ORDER BY priority_score DESC"
    )
    complaints = cur.fetchall()
    cur.execute(
        "SELECT location, COUNT(*) FROM complaints WHERE status!='resolved' "
        "GROUP BY location ORDER BY COUNT(*) DESC LIMIT 5"
    )
    hotspots = cur.fetchall()
    cur.execute("SELECT category, COUNT(*) FROM complaints GROUP BY category")
    cat_data = cur.fetchall()
    cur.execute(
        "SELECT staff_id, staff_name, designation, available, current_load FROM staff"
    )
    staff_list = cur.fetchall()
    cur.execute("SELECT AVG(rating) FROM feedback WHERE rating IS NOT NULL")
    ar = cur.fetchone()[0]
    avg_rating = round(ar, 1) if ar else "N/A"
    con.close()

    return render_template(
        "admin_home.html",
        total=total, pending=pending, resolved=resolved, verified=verified,
        avg_resolution=avg_resolution, critical_count=critical_count,
        complaints=complaints, hotspots=hotspots, cat_data=cat_data,
        staff_list=staff_list, avg_rating=avg_rating
    )

# ── Knowledge Base ─────────────────────────────────────────────────
@app.route("/add_questions")
def add_questions():
    con, cur = database()
    cur.execute("SELECT qid, question, answer FROM questions ORDER BY qid DESC")
    all_qa = cur.fetchall()
    con.close()
    return render_template("add_questions.html", all_qa=all_qa)

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
    cur.execute("SELECT staff_id, staff_name FROM staff WHERE available=1")
    staff_list = cur.fetchall()
    con.close()
    return render_template("view_complaints2.html", rawdata=values, staff_list=staff_list)

@app.route("/update_status/<cid>")
def update_status(cid):
    con, cur = database()
    cur.execute(
        "SELECT staff_id, staff_name FROM staff WHERE available=1 ORDER BY current_load ASC"
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
                "UPDATE staff SET current_load=GREATEST(current_load-1,0) "
                "WHERE staff_id=%s", (sid,)
            )
        else:
            cur.execute(
                "UPDATE staff SET current_load=current_load+1 WHERE staff_id=%s", (sid,)
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
    cur.execute("SELECT staff_id, staff_name FROM staff WHERE available=1")
    staff_list = cur.fetchall()
    con.close()

    return render_template(
        "view_complaints2.html", msg="Status updated!",
        rawdata=values, staff_list=staff_list
    )

@app.route("/auto_assign/<int:cid>")
def auto_assign(cid):
    con, cur = database()
    staff_id, staff_name = suggest_staff(con, cur)
    if staff_id:
        cur.execute(
            "UPDATE complaints SET assigned_staff=%s, staff_id=%s WHERE complaint_id=%s",
            (staff_name, staff_id, cid)
        )
        cur.execute(
            "UPDATE staff SET current_load=current_load+1 WHERE staff_id=%s", (staff_id,)
        )
        con.commit()
    con.close()
    return redirect('/view_complaints')

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
    name = request.form['name']
    uid  = request.form['usid']
    pwd  = request.form['pwd']
    mail = request.form['email']
    mno  = request.form['phno']
    con, cur = database()
    cur.execute("SELECT COUNT(*) FROM users WHERE userid=%s", (uid,))
    if cur.fetchone()[0] > 0:
        con.close()
        return render_template("user_reg.html", msg="already exists!")
    cur.execute(
        "INSERT INTO users VALUES (%s,%s,%s,%s,%s)", (name, uid, mail, pwd, mno)
    )
    con.commit()
    con.close()
    return render_template("user.html", msg="Registered Successfully! Login here.")

@app.route("/user_loginchk", methods=["GET", "POST"])
def user_loginchk():
    uid = request.form.get("userid")
    pwd = request.form.get("pwd")
    con, cur = database()
    cur.execute(
        "SELECT COUNT(*) FROM users WHERE userid=%s AND passwrd=%s", (uid, pwd)
    )
    if cur.fetchone()[0] > 0:
        session['uid'] = uid
        con.close()
        return redirect("/userhome")
    con.close()
    return render_template("user.html", msg2="Invalid Credentials")

@app.route("/userhome")
def userhome():
    uid = session.get('uid')
    if not uid:
        return redirect('/user')
    con, cur = database()
    cur.execute("SELECT COUNT(*) FROM complaints WHERE userid=%s", (uid,))
    total = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM complaints WHERE userid=%s AND status='pending'", (uid,)
    )
    pending = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM complaints WHERE userid=%s AND status='resolved'", (uid,)
    )
    resolved = cur.fetchone()[0]
    cur.execute(
        "SELECT AVG(DATEDIFF(resolved_at, created_at)) "
        "FROM complaints WHERE userid=%s AND resolved_at IS NOT NULL", (uid,)
    )
    ar = cur.fetchone()[0]
    avg_days = round(ar, 1) if ar else "N/A"
    cur.execute(
        "SELECT category, location, status, priority_score, created_at "
        "FROM complaints WHERE userid=%s ORDER BY created_at DESC LIMIT 1", (uid,)
    )
    latest = cur.fetchone()
    con.close()
    return render_template(
        "user_home.html",
        total=total, pending=pending, resolved=resolved,
        avg_days=avg_days, latest=latest
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
    name, mno = user_row[0], user_row[4]
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
            "UPDATE staff SET current_load=current_load+1 WHERE staff_id=%s", (staff_id,)
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
            "UPDATE staff SET current_load=GREATEST(current_load-1,0) "
            "WHERE staff_id=%s", (row[0],)
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

# ══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    app.run(host="localhost", debug=True, port=5678)
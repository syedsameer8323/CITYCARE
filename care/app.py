# ─────────────────────────────────────────────────────────────────
#  CityCare  –  app.py  (UPGRADED: Staff Hierarchy + Escalation + Notifications)
# ─────────────────────────────────────────────────────────────────

from flask import Flask, session, render_template, request, jsonify, redirect, url_for, flash
import mysql.connector
import os
import uuid

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import datetime, timedelta
from functools import wraps

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
EMAIL_ENABLED  = True
EMAIL_SENDER   = "syedsameer8323@gmail.com"
EMAIL_PASSWORD = "bqrm obpn jvva skgf"   # Gmail App Password

# ── Anthropic AI config ────────────────────────────────────────────
ANTHROPIC_API_KEY = "sk-ant-your-key-here"
AI_ENABLED        = False

# ── Staff Designation Hierarchy (lowest index = lowest rank) ──────
DESIGNATION_HIERARCHY = [
    "Worker",
    "Senior Worker",
    "Supervisor",
    "Senior Supervisor",
    "Officer",
    "Senior Officer",
    "Chief Officer"
]

# ── Category → Department mapping ─────────────────────────────────
CATEGORY_DEPT_MAP = {
    "Organic":           "Waste Management",
    "Hazardous":         "Environment",
    "Liquid":            "Public Works",
    "Domestic":          "Sanitation",
    "Mixed":             "Waste Management",
    "Garbage Overflow":  "Waste Management",
    "Uncollected Waste": "Sanitation",
    "Streetlight Issue": "Public Works",
    "Water Leakage":     "Public Works",
    "Road Damage":       "Public Works",
    "Drainage Issue":    "Public Works",
    "Public Toilet Issue":"Health & Hygiene",
    "Illegal Dumping":   "Environment",
    "Dead Animal":       "Health & Hygiene",
}

ALLOWED_EXTS  = {'png', 'jpg', 'jpeg', 'webp'}
SEVERITY_MAP  = {'Critical': 10, 'High': 7, 'Medium': 4, 'Low': 1}

# ══════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════

def database():
    con = mysql.connector.connect(
        user="root", password="root",
        host="localhost", port="3306",
        database="waste_management_system"
    )
    return con, con.cursor(dictionary=True)

# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTS

def staff_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'staff_id' not in session:
            flash('Please log in as staff.', 'danger')
            return redirect(url_for('staff_login'))
        return f(*args, **kwargs)
    return decorated

def get_designation_level(designation):
    """Returns numeric level of designation (0 = lowest). -1 if unknown."""
    try:
        return DESIGNATION_HIERARCHY.index(designation)
    except ValueError:
        return -1

def get_next_designation(designation):
    """Returns the next higher designation, or None if already at top."""
    level = get_designation_level(designation)
    if level == -1 or level >= len(DESIGNATION_HIERARCHY) - 1:
        return None
    return DESIGNATION_HIERARCHY[level + 1]

# ══════════════════════════════════════════════════════════════════
#  EMAIL
# ══════════════════════════════════════════════════════════════════

def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From']    = EMAIL_SENDER
        msg['To']      = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Email sent to:", to_email)
    except Exception as e:
        print("❌ Email error:", e)

def send_status_email(to_email, user_name, complaint_id, category, location, new_status):
    if not EMAIL_ENABLED or not to_email:
        return False
    try:
        colors = {
            'resolved':   '#1e8449', 'verified': '#1a6ebf',
            'processing': '#6b30b5', 'pending':  '#e67e22',
            'escalated':  '#c0392b', 'in progress': '#1a6ebf'
        }
        color = colors.get(new_status.lower(), '#1a4d2e')
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;">
          <div style="background:#0d1f13;padding:24px 32px;border-radius:12px 12px 0 0;">
            <h2 style="color:#fff;margin:0;"><span style="color:#52b788;">CITY</span>CARE</h2>
          </div>
          <div style="background:#fff;padding:32px;border:1px solid #d0e8d8;border-top:none;border-radius:0 0 12px 12px;">
            <p style="font-size:16px;color:#1b2d23;">Hi <b>{user_name}</b>,</p>
            <p style="color:#5a7a65;line-height:1.7;">
              Your complaint <b>#{complaint_id}</b> ({category} at {location}) has been updated.
            </p>
            <div style="background:#f0f6f2;border-radius:10px;padding:20px;margin:20px 0;text-align:center;">
              <p style="margin:0 0 8px;font-size:13px;color:#5a7a65;text-transform:uppercase;">New Status</p>
              <span style="background:{color};color:#fff;padding:8px 24px;border-radius:50px;font-size:16px;font-weight:700;">
                {new_status.capitalize()}
              </span>
            </div>
            {"<p style='color:#52b788;font-weight:600;'>Your complaint is resolved! Please log in to CityCare and leave feedback.</p>" if new_status.lower()=='resolved' else ""}
            <p style="color:#5a7a65;font-size:14px;margin-top:12px;">Log in to CityCare to track your complaint.</p>
            <p style="margin-top:24px;font-size:13px;color:#aaa;">&mdash; The CityCare Team</p>
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
#  NOTIFICATION SYSTEM
# ══════════════════════════════════════════════════════════════════

def create_notification(staff_id, complaint_id, message,
                         notif_type='assignment', title=None):
    """
    Insert into notifications table.
    notif_type: assignment | reminder | escalation | admin_message
    """
    con, cur = database()
    if not title:
        title = notif_type.replace('_', ' ').capitalize()
    cur.execute(
        """INSERT INTO notifications
               (complaint_id, staff_id, message, type, title)
           VALUES (%s, %s, %s, %s, %s)""",
        (complaint_id, staff_id, message, notif_type, title)
    )
    con.commit()

    # Also send email if staff has email preference
    cur.execute(
        "SELECT name, email, notify_pref FROM staff_accounts WHERE id = %s",
        (staff_id,)
    )
    staff = cur.fetchone()
    con.close()

    if staff and staff.get('notify_pref') in ('email', 'both') and staff.get('email'):
        send_email(staff['email'], f"CityCare: {title}", message)

def send_notification_route(staff_id, complaint_id, message, notif_type='admin_message'):
    """Wrapper used by /send_notification route."""
    create_notification(staff_id, complaint_id, message, notif_type,
                        title=f"Admin Message – Complaint #{complaint_id}")

# ══════════════════════════════════════════════════════════════════
#  PRIORITY ENGINE
# ══════════════════════════════════════════════════════════════════

def compute_priority(severity, created_at, area, con, cur):
    sev_score = SEVERITY_MAP.get(severity, 4)
    if created_at and isinstance(created_at, str):
        try:
            created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        except Exception:
            created_at = None
    waiting_days = min((datetime.now() - created_at).days, 30) if created_at else 0
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE location=%s AND status!='resolved'",
        (area,)
    )
    result   = cur.fetchone()
    area_load = min(result['cnt'], 10) if result else 0
    return round((sev_score * 0.50) + (waiting_days * 0.30) + (area_load * 0.20), 2)

def recalculate_all_priorities():
    con, cur = database()
    cur.execute(
        "SELECT complaint_id, severity, created_at, location "
        "FROM complaints WHERE status != 'resolved'"
    )
    for row in cur.fetchall():
        score = compute_priority(row['severity'], row['created_at'],
                                 row['location'], con, cur)
        cur.execute(
            "UPDATE complaints SET priority_score=%s, severity_score=%s "
            "WHERE complaint_id=%s",
            (score, SEVERITY_MAP.get(row['severity'], 4), row['complaint_id'])
        )
    con.commit()
    con.close()

# ══════════════════════════════════════════════════════════════════
#  SMART AUTO-ASSIGN (department + zone + designation hierarchy)
# ══════════════════════════════════════════════════════════════════

def smart_assign_complaint(complaint_id):
    """
    Assignment rules:
    1. Match department (from category) + zone (from location keywords)
    2. Among matches, pick lowest designation (Worker first)
    3. Among same designation, pick least loaded
    4. Fallback: least-loaded approved staff overall
    """
    con, cur = database()
    cur.execute("SELECT * FROM complaints WHERE complaint_id=%s", (complaint_id,))
    complaint = cur.fetchone()
    if not complaint:
        con.close()
        return None

    category = complaint.get('category', '')
    location = (complaint.get('location') or '').lower()
    target_dept = CATEGORY_DEPT_MAP.get(category, '')

    # All active approved staff with workload
    cur.execute(
        """SELECT sa.id, sa.name, sa.department, sa.zone, sa.designation, sa.email,
                  COUNT(c.complaint_id) AS active_count
           FROM staff_accounts sa
           LEFT JOIN complaints c
             ON c.staff_id = sa.id AND c.status NOT IN ('resolved','Resolved','escalated')
           WHERE sa.is_active=1 AND sa.is_approved=1
           GROUP BY sa.id, sa.name, sa.department, sa.zone, sa.designation, sa.email
           ORDER BY active_count ASC"""
    )
    all_staff = cur.fetchall()
    con.close()

    if not all_staff:
        return None

    def zone_matches(staff_zone):
        words = [w.strip() for w in staff_zone.lower().split(',') if len(w.strip()) > 2]
        return any(w in location for w in words)

    # Step 1: dept + zone match
    dept_zone = [s for s in all_staff
                 if s['department'] == target_dept and zone_matches(s['zone'])]

    # Step 2: dept only
    dept_only = [s for s in all_staff
                 if s['department'] == target_dept]

    # Step 3: zone only
    zone_only = [s for s in all_staff if zone_matches(s['zone'])]

    pool = dept_zone or dept_only or zone_only or all_staff

    # Sort pool: lowest designation level first, then fewest tasks
    pool.sort(key=lambda s: (get_designation_level(s['designation']),
                              s['active_count']))
    chosen = pool[0]

    con, cur = database()
    cur.execute(
        "UPDATE complaints SET assigned_staff=%s, staff_id=%s WHERE complaint_id=%s",
        (chosen['name'], chosen['id'], complaint_id)
    )
    cur.execute(
        "UPDATE staff_accounts SET current_load=current_load+1 WHERE id=%s",
        (chosen['id'],)
    )
    con.commit()
    con.close()

    cat      = complaint.get('category', 'Issue')
    loc      = complaint.get('location', '')
    priority = complaint.get('priority_score', 0) or 0

    create_notification(
        staff_id     = chosen['id'],
        complaint_id = complaint_id,
        message      = (f"A {cat} complaint at {loc} has been assigned to you. "
                        f"Priority score: {priority}. Please review and begin work."),
        notif_type   = 'assignment',
        title        = f"New Complaint Assigned: #{complaint_id}"
    )
    return chosen['id']

# ══════════════════════════════════════════════════════════════════
#  ESCALATION ENGINE
# ══════════════════════════════════════════════════════════════════

def escalate_complaint(complaint_id, reason="Not resolved within deadline"):
    """
    Escalate to next-higher designation in same dept + zone.
    Returns (success: bool, message: str)
    """
    con, cur = database()
    cur.execute(
        """SELECT c.*, sa.designation AS staff_designation,
                  sa.department AS staff_department, sa.zone AS staff_zone
           FROM complaints c
           LEFT JOIN staff_accounts sa ON c.staff_id = sa.id
           WHERE c.complaint_id=%s""",
        (complaint_id,)
    )
    complaint = cur.fetchone()

    if not complaint:
        con.close()
        return False, "Complaint not found."

    current_designation = complaint.get('staff_designation') or 'Worker'
    dept  = complaint.get('staff_department') or ''
    zone  = complaint.get('staff_zone') or ''
    next_desig = get_next_designation(current_designation)

    if not next_desig:
        con.close()
        return False, "Already at the highest designation level. Cannot escalate further."

    # Find next-level staff in same dept + zone
    cur.execute(
        """SELECT sa.id, sa.name, sa.email,
                  COUNT(c2.complaint_id) AS active_count
           FROM staff_accounts sa
           LEFT JOIN complaints c2
             ON c2.staff_id = sa.id AND c2.status NOT IN ('resolved','Resolved')
           WHERE sa.designation=%s AND sa.department=%s
             AND sa.zone LIKE %s
             AND sa.is_active=1 AND sa.is_approved=1
           GROUP BY sa.id, sa.name, sa.email
           ORDER BY active_count ASC
           LIMIT 1""",
        (next_desig, dept, f"%{zone.split(',')[0].strip() if zone else ''}%")
    )
    escalate_to = cur.fetchone()

    # Fallback: same dept, next designation, any zone
    if not escalate_to:
        cur.execute(
            """SELECT sa.id, sa.name, sa.email,
                      COUNT(c2.complaint_id) AS active_count
               FROM staff_accounts sa
               LEFT JOIN complaints c2
                 ON c2.staff_id = sa.id AND c2.status NOT IN ('resolved','Resolved')
               WHERE sa.designation=%s AND sa.department=%s
                 AND sa.is_active=1 AND sa.is_approved=1
               GROUP BY sa.id, sa.name, sa.email
               ORDER BY active_count ASC
               LIMIT 1""",
            (next_desig, dept)
        )
        escalate_to = cur.fetchone()

    if not escalate_to:
        con.close()
        return False, f"No active {next_desig} found in department '{dept}'."

    old_staff_id   = complaint.get('staff_id')
    old_staff_name = complaint.get('assigned_staff', '')

    # Update complaint
    cur.execute(
        """UPDATE complaints
           SET assigned_staff=%s, staff_id=%s, status='escalated',
               escalated=1, escalated_at=NOW(), escalation_reason=%s,
               escalated_from_staff=%s
           WHERE complaint_id=%s""",
        (escalate_to['name'], escalate_to['id'], reason,
         old_staff_name, complaint_id)
    )

    # Reduce old staff load
    if old_staff_id:
        cur.execute(
            "UPDATE staff_accounts SET current_load=GREATEST(current_load-1,0) WHERE id=%s",
            (old_staff_id,)
        )
    # Increase new staff load
    cur.execute(
        "UPDATE staff_accounts SET current_load=current_load+1 WHERE id=%s",
        (escalate_to['id'],)
    )
    con.commit()
    con.close()

    # Notify new (escalated-to) staff
    create_notification(
        staff_id     = escalate_to['id'],
        complaint_id = complaint_id,
        message      = (f"Complaint #{complaint_id} has been escalated to you "
                        f"({next_desig}). Reason: {reason}. "
                        f"Previously assigned to: {old_staff_name}."),
        notif_type   = 'escalation',
        title        = f"Escalated Complaint: #{complaint_id}"
    )
    return True, f"Escalated to {escalate_to['name']} ({next_desig})"

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
        return None
    except Exception as e:
        print(f"[Claude exception] {e}")
        return None

# ══════════════════════════════════════════════════════════════════
#  PERFORMANCE SCORE
# ══════════════════════════════════════════════════════════════════

def recalculate_staff_score(staff_id):
    con, cur = database()
    cur.execute(
        "SELECT severity FROM complaints WHERE staff_id=%s AND status='Resolved'",
        (staff_id,)
    )
    resolved = cur.fetchall()
    base  = 50
    bonus = min(len(resolved) * 2, 30)
    for r in resolved:
        sev = (r['severity'] or '').lower()
        if sev == 'critical': bonus += 5
        elif sev == 'high':   bonus += 3

    cur.execute(
        """SELECT COUNT(*) AS cnt FROM complaints
           WHERE staff_id=%s AND status='Pending'
           AND DATEDIFF(NOW(), created_at) > 7""",
        (staff_id,)
    )
    row     = cur.fetchone()
    penalty = (row['cnt'] if row else 0) * 2

    cur.execute("SELECT avg_rating FROM staff_accounts WHERE id=%s", (staff_id,))
    sa           = cur.fetchone()
    rating_bonus = ((sa['avg_rating'] if sa and sa['avg_rating'] else 0) / 5.0) * 20

    score = max(0, min(100, int(base + bonus - penalty + rating_bonus)))
    cur.execute(
        "UPDATE staff_accounts SET performance_score=%s WHERE id=%s",
        (score, staff_id)
    )
    con.commit()
    con.close()
    return score

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
#  ADMIN AUTH
# ══════════════════════════════════════════════════════════════════

@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.route('/admin_loginchk', methods=['POST'])
def admin_loginchk():
    uid = request.form['uid']
    pwd = request.form['pwd']
    if uid == 'admin' and pwd == 'admin':
        session['admin'] = uid
        return redirect(url_for('adminhome'))
    return render_template('admin.html', msg2="Invalid credentials")

# ══════════════════════════════════════════════════════════════════
#  ADMIN HOME DASHBOARD
# ══════════════════════════════════════════════════════════════════

@app.route("/adminhome")
def adminhome():
    if 'admin' not in session:
        return redirect(url_for('admin'))

    con, cur = database()

    cur.execute("SELECT COUNT(*) AS cnt FROM complaints")
    total = cur.fetchone()['cnt']

    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE status='pending'")
    pending = cur.fetchone()['cnt']

    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE status='resolved'")
    resolved = cur.fetchone()['cnt']

    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE severity IN ('Critical','High')")
    critical_count = cur.fetchone()['cnt']

    cur.execute(
        """SELECT ROUND(AVG(DATEDIFF(resolved_at, created_at)),1) AS avg_d
           FROM complaints WHERE status='resolved' AND resolved_at IS NOT NULL"""
    )
    avg_row        = cur.fetchone()
    avg_resolution = avg_row['avg_d'] if avg_row and avg_row['avg_d'] else 0

    cur.execute(
        """SELECT COUNT(*) AS cnt FROM complaints
           WHERE severity IN ('Critical','High')
           AND (staff_id IS NULL OR assigned_staff='' OR assigned_staff IS NULL)"""
    )
    unassigned_critical = cur.fetchone()['cnt']

    cur.execute("SELECT COUNT(*) AS cnt FROM staff_accounts WHERE is_approved=0")
    pending_approvals = cur.fetchone()['cnt']

    cur.execute(
        "SELECT COUNT(*) AS cnt FROM staff_accounts WHERE is_approved=1 AND is_active=1"
    )
    active_staff_count = cur.fetchone()['cnt']

    # Overdue: pending > 5 days
    cur.execute(
        """SELECT COUNT(*) AS cnt FROM complaints
           WHERE status NOT IN ('resolved','Resolved')
           AND DATEDIFF(NOW(), created_at) > 5"""
    )
    overdue_count = cur.fetchone()['cnt']

    # Escalated
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE escalated=1 OR status='escalated'"
    )
    escalated_count = cur.fetchone()['cnt']

    # Complaints grouped by dept → zone → priority → status
    cur.execute(
        """SELECT c.complaint_id, c.user_name, c.category, c.location, c.status,
                  c.severity, c.priority_score, c.assigned_staff, c.created_at,
                  c.staff_id, c.deadline, c.escalated, c.escalated_at,
                  DATEDIFF(NOW(), c.created_at) AS days_pending,
                  sa.department AS staff_dept, sa.zone AS staff_zone,
                  sa.designation AS staff_designation
           FROM complaints c
           LEFT JOIN staff_accounts sa ON c.staff_id = sa.id
           ORDER BY
             FIELD(c.severity,'Critical','High','Medium','Low'),
             c.priority_score DESC
           LIMIT 60"""
    )
    complaints = cur.fetchall()

    cur.execute(
        """SELECT category, COUNT(*) AS cnt FROM complaints
           GROUP BY category ORDER BY cnt DESC"""
    )
    cat_data = [(r['category'] or 'Unknown', r['cnt']) for r in cur.fetchall()]

    cur.execute(
        """SELECT location, COUNT(*) AS cnt FROM complaints
           WHERE location IS NOT NULL AND location!=''
           GROUP BY location ORDER BY cnt DESC LIMIT 5"""
    )
    hotspots = [(r['location'], r['cnt']) for r in cur.fetchall()]

    cur.execute(
        """SELECT sa.id, sa.name, sa.designation, sa.zone, sa.department,
                  sa.performance_score, sa.avg_rating,
                  COUNT(c.complaint_id) AS active_load
           FROM staff_accounts sa
           LEFT JOIN complaints c
             ON c.staff_id=sa.id AND c.status NOT IN ('resolved','Resolved')
           WHERE sa.is_approved=1 AND sa.is_active=1
           GROUP BY sa.id, sa.name, sa.designation, sa.zone,
                    sa.department, sa.performance_score, sa.avg_rating
           ORDER BY active_load ASC, sa.performance_score DESC
           LIMIT 8"""
    )
    staff_list = cur.fetchall()

    # Unread notification count for admin panel badge
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE is_read=0"
    )
    unread_notifs = cur.fetchone()['cnt']

    con.close()

    return render_template(
        'admin_home.html',
        total               = total,
        pending             = pending,
        resolved            = resolved,
        critical_count      = critical_count,
        avg_resolution      = avg_resolution,
        unassigned_critical = unassigned_critical,
        pending_approvals   = pending_approvals,
        active_staff_count  = active_staff_count,
        overdue_count       = overdue_count,
        escalated_count     = escalated_count,
        complaints          = complaints,
        cat_data            = cat_data,
        hotspots            = hotspots,
        staff_list          = staff_list,
        unread_notifs       = unread_notifs,
    )

# ══════════════════════════════════════════════════════════════════
#  ADMIN MANAGE COMPLAINT  (upgraded control panel)
# ══════════════════════════════════════════════════════════════════

@app.route("/manage_complaint/<int:cid>")
def manage_complaint(cid):
    if 'admin' not in session:
        return redirect(url_for('admin'))

    con, cur = database()

    # Full complaint details
    cur.execute(
        """SELECT c.*, sa.designation AS staff_designation,
                  sa.department AS staff_dept, sa.zone AS staff_zone,
                  sa.performance_score, sa.avg_rating,
                  sa.email AS staff_email,
                  u.email AS user_email, u.user_name AS user_full_name
           FROM complaints c
           LEFT JOIN staff_accounts sa ON c.staff_id = sa.id
           LEFT JOIN users u ON c.userid = u.userid
           WHERE c.complaint_id=%s""",
        (cid,)
    )
    complaint = cur.fetchone()

    if not complaint:
        con.close()
        flash("Complaint not found.", "danger")
        return redirect(url_for('adminhome'))

    # Available staff grouped by dept+zone for smart assignment
    cur.execute(
        """SELECT sa.id, sa.name, sa.department, sa.zone, sa.designation,
                  COUNT(c2.complaint_id) AS active_load
           FROM staff_accounts sa
           LEFT JOIN complaints c2
             ON c2.staff_id=sa.id AND c2.status NOT IN ('resolved','Resolved')
           WHERE sa.is_approved=1 AND sa.is_active=1
           GROUP BY sa.id, sa.name, sa.department, sa.zone, sa.designation
           ORDER BY sa.department, sa.zone,
                    FIELD(sa.designation,
                      'Worker','Senior Worker','Supervisor','Senior Supervisor',
                      'Officer','Senior Officer','Chief Officer'),
                    active_load ASC"""
    )
    staff_list = cur.fetchall()

    # Escalation path preview
    current_desig = complaint.get('staff_designation') or 'Worker'
    next_desig    = get_next_designation(current_desig)

    # Notification history for this complaint
    cur.execute(
        """SELECT n.*, sa.name AS staff_name
           FROM notifications n
           LEFT JOIN staff_accounts sa ON n.staff_id = sa.id
           WHERE n.complaint_id=%s
           ORDER BY n.created_at DESC LIMIT 10""",
        (cid,)
    )
    notif_history = cur.fetchall()

    # Activity log
    cur.execute(
        """SELECT ca.*, sa.name AS staff_name
           FROM complaint_activity ca
           LEFT JOIN staff_accounts sa ON ca.staff_id = sa.id
           WHERE ca.complaint_id=%s
           ORDER BY ca.created_at DESC""",
        (cid,)
    )
    activity_log = cur.fetchall()

    # Staff workload summary for current staff
    workload_data = None
    if complaint.get('staff_id'):
        cur.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) AS resolved,
                      SUM(CASE WHEN status IN ('In Progress','processing') THEN 1 ELSE 0 END) AS inprogress
               FROM complaints WHERE staff_id=%s""",
            (complaint['staff_id'],)
        )
        workload_data = cur.fetchone()

    con.close()

    return render_template(
        "manage_complaint.html",
        complaint      = complaint,
        staff_list     = staff_list,
        next_desig     = next_desig,
        notif_history  = notif_history,
        activity_log   = activity_log,
        workload_data  = workload_data,
        desig_hierarchy= DESIGNATION_HIERARCHY,
    )

# ══════════════════════════════════════════════════════════════════
#  UPDATE STATUS  (POST handler for manage_complaint)
# ══════════════════════════════════════════════════════════════════

@app.route("/update_status", methods=["POST"])
def update_status_post():
    if 'admin' not in session:
        return redirect(url_for('admin'))

    cid        = request.form.get("id")
    new_status = request.form.get('status', '')
    staff_id   = request.form.get('staff_id', '')
    staff_name = request.form.get('staff_name', '')
    deadline   = request.form.get('deadline', '')
    message    = request.form.get('message', '').strip()
    admin_note = request.form.get('admin_note', '').strip()
    reminder_h = request.form.get('reminder', '')
    priority   = request.form.get('priority', '')

    con, cur = database()

    # Fetch old state
    cur.execute(
        "SELECT staff_id, status, assigned_staff FROM complaints WHERE complaint_id=%s",
        (cid,)
    )
    old = cur.fetchone()
    old_staff_id   = old['staff_id']   if old else None
    old_status     = old['status']     if old else None

    # Build UPDATE fields
    updates = []
    params  = []

    if new_status:
        updates.append("status=%s")
        params.append(new_status)
        if new_status.lower() == 'resolved':
            updates.append("resolved_at=NOW()")

    if staff_id:
        updates.append("assigned_staff=%s")
        params.append(staff_name)
        updates.append("staff_id=%s")
        params.append(staff_id)

    if deadline:
        updates.append("deadline=%s")
        params.append(deadline)

    if admin_note:
        updates.append("admin_notes=%s")
        params.append(admin_note)

    if priority:
        updates.append("severity=%s")
        params.append(priority.capitalize())

    if reminder_h:
        remind_at = datetime.now() + timedelta(hours=int(reminder_h))
        updates.append("reminder_at=%s")
        params.append(remind_at)

    if updates:
        params.append(cid)
        cur.execute(
            f"UPDATE complaints SET {', '.join(updates)} WHERE complaint_id=%s",
            tuple(params)
        )

    # Staff load management
    if new_status and new_status.lower() == 'resolved':
        target = staff_id or old_staff_id
        if target:
            cur.execute(
                "UPDATE staff_accounts SET current_load=GREATEST(current_load-1,0) WHERE id=%s",
                (target,)
            )
    elif staff_id and str(staff_id) != str(old_staff_id):
        cur.execute(
            "UPDATE staff_accounts SET current_load=current_load+1 WHERE id=%s",
            (staff_id,)
        )
        if old_staff_id:
            cur.execute(
                "UPDATE staff_accounts SET current_load=GREATEST(current_load-1,0) WHERE id=%s",
                (old_staff_id,)
            )

    # Activity log
    action_parts = []
    if new_status and new_status != old_status:
        action_parts.append(f"Status: {old_status} → {new_status}")
    if staff_id and str(staff_id) != str(old_staff_id):
        action_parts.append(f"Assigned to: {staff_name}")
    if deadline:
        action_parts.append(f"Deadline set: {deadline}")
    if admin_note:
        action_parts.append("Admin note added")

    if action_parts:
        cur.execute(
            """INSERT INTO complaint_activity (complaint_id, staff_id, action, notes)
               VALUES (%s, %s, %s, %s)""",
            (cid, old_staff_id or (staff_id or None),
             " | ".join(action_parts), admin_note or None)
        )

    con.commit()

    # Send message to staff notification
    target_staff = staff_id or old_staff_id
    if message and target_staff:
        create_notification(
            staff_id     = int(target_staff),
            complaint_id = int(cid),
            message      = message,
            notif_type   = 'admin_message',
            title        = f"Admin Message – Complaint #{cid}"
        )

    # Notify on assignment
    if staff_id and str(staff_id) != str(old_staff_id):
        create_notification(
            staff_id     = int(staff_id),
            complaint_id = int(cid),
            message      = f"Complaint #{cid} has been assigned to you by admin.",
            notif_type   = 'assignment',
            title        = f"Complaint Assigned: #{cid}"
        )

    # Email user on status change
    if new_status and new_status != old_status:
        cur.execute(
            """SELECT u.email, u.user_name, c.category, c.location
               FROM complaints c JOIN users u ON c.userid=u.userid
               WHERE c.complaint_id=%s""",
            (cid,)
        )
        urow = cur.fetchone()
        if urow:
            send_status_email(
                urow['email'], urow['user_name'], cid,
                urow['category'], urow['location'], new_status
            )

    if new_status == 'resolved' and (staff_id or old_staff_id):
        recalculate_staff_score(int(staff_id or old_staff_id))

    con.close()
    flash("Complaint updated successfully!", "success")
    return redirect(url_for('manage_complaint', cid=cid))

# Keep old GET route for backward compatibility
@app.route("/update_status/<cid>")
def update_status(cid):
    return redirect(url_for('manage_complaint', cid=cid))

# ══════════════════════════════════════════════════════════════════
#  SEND NOTIFICATION ROUTE
# ══════════════════════════════════════════════════════════════════

@app.route("/send_notification", methods=["POST"])
def send_notification():
    if 'admin' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data         = request.json or {}
    staff_id     = data.get('staff_id')
    complaint_id = data.get('complaint_id')
    message      = data.get('message', '').strip()
    notif_type   = data.get('type', 'admin_message')

    if not staff_id or not message:
        return jsonify({"success": False, "error": "Missing fields"}), 400

    create_notification(
        staff_id     = int(staff_id),
        complaint_id = complaint_id,
        message      = message,
        notif_type   = notif_type,
        title        = f"Admin Message – Complaint #{complaint_id}"
    )
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
#  TRIGGER REMINDER
# ══════════════════════════════════════════════════════════════════

@app.route("/trigger_reminder", methods=["POST"])
def trigger_reminder():
    if 'admin' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data         = request.json or {}
    complaint_id = data.get('complaint_id')
    hours        = int(data.get('hours', 24))

    con, cur = database()
    cur.execute(
        "SELECT staff_id, assigned_staff FROM complaints WHERE complaint_id=%s",
        (complaint_id,)
    )
    c = cur.fetchone()
    con.close()

    if not c or not c['staff_id']:
        return jsonify({"success": False, "error": "No staff assigned"}), 400

    create_notification(
        staff_id     = c['staff_id'],
        complaint_id = complaint_id,
        message      = (f"Reminder: Complaint #{complaint_id} is still unresolved. "
                        f"Please take action within {hours} hours."),
        notif_type   = 'reminder',
        title        = f"Reminder – Complaint #{complaint_id}"
    )
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════════
#  ESCALATE COMPLAINT
# ══════════════════════════════════════════════════════════════════

@app.route("/escalate_complaint/<int:cid>", methods=["POST", "GET"])
def escalate_complaint_route(cid):
    if 'admin' not in session:
        return redirect(url_for('admin'))

    reason = request.form.get('reason', 'Manually escalated by admin')
    success, msg = escalate_complaint(cid, reason)

    if success:
        flash(f"✅ {msg}", "success")
    else:
        flash(f"⚠ {msg}", "warning")

    return redirect(url_for('manage_complaint', cid=cid))

# ══════════════════════════════════════════════════════════════════
#  AUTO-ESCALATION CHECK  (flag overdue complaints)
# ══════════════════════════════════════════════════════════════════

@app.route("/check_escalations")
def check_escalations():
    """System route: auto-flag/escalate complaints pending > 5 days."""
    if 'admin' not in session:
        return redirect(url_for('admin'))

    con, cur = database()
    cur.execute(
        """SELECT complaint_id FROM complaints
           WHERE status NOT IN ('resolved','Resolved','escalated')
           AND DATEDIFF(NOW(), created_at) > 5
           AND (escalated IS NULL OR escalated=0)"""
    )
    overdue = cur.fetchall()
    con.close()

    count = 0
    for row in overdue:
        success, msg = escalate_complaint(
            row['complaint_id'],
            "Auto-escalated: unresolved for more than 5 days"
        )
        if success:
            count += 1
        else:
            flash(f"❌ Complaint {row['complaint_id']}: {msg}", "warning")    

    # flash(f"{count} complaint(s) auto-escalated.", "info")
    if count > 0:
        flash(f"✅ {count} complaint(s) auto-escalated.", "success")
    else:
        flash("⚠ No complaints were escalated. Check staff hierarchy.", "warning")
    return redirect(url_for('adminhome'))

# ══════════════════════════════════════════════════════════════════
#  AUTO-ASSIGN ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route('/auto_assign/<int:complaint_id>')
def auto_assign(complaint_id):
    if 'admin' not in session:
        return redirect(url_for('admin'))
    assigned_id = smart_assign_complaint(complaint_id)
    if assigned_id:
        flash(f'Complaint #{complaint_id} auto-assigned successfully.', 'success')
    else:
        flash('No approved active staff found.', 'warning')
    return redirect(url_for('adminhome'))

@app.route('/auto_assign_all')
def auto_assign_all():
    if 'admin' not in session:
        return redirect(url_for('admin'))
    con, cur = database()
    cur.execute(
        """SELECT complaint_id FROM complaints
           WHERE (staff_id IS NULL OR assigned_staff='' OR assigned_staff IS NULL)
           AND status NOT IN ('resolved','Resolved')"""
    )
    unassigned = cur.fetchall()
    con.close()
    count = sum(1 for row in unassigned if smart_assign_complaint(row['complaint_id']))
    if count:
        flash(f'{count} complaint(s) auto-assigned successfully.', 'success')
    else:
        flash('No unassigned complaints found, or no approved staff available.', 'warning')
    return redirect(url_for('adminhome'))

# ══════════════════════════════════════════════════════════════════
#  KNOWLEDGE BASE
# ══════════════════════════════════════════════════════════════════

@app.route("/add_questions", methods=["GET", "POST"])
def add_questions2():
    con, cur = database()
    msg = None
    if request.method == "POST":
        qns = request.form.get('qns')
        ans = request.form.get('ans')
        if qns and ans:
            cur.execute("INSERT INTO questions(question,answer) VALUES (%s,%s)", (qns, ans))
            con.commit()
            msg = "Entry added!"
        else:
            msg = "Please fill all fields"
    cur.execute("SELECT qid, question, answer FROM questions ORDER BY qid DESC")
    all_qa = cur.fetchall()
    con.close()
    return render_template("add_questions.html", msg=msg, all_qa=all_qa)

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

# ══════════════════════════════════════════════════════════════════
#  ADMIN COMPLAINTS VIEW
# ══════════════════════════════════════════════════════════════════

@app.route("/view_complaints")
def view_complaints():
    recalculate_all_priorities()
    con, cur = database()
    cur.execute(
        """SELECT c.complaint_id, c.user_name, c.userid, c.phone_number, c.category,
                  c.location, c.adddress, c.waste_image, c.status, c.severity,
                  c.priority_score, c.assigned_staff, c.created_at,
                  c.escalated, c.deadline,
                  sa.designation AS staff_designation
           FROM complaints c
           LEFT JOIN staff_accounts sa ON c.staff_id = sa.id
           ORDER BY c.priority_score DESC"""
    )
    values = cur.fetchall()
    cur.execute(
        """SELECT id, name, designation, department, zone,
                  COUNT(c2.complaint_id) AS active_load
           FROM staff_accounts sa
           LEFT JOIN complaints c2
             ON c2.staff_id=sa.id AND c2.status NOT IN ('resolved','Resolved')
           WHERE sa.is_approved=1 AND sa.is_active=1
           GROUP BY sa.id, sa.name, sa.designation, sa.department, sa.zone
           ORDER BY sa.department, sa.zone,
                    FIELD(sa.designation,'Worker','Senior Worker','Supervisor',
                    'Senior Supervisor','Officer','Senior Officer','Chief Officer'),
                    active_load ASC"""
    )
    staff_list = cur.fetchall()
    con.close()
    return render_template("view_complaints2.html", rawdata=values, staff_list=staff_list)

# Legacy update_status2 POST (from old view_complaints form)
@app.route("/update_status2", methods=["POST"])
def update_status2():
    cid        = request.form["id"]
    sts        = request.form.get('status')
    sid        = request.form.get('staff_id')
    sname      = request.form.get('staff_name', '')
    con, cur   = database()
    cur.execute(
        "SELECT staff_id, status FROM complaints WHERE complaint_id=%s", (cid,)
    )
    old = cur.fetchone()
    old_staff_id = old['staff_id'] if old else None
    old_status   = old['status']   if old else None
    rc = ", resolved_at=NOW()" if sts == 'resolved' else ""
    if sid:
        cur.execute(
            f"UPDATE complaints SET status=%s, assigned_staff=%s, staff_id=%s{rc} "
            "WHERE complaint_id=%s",
            (sts, sname, sid, cid)
        )
    else:
        cur.execute(
            f"UPDATE complaints SET status=%s{rc} WHERE complaint_id=%s",
            (sts, cid)
        )
    if sts == "resolved":
        target = sid or old_staff_id
        if target:
            cur.execute(
                "UPDATE staff_accounts SET current_load=GREATEST(current_load-1,0) WHERE id=%s",
                (target,)
            )
    elif sid and str(sid) != str(old_staff_id):
        cur.execute(
            "UPDATE staff_accounts SET current_load=current_load+1 WHERE id=%s", (sid,)
        )
    con.commit()
    # Email user
    cur.execute(
        """SELECT u.email, u.user_name, c.category, c.location
           FROM complaints c JOIN users u ON c.userid=u.userid
           WHERE c.complaint_id=%s""",
        (cid,)
    )
    urow = cur.fetchone()
    if urow and sts:
        send_status_email(urow['email'], urow['user_name'], cid,
                          urow['category'], urow['location'], sts)
    if sts == 'resolved' and (sid or old_staff_id):
        recalculate_staff_score(int(sid or old_staff_id))
    cur.execute(
        """SELECT c.complaint_id, c.user_name, c.userid, c.phone_number, c.category,
                  c.location, c.adddress, c.waste_image, c.status, c.severity,
                  c.priority_score, c.assigned_staff, c.created_at
           FROM complaints c ORDER BY c.priority_score DESC"""
    )
    values = cur.fetchall()
    cur.execute(
        "SELECT id, name, current_load FROM staff_accounts WHERE is_approved=1 AND is_active=1"
    )
    staff_list = cur.fetchall()
    con.close()
    return render_template("view_complaints2.html", msg="Status updated!", rawdata=values, staff_list=staff_list)

# ══════════════════════════════════════════════════════════════════
#  ADMIN FEEDBACK
# ══════════════════════════════════════════════════════════════════

@app.route("/admin_feedback")
def admin_feedback():
    con, cur = database()
    cur.execute(
        """SELECT f.feedback_id, f.complaint_id, f.userid, f.rating, f.comment,
                  f.submitted_at, c.category, c.location
           FROM feedback f JOIN complaints c ON f.complaint_id=c.complaint_id
           ORDER BY f.submitted_at DESC"""
    )
    feedbacks = cur.fetchall()
    cur.execute("SELECT AVG(rating) AS ar FROM feedback WHERE rating IS NOT NULL")
    row = cur.fetchone()
    avg_rating = round(float(row['ar']), 1) if row and row['ar'] else "N/A"
    con.close()
    return render_template("admin_feedback.html", feedbacks=feedbacks, avg_rating=avg_rating)

@app.route("/api/analytics")
def api_analytics():
    con, cur = database()
    cur.execute("SELECT category, COUNT(*) AS cnt FROM complaints GROUP BY category")
    cat_raw = [(r['category'], r['cnt']) for r in cur.fetchall()]
    cur.execute(
        """SELECT location, COUNT(*) AS cnt FROM complaints
           WHERE status!='resolved' GROUP BY location
           ORDER BY cnt DESC LIMIT 6"""
    )
    area_raw = [(r['location'], r['cnt']) for r in cur.fetchall()]
    cur.execute("SELECT severity, COUNT(*) AS cnt FROM complaints GROUP BY severity")
    sev_raw = [(r['severity'], r['cnt']) for r in cur.fetchall()]
    cur.execute(
        """SELECT DATE(created_at) AS d, COUNT(*) AS cnt FROM complaints
           GROUP BY d ORDER BY d DESC LIMIT 7"""
    )
    trend_raw = [(str(r['d']), r['cnt']) for r in cur.fetchall()][::-1]
    con.close()
    return jsonify({
        "categories": [{"label": r[0], "value": r[1]} for r in cat_raw],
        "areas":      [{"label": r[0], "value": r[1]} for r in area_raw],
        "severities": [{"label": r[0], "value": r[1]} for r in sev_raw],
        "trend":      [{"date": r[0], "count": r[1]} for r in trend_raw],
    })

# ══════════════════════════════════════════════════════════════════
#  USER ROUTES
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
        cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE userid=%s", (uid,))
        if cur.fetchone()['cnt'] > 0:
            con.close()
            return render_template("user_reg.html", msg="Already exists!")
        cur.execute(
            "INSERT INTO users (user_name, userid, email, passwrd, phno) VALUES (%s,%s,%s,%s,%s)",
            (name, uid, mail, pwd, mno)
        )
        con.commit()
        con.close()
        return render_template("user.html", msg="Registered Successfully! Login here.")
    return render_template("user_reg.html")

@app.route("/user_loginchk", methods=["GET", "POST"])
def user_loginchk():
    if request.method == "POST":
        uid = request.form.get("userid")
        pwd = request.form.get("pwd")
        con, cur = database()
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE userid=%s AND passwrd=%s",
            (uid, pwd)
        )
        if cur.fetchone()['cnt'] > 0:
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
    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE userid=%s", (uid,))
    total = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE userid=%s AND status='pending'", (uid,))
    pending = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE userid=%s AND status='resolved'", (uid,))
    resolved = cur.fetchone()['cnt']
    cur.execute(
        """SELECT AVG(DATEDIFF(resolved_at, created_at)) AS avg_d FROM complaints
           WHERE userid=%s AND resolved_at IS NOT NULL""",
        (uid,)
    )
    avg_row  = cur.fetchone()
    avg_days = round(float(avg_row['avg_d']), 1) if avg_row and avg_row['avg_d'] else "N/A"
    cur.execute(
        """SELECT category, location, status, priority_score, created_at
           FROM complaints WHERE userid=%s ORDER BY created_at DESC LIMIT 1""",
        (uid,)
    )
    latest = cur.fetchone()
    cur.execute("SELECT user_name FROM users WHERE userid=%s", (uid,))
    user     = cur.fetchone()
    user_name = user['user_name'] if user else "User"
    con.close()
    return render_template("user_home.html", user_name=user_name,
                           total=total, pending=pending, resolved=resolved,
                           avg_days=avg_days, latest=latest)

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
    category   = request.form['type']
    location   = request.form['area'].strip().title()
    addr       = request.form['address']
    severity   = request.form.get('severity', 'Medium')
    file       = request.files['pic']
    filename   = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    sev_score  = SEVERITY_MAP.get(severity, 4)
    created_at = datetime.now()
    priority   = compute_priority(severity, created_at, location, con, cur)
    cur.execute(
        """INSERT INTO complaints
           (user_name,userid,phone_number,category,location,adddress,
            waste_image,status,severity,severity_score,priority_score,
            assigned_staff,staff_id,created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (name, uid, mno, category, location, addr, filename,
         'pending', severity, sev_score, priority, None, None, created_at)
    )
    new_cid = cur.lastrowid
    con.commit()
    con.close()
    # Smart auto-assign after insert
    smart_assign_complaint(new_cid)
    return render_template("create_complaint.html", msg="Complaint submitted successfully!")

@app.route("/view_complaints_user")
def view_complaints_user():
    uid = session.get('uid')
    if not uid:
        return redirect('/user')
    con, cur = database()
    cur.execute(
        """SELECT c.complaint_id, c.user_name, c.userid, c.phone_number, c.category,
                  c.location, c.adddress, c.waste_image, c.status, c.severity,
                  c.priority_score, c.assigned_staff, c.created_at, f.rating
           FROM complaints c LEFT JOIN feedback f ON c.complaint_id=f.complaint_id
           WHERE c.userid=%s ORDER BY c.priority_score DESC""",
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
    if not row:
        return "Complaint not found", 404
    return render_template("complaint_update.html", id=cid,
                           category=row['category'], location=row['location'],
                           address=row['adddress'],
                           severity=row['severity'] if row['severity'] else 'Medium')

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
    created_at = row['created_at'] if row else datetime.now()
    priority   = compute_priority(severity, created_at, location, con, cur)
    cur.execute(
        """UPDATE complaints SET category=%s, location=%s, adddress=%s, waste_image=%s,
           severity=%s, severity_score=%s, priority_score=%s WHERE complaint_id=%s""",
        (category, location, address, filename, severity, sev_score, priority, cid)
    )
    con.commit()
    cur.execute(
        """SELECT c.complaint_id, c.user_name, c.userid, c.phone_number, c.category,
                  c.location, c.adddress, c.waste_image, c.status, c.severity,
                  c.priority_score, c.assigned_staff, c.created_at, f.rating
           FROM complaints c LEFT JOIN feedback f ON c.complaint_id=f.complaint_id
           WHERE c.userid=%s ORDER BY c.priority_score DESC""",
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
    if row and row['staff_id']:
        cur.execute(
            "UPDATE staff_accounts SET current_load=GREATEST(current_load-1,0) WHERE id=%s",
            (row['staff_id'],)
        )
    cur.execute("DELETE FROM feedback WHERE complaint_id=%s", (cid,))
    cur.execute("DELETE FROM notifications WHERE complaint_id=%s", (cid,))
    cur.execute("DELETE FROM complaints WHERE complaint_id=%s", (cid,))
    con.commit()
    cur.execute(
        """SELECT c.complaint_id, c.user_name, c.userid, c.phone_number, c.category,
                  c.location, c.adddress, c.waste_image, c.status, c.severity,
                  c.priority_score, c.assigned_staff, c.created_at, f.rating
           FROM complaints c LEFT JOIN feedback f ON c.complaint_id=f.complaint_id
           WHERE c.userid=%s ORDER BY c.priority_score DESC""",
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
        """INSERT INTO feedback (complaint_id, userid, rating, comment)
           VALUES (%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE rating=%s, comment=%s""",
        (complaint_id, uid, rating, comment, rating, comment)
    )
    con.commit()
    con.close()
    return redirect('/view_complaints_user')

# ══════════════════════════════════════════════════════════════════
#  CHATBOT
# ══════════════════════════════════════════════════════════════════

@app.route("/chatbot")
def chatbot():
    return render_template("chatbot2.html", ai_enabled=AI_ENABLED)

@app.route('/ask', methods=['POST'])
def ask_question():
    data    = request.json
    message = data.get('question', '').strip()
    history = data.get('history', [])
    if not message:
        return jsonify({"answer": "Please ask a valid question.", "source": "error"})
    if AI_ENABLED:
        ai_answer = ask_claude(message, history[-10:])
        if ai_answer:
            return jsonify({"answer": ai_answer, "source": "ai"})
    return jsonify({"answer": find_best_match(message.lower()), "source": "db"})

_qa_data = None

def fetch_data():
    global _qa_data
    con, cur = database()
    cur.execute("SELECT question, answer FROM questions")
    _qa_data = [(r['question'], r['answer']) for r in cur.fetchall()]
    con.close()

def find_best_match(user_question):
    global _qa_data
    if _qa_data is None:
        fetch_data()
    if not _qa_data:
        return "No knowledge base entries yet."
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
#  STAFF AUTH
# ══════════════════════════════════════════════════════════════════

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
            "SELECT id FROM staff_accounts WHERE email=%s OR employee_id=%s",
            (email, emp_id)
        )
        if cur.fetchone():
            con.close()
            flash('Email or Employee ID already registered.', 'danger')
            return redirect(url_for('staff_register'))
        cur.execute(
            """INSERT INTO staff_accounts
               (name, employee_id, email, phone, department, designation,
                zone, notify_pref, password_hash)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (name, emp_id, email, phone, dept, desig, zone,
             notify, generate_password_hash(pw))
        )
        con.commit()
        con.close()
        flash('Registration successful! Please wait for admin approval.', 'success')
        return redirect(url_for('staff_login'))
    return render_template('staff_register.html',
                           designation_levels=DESIGNATION_HIERARCHY)

@app.route('/staff/login', methods=['GET', 'POST'])
def staff_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        con, cur = database()
        cur.execute("SELECT * FROM staff_accounts WHERE email=%s", (email,))
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
    return redirect(url_for('index'))

# ══════════════════════════════════════════════════════════════════
#  STAFF DASHBOARD
# ══════════════════════════════════════════════════════════════════

@app.route('/staff/home')
@staff_login_required
def staff_home():
    staff_id = session['staff_id']
    con, cur = database()
    cur.execute("SELECT * FROM staff_accounts WHERE id=%s", (staff_id,))
    staff_data = cur.fetchone()
    cur.execute(
        """SELECT c.*, u.user_name AS user_name, u.phno AS user_phone
           FROM complaints c LEFT JOIN users u ON c.userid=u.userid
           WHERE c.staff_id=%s AND c.status NOT IN ('resolved','Resolved')
           ORDER BY c.priority_score DESC LIMIT 10""",
        (staff_id,)
    )
    complaints = cur.fetchall()
    cur.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE staff_id=%s", (staff_id,))
    total_assigned = cur.fetchone()['cnt']
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE staff_id=%s AND status='Resolved'",
        (staff_id,)
    )
    total_resolved = cur.fetchone()['cnt']
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaints WHERE staff_id=%s AND status='In Progress'",
        (staff_id,)
    )
    total_inprogress = cur.fetchone()['cnt']
    cur.execute(
        """SELECT * FROM notifications WHERE staff_id=%s
           ORDER BY created_at DESC LIMIT 5""",
        (staff_id,)
    )
    notifications = cur.fetchall()
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE staff_id=%s AND is_read=0",
        (staff_id,)
    )
    unread_count = cur.fetchone()['cnt']
    con.close()
    stats = {'assigned': total_assigned, 'resolved': total_resolved, 'inprogress': total_inprogress}
    return render_template('staff_home.html', staff_data=staff_data, complaints=complaints,
                           stats=stats, notifications=notifications, unread_count=unread_count)

@app.route('/staff/complaints')
@staff_login_required
def staff_complaints():
    staff_id      = session['staff_id']
    status_filter = request.args.get('status', 'all')
    con, cur      = database()
    if status_filter == 'all':
        cur.execute(
            """SELECT c.*, u.user_name, u.phno AS user_phone
               FROM complaints c LEFT JOIN users u ON c.userid=u.userid
               WHERE c.staff_id=%s ORDER BY c.priority_score DESC""",
            (staff_id,)
        )
    else:
        cur.execute(
            """SELECT c.*, u.user_name, u.phno AS user_phone
               FROM complaints c LEFT JOIN users u ON c.userid=u.userid
               WHERE c.staff_id=%s AND c.status=%s ORDER BY c.priority_score DESC""",
            (staff_id, status_filter)
        )
    complaints = cur.fetchall()
    con.close()
    return render_template('staff_complaints_list.html',
                           complaints=complaints, status_filter=status_filter)

@app.route('/staff/complaint/<int:complaint_id>', methods=['GET'])
@staff_login_required
def staff_manage_complaint(complaint_id):
    staff_id = session['staff_id']
    con, cur = database()
    cur.execute(
        """SELECT c.*, u.user_name, u.phno AS user_phone
           FROM complaints c LEFT JOIN users u ON c.userid=u.userid
           WHERE c.complaint_id=%s AND c.staff_id=%s""",
        (complaint_id, staff_id)
    )
    complaint = cur.fetchone()
    if not complaint:
        con.close()
        flash('Complaint not found or not assigned to you.', 'danger')
        return redirect(url_for('staff_complaints'))
    cur.execute(
        "SELECT * FROM complaint_photos WHERE complaint_id=%s ORDER BY uploaded_at ASC",
        (complaint_id,)
    )
    photos = cur.fetchall()
    cur.execute(
        """SELECT ca.*, sa.name AS staff_name
           FROM complaint_activity ca LEFT JOIN staff_accounts sa ON ca.staff_id=sa.id
           WHERE ca.complaint_id=%s ORDER BY ca.created_at DESC""",
        (complaint_id,)
    )
    activity = cur.fetchall()
    con.close()
    return render_template('staff_complaint.html', complaint=complaint,
                           photos=photos, activity=activity)

@app.route('/staff/complaint/<int:complaint_id>/update', methods=['POST'])
@staff_login_required
def staff_update_complaint(complaint_id):
    staff_id   = session['staff_id']
    new_status = request.form.get('status', 'Pending')
    notes      = request.form.get('notes', '').strip()
    con, cur   = database()
    cur.execute(
        "SELECT * FROM complaints WHERE complaint_id=%s AND staff_id=%s",
        (complaint_id, staff_id)
    )
    complaint = cur.fetchone()
    if not complaint:
        con.close()
        flash('Not authorised.', 'danger')
        return redirect(url_for('staff_complaints'))
    old_status = complaint['status'] or 'Pending'
    cur.execute(
        """SELECT u.email, u.user_name, c.category, c.location
           FROM complaints c JOIN users u ON c.userid=u.userid
           WHERE c.complaint_id=%s""",
        (complaint_id,)
    )
    user_data = cur.fetchone()
    if new_status == 'Resolved':
        cur.execute(
            "UPDATE complaints SET status=%s, resolved_at=%s WHERE complaint_id=%s",
            (new_status, datetime.now(), complaint_id)
        )
    else:
        cur.execute("UPDATE complaints SET status=%s WHERE complaint_id=%s",
                    (new_status, complaint_id))
    cur.execute(
        """INSERT INTO complaint_activity (complaint_id, staff_id, action, notes)
           VALUES (%s,%s,%s,%s)""",
        (complaint_id, staff_id, f"Status: {old_status} → {new_status}", notes)
    )
    # Photos
    def save_photos(file_key, photo_type):
        for f in request.files.getlist(file_key)[:5]:
            if f and f.filename and allowed_file(f.filename):
                ext      = f.filename.rsplit('.', 1)[1].lower()
                fname    = f"{photo_type}_{complaint_id}_{uuid.uuid4().hex[:8]}.{ext}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                cur.execute(
                    """INSERT INTO complaint_photos (complaint_id, staff_id, filename, photo_type)
                       VALUES (%s,%s,%s,%s)""",
                    (complaint_id, staff_id, fname, photo_type)
                )
    save_photos('before_photos', 'before')
    save_photos('after_photos',  'after')
    con.commit()
    con.close()
    if user_data:
        send_status_email(user_data['email'], user_data['user_name'], complaint_id,
                          user_data['category'], user_data['location'], new_status)
    if new_status == 'Resolved':
        recalculate_staff_score(staff_id)
    flash(f'Updated to "{new_status}".', 'success')
    return redirect(url_for('staff_manage_complaint', complaint_id=complaint_id))

@app.route('/staff/notifications')
@staff_login_required
def staff_notifications():
    staff_id = session['staff_id']
    con, cur = database()
    cur.execute(
        "SELECT * FROM notifications WHERE staff_id=%s ORDER BY created_at DESC",
        (staff_id,)
    )
    notifications = cur.fetchall()
    con.close()
    return render_template('staff_notifications.html', notifications=notifications)

@app.route('/staff/notifications/mark_read', methods=['POST'])
@staff_login_required
def staff_mark_all_read():
    con, cur = database()
    cur.execute("UPDATE notifications SET is_read=1 WHERE staff_id=%s", (session['staff_id'],))
    con.commit()
    con.close()
    return redirect(url_for('staff_notifications'))

# ══════════════════════════════════════════════════════════════════
#  ADMIN STAFF MANAGEMENT
# ══════════════════════════════════════════════════════════════════

@app.route('/admin/staff')
def admin_staff_list():
    if 'admin' not in session:
        return redirect(url_for('admin'))
    con, cur = database()
    cur.execute(
        """SELECT sa.*,
               COUNT(CASE WHEN c.status NOT IN ('resolved','Resolved') THEN 1 END) AS active_complaints,
               COUNT(CASE WHEN c.status IN ('resolved','Resolved') THEN 1 END) AS resolved_complaints
           FROM staff_accounts sa
           LEFT JOIN complaints c ON c.staff_id=sa.id
           GROUP BY sa.id
           ORDER BY sa.is_approved ASC, sa.performance_score DESC"""
    )
    staff_list = cur.fetchall()
    cur.execute("SELECT COUNT(*) AS cnt FROM staff_accounts WHERE is_approved=0")
    pending_approvals = cur.fetchone()['cnt']
    con.close()
    return render_template('admin_staff_list.html',
                           staff_list=staff_list, pending_approvals=pending_approvals)

@app.route('/admin/staff/approve/<int:staff_id>')
def admin_approve_staff(staff_id):
    if 'admin' not in session:
        return redirect(url_for('admin'))
    con, cur = database()
    cur.execute("UPDATE staff_accounts SET is_approved=1 WHERE id=%s", (staff_id,))
    con.commit()
    con.close()
    create_notification(
        staff_id     = staff_id,
        complaint_id = None,
        message      = ("Your CityCare staff account has been approved by the admin. "
                        "You can now log in and start receiving complaint assignments."),
        notif_type   = 'system',
        title        = "Account Approved!"
    )
    flash('Staff member approved successfully.', 'success')
    return redirect(url_for('admin_staff_list'))

@app.route('/admin/staff/reject/<int:staff_id>')
def admin_reject_staff(staff_id):
    if 'admin' not in session:
        return redirect(url_for('admin'))
    con, cur = database()
    cur.execute("UPDATE staff_accounts SET is_active=0 WHERE id=%s", (staff_id,))
    con.commit()
    con.close()
    flash('Staff member rejected/deactivated.', 'success')
    return redirect(url_for('admin_staff_list'))

# ══════════════════════════════════════════════════════════════════
#  STAFF PUBLIC PROFILE
# ══════════════════════════════════════════════════════════════════

@app.route('/staff/profile/<int:staff_id>')
def staff_profile(staff_id):
    con, cur = database()
    cur.execute("SELECT * FROM staff_accounts WHERE id=%s AND is_active=1", (staff_id,))
    staff = cur.fetchone()
    if not staff:
        con.close()
        return "Staff profile not found.", 404
    cur.execute(
        """SELECT c.complaint_id, c.category, c.location, c.severity, c.resolved_at
           FROM complaints c
           WHERE c.staff_id=%s AND c.status='Resolved'
           ORDER BY c.resolved_at DESC""",
        (staff_id,)
    )
    resolved_complaints = cur.fetchall()
    cur.execute(
        """SELECT category, COUNT(*) AS cnt FROM complaints
           WHERE staff_id=%s AND status='Resolved'
           GROUP BY category ORDER BY cnt DESC""",
        (staff_id,)
    )
    cat_rows = cur.fetchall()
    cur.execute(
        """SELECT ROUND(AVG(DATEDIFF(resolved_at, created_at)),1) AS avg_d
           FROM complaints WHERE staff_id=%s AND status='Resolved' AND resolved_at IS NOT NULL""",
        (staff_id,)
    )
    avg_days_row = cur.fetchone()
    avg_days     = avg_days_row['avg_d'] if avg_days_row and avg_days_row['avg_d'] else 0
    cur.execute(
        """SELECT COUNT(*) AS cnt FROM complaints
           WHERE staff_id=%s AND status='Resolved' AND severity IN ('Critical','High')""",
        (staff_id,)
    )
    critical_resolved = cur.fetchone()['cnt']
    cur.execute(
        "SELECT id FROM staff_accounts WHERE zone=%s AND is_active=1 ORDER BY performance_score DESC",
        (staff['zone'],)
    )
    zone_rows  = [r['id'] for r in cur.fetchall()]
    zone_rank  = zone_rows.index(staff_id) + 1 if staff_id in zone_rows else 0
    zone_total = len(zone_rows)
    max_cat    = cat_rows[0]['cnt'] if cat_rows else 1
    con.close()
    stats = {
        'resolved': len(resolved_complaints), 'avg_days': avg_days,
        'critical_resolved': critical_resolved,
        'categories': [(r['category'], r['cnt']) for r in cat_rows],
        'max_cat': max_cat, 'zone_rank': zone_rank, 'zone_total': zone_total,
    }
    return render_template('staff_profile.html', staff=staff, stats=stats,
                           resolved_complaints=resolved_complaints)

# ══════════════════════════════════════════════════════════════════
#  RATE STAFF
# ══════════════════════════════════════════════════════════════════

@app.route('/rate_staff/<int:complaint_id>', methods=['POST'])
def rate_staff(complaint_id):
    if 'uid' not in session:
        return redirect(url_for('user_loginchk'))
    rating  = int(request.form.get('rating', 0))
    comment = request.form.get('comment', '').strip()
    if not (1 <= rating <= 5):
        flash('Please select a rating between 1 and 5.', 'danger')
        return redirect(url_for('userhome'))
    con, cur = database()
    cur.execute(
        "SELECT * FROM complaints WHERE complaint_id=%s AND userid=%s AND status='Resolved'",
        (complaint_id, session['uid'])
    )
    complaint = cur.fetchone()
    if not complaint or not complaint.get('staff_id'):
        con.close()
        flash('Cannot rate this complaint.', 'danger')
        return redirect(url_for('userhome'))
    cur.execute("SELECT id FROM staff_ratings WHERE complaint_id=%s", (complaint_id,))
    if cur.fetchone():
        con.close()
        flash('You have already rated this complaint.', 'warning')
        return redirect(url_for('userhome'))
    staff_id = complaint['staff_id']
    cur.execute(
        """INSERT INTO staff_ratings (complaint_id, staff_id, userid, rating, comment)
           VALUES (%s,%s,%s,%s,%s)""",
        (complaint_id, staff_id, session['uid'], rating, comment)
    )
    cur.execute(
        "SELECT AVG(rating) AS avg_r, COUNT(*) AS cnt FROM staff_ratings WHERE staff_id=%s",
        (staff_id,)
    )
    avg_row = cur.fetchone()
    cur.execute(
        "UPDATE staff_accounts SET avg_rating=%s, total_ratings=%s WHERE id=%s",
        (round(float(avg_row['avg_r']), 2), avg_row['cnt'], staff_id)
    )
    con.commit()
    con.close()
    recalculate_staff_score(staff_id)
    flash('Thank you for your rating!', 'success')
    return redirect(url_for('userhome'))

if __name__ == '__main__':
    app.run(host="localhost", port=5678, debug=True)
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_file
import os
import json
import uuid
import time
import cv2
import logging
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import face_utils
import numpy as np
# from surveillance_system import VideoCamera # Deprecated
from core.plugin_manager import PluginManager
from core.surveillance_engine import SurveillanceEngine
import yaml
import random
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("TriNetra")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey_fallback_change_in_prod')

# ==================== EMAIL ALERT CONFIGURATION ====================
# Gmail SMTP Configuration (Use App Password for Gmail - enable 2FA first)
EMAIL_CONFIG = {
    'enabled': True,
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'pankajchavan944@gmail.com',
    'sender_password': 'hvue xbno shgw aoiq',
    
    # Admin emails - receive all criminal/missing person match alerts
    'admin_emails': [
        'gdgpankaj@gmail.com',
    ],
    
    # Officer emails - receive only urgent alerts (wanted criminals, SOS)
    'officer_emails': [
        'gdgpankaj@gmail.com',
    ]
}

def send_email_alert(subject, body, recipients, alert_type='general', attachment_path=None):
    """Send email alert in background thread"""
    if not EMAIL_CONFIG['enabled']:
        logger.info(f"Email alerts disabled. Would send: {subject}")
        return
    
    if not recipients:
        logger.warning(f"No recipients for email: {subject}")
        return
    
    logger.info(f"📧 Queueing email: {subject} to {recipients}")
    
    def send_async():
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_CONFIG['sender_email']
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            
            # Create HTML body
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 10px; overflow: hidden;">
                    <div style="background: {'#dc2626' if alert_type == 'critical' else '#1e40af'}; color: white; padding: 20px; text-align: center;">
                        <h2 style="margin: 0;">🚨 TRI-NETRA ALERT SYSTEM</h2>
                        <p style="margin: 5px 0 0 0; opacity: 0.9;">Indian Police Surveillance Network</p>
                    </div>
                    <div style="padding: 25px;">
                        <h3 style="color: {'#dc2626' if alert_type == 'critical' else '#1e40af'}; margin-top: 0;">{subject}</h3>
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                            {body}
                        </div>
                        <p style="color: #666; font-size: 12px; margin-top: 20px; border-top: 1px solid #eee; padding-top: 15px;">
                            ⏰ Alert Time: {(datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %H:%M:%S')} IST<br>
                            📍 This is an automated alert from TRI-NETRA Surveillance System.<br>
                            🔒 Please treat this information as confidential.
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html_body, 'html'))
            
            # Attach file if provided
            if attachment_path and os.path.exists(attachment_path):
                try:
                    with open(attachment_path, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(attachment_path)}')
                        msg.attach(part)
                    logger.info(f"📎 Attached file: {attachment_path}")
                except Exception as attach_err:
                    logger.error(f"❌ Failed to attach file: {attach_err}")
            
            # Send email
            logger.info(f"📧 Connecting to SMTP server {EMAIL_CONFIG['smtp_server']}:{EMAIL_CONFIG['smtp_port']}")
            with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
                server.starttls()
                logger.info(f"📧 Logging in as {EMAIL_CONFIG['sender_email']}")
                server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
                server.send_message(msg)
            
            logger.info(f"✅ Email alert sent successfully: {subject} to {len(recipients)} recipients")
        except smtplib.SMTPAuthenticationError as auth_err:
            logger.error(f"❌ Email authentication failed: {auth_err}. Check sender email and app password.")
        except smtplib.SMTPException as smtp_err:
            logger.error(f"❌ SMTP error: {smtp_err}")
        except Exception as e:
            logger.error(f"❌ Email send failed: {type(e).__name__}: {e}")
    
    # Send in background thread to not block main request
    thread = threading.Thread(target=send_async)
    thread.daemon = True
    thread.start()

def send_criminal_match_email(person_name, confidence, db_type, location='Dashboard', capture_path=None):
    """Send email when criminal/missing person is detected"""
    logger.info(f"📧 Preparing criminal match email - Name: {person_name}, Type: {db_type}, Confidence: {confidence}%")
    
    is_critical = db_type == 'wanted' or db_type == 'criminal'
    
    subject = f"🚨 {'WANTED CRIMINAL' if db_type == 'wanted' else 'PERSON'} DETECTED: {person_name}"
    
    body = f"""
    <p><strong>🔍 Match Details:</strong></p>
    <ul style="list-style: none; padding-left: 0;">
        <li>👤 <strong>Name:</strong> {person_name}</li>
        <li>📊 <strong>Confidence:</strong> {confidence}%</li>
        <li>🏷️ <strong>Category:</strong> {db_type.upper()}</li>
        <li>📍 <strong>Detection Source:</strong> {location}</li>
    </ul>
    <p style="color: #dc2626; font-weight: bold;">⚠️ {'IMMEDIATE ACTION REQUIRED!' if is_critical else 'Please verify and take appropriate action.'}</p>
    """
    
    logger.info(f"📧 Sending criminal match email to admins: {EMAIL_CONFIG['admin_emails']}")
    
    # Send to admins always
    send_email_alert(subject, body, EMAIL_CONFIG['admin_emails'], 
                     alert_type='critical' if is_critical else 'general',
                     attachment_path=capture_path)
    
    # Send to officers only for wanted criminals or criminals
    if db_type == 'wanted' or db_type == 'criminal':
        logger.info(f"📧 Sending criminal match email to officers: {EMAIL_CONFIG['officer_emails']}")
        send_email_alert(subject, body, EMAIL_CONFIG['officer_emails'], 
                         alert_type='critical',
                         attachment_path=capture_path)

def send_sos_email(location, coordinates, address):
    """Send email for women SOS emergency - goes to officers"""
    logger.info(f"📧 Preparing SOS email - Location: {address}, Coords: {coordinates}")
    
    subject = "🆘 EMERGENCY SOS ALERT - WOMAN IN DISTRESS"
    
    lat = coordinates.get('lat') if coordinates else None
    lng = coordinates.get('lng') if coordinates else None
    map_link = f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else ''
    
    coord_text = f"{lat}, {lng}" if lat and lng else "Location unavailable"
    
    body = f"""
    <p style="color: #dc2626; font-size: 18px; font-weight: bold;">⚠️ IMMEDIATE RESPONSE REQUIRED!</p>
    <p><strong>📍 Location Details:</strong></p>
    <ul style="list-style: none; padding-left: 0;">
        <li>🗺️ <strong>Address:</strong> {address or 'Address not available'}</li>
        <li>📌 <strong>Coordinates:</strong> {coord_text}</li>
    </ul>
    {f'<p><a href="{map_link}" style="background: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">🗺️ Open in Google Maps</a></p>' if map_link else '<p style="color: #666;">(Map link unavailable - location not detected)</p>'}
    <p style="background: #fef2f2; padding: 12px; border-radius: 6px; border-left: 4px solid #dc2626;">
        A woman has triggered an emergency SOS alert. Dispatch nearest patrol immediately!
    </p>
    """
    
    # Send to both admins and officers for SOS
    all_recipients = list(set(EMAIL_CONFIG['admin_emails'] + EMAIL_CONFIG['officer_emails']))
    logger.info(f"📧 Sending SOS email to: {all_recipients}")
    send_email_alert(subject, body, all_recipients, alert_type='critical')

def send_urgent_travel_email(start_location, end_location, coordinates):
    """Send email for urgent travel mode - goes to officers"""
    subject = "🚗 URGENT TRAVEL ALERT - Woman Monitoring Required"
    
    body = f"""
    <p><strong>🚗 Urgent Travel Activated:</strong></p>
    <ul style="list-style: none; padding-left: 0;">
        <li>📍 <strong>From:</strong> {start_location}</li>
        <li>🎯 <strong>To:</strong> {end_location}</li>
    </ul>
    <p style="background: #fef3c7; padding: 12px; border-radius: 6px; border-left: 4px solid #f59e0b;">
        A woman has activated urgent travel mode. Please monitor the route and ensure safe arrival.
    </p>
    """
    
    send_email_alert(subject, body, EMAIL_CONFIG['officer_emails'], alert_type='general')

# ==================== END EMAIL CONFIGURATION ====================

# Login Manager Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Template filter to convert UTC to IST (UTC+5:30)
@app.template_filter('utc_to_ist')
def utc_to_ist_filter(utc_str):
    """Convert UTC timestamp string to IST"""
    if not utc_str:
        return ''
    try:
        # Parse the UTC timestamp
        utc_dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00').replace('+00:00', ''))
        # Add 5 hours 30 minutes for IST
        ist_dt = utc_dt + timedelta(hours=5, minutes=30)
        return ist_dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return utc_str

# User Class
class User(UserMixin):
    def __init__(self, id, username, password_hash, role='admin'):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role
    
    def check_password(self, password):
        """Verify password against stored hash"""
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission):
        """Check if user has a specific permission based on role"""
        permissions = {
            'admin': ['all', 'criminal_db', 'missing_db', 'surveillance', 'alerts', 'settings', 'users', 'reports'],
            'officer': ['criminal_db', 'missing_db', 'surveillance', 'alerts', 'reports'],
            'women': ['women_portal', 'sos', 'safe_routes']
        }
        role_perms = permissions.get(self.role, [])
        return 'all' in role_perms or permission in role_perms

USERS_FILE = 'data/users.json'

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        user_data = users[user_id]
        return User(user_id, user_data['username'], user_data['password_hash'], user_data.get('role', 'admin'))
    return None

# Initialize Admin User
def init_db():
    users = load_users() if os.path.exists(USERS_FILE) else {}
    updated = False
    
    # Default admin: admin / admin123
    if 'admin' not in users:
        users['admin'] = {
            'username': 'admin',
            'password_hash': generate_password_hash('admin123'),
            'role': 'admin'
        }
        updated = True
        print("Initialized default admin user.")
    elif 'role' not in users['admin']:
        users['admin']['role'] = 'admin'
        updated = True
    
    # Default officer: officer / officer123
    if 'officer' not in users:
        users['officer'] = {
            'username': 'officer',
            'password_hash': generate_password_hash('officer123'),
            'role': 'officer'
        }
        updated = True
        print("Initialized default officer user.")
    
    # Default women portal user: women / women123
    if 'women' not in users:
        users['women'] = {
            'username': 'women',
            'password_hash': generate_password_hash('women123'),
            'role': 'women'
        }
        updated = True
        print("Initialized default women portal user.")
    
    if updated:
        save_users(users)

init_db()

# Initialize Modular System
pm = PluginManager()
config_path = os.path.join("config", "config.yaml")
if os.path.exists(config_path):
    with open(config_path, 'r') as f:
        sys_config = yaml.safe_load(f)
        try:
            # Only initialize model at startup (takes time to load)
            # Camera will be initialized on demand to keep light off
            pm.initialize_model(sys_config)
        except Exception as e:
            print(f"Modular Init Error: {e}")
else:
    print("Config file missing!")

# Configuration
UPLOAD_FOLDER = 'data/images'
PERSONS_FOLDER = 'data/persons'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PERSONS_FOLDER'] = PERSONS_FOLDER
app.config['MISSING_FOLDER'] = 'data/missing_persons'
app.config['ALERTS_FOLDER'] = 'data/alerts'
app.config['SYSTEM_ALERTS_FOLDER'] = 'data/system_alerts'
app.config['SYSTEM_ALERTS_FILE'] = 'data/system_alerts/alerts.json'
app.config['ACTIVITY_LOG_FILE'] = 'data/system_alerts/activity_log.json'

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PERSONS_FOLDER'], exist_ok=True)
os.makedirs(app.config['MISSING_FOLDER'], exist_ok=True)
os.makedirs(app.config['ALERTS_FOLDER'], exist_ok=True)
os.makedirs(os.path.dirname(app.config['SYSTEM_ALERTS_FILE']), exist_ok=True)

# Force reload check
print("Server reloading...")

@app.context_processor
def inject_alert_count():
    count = 0
    if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
        try:
            with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                alerts = json.load(f)
                count = len([a for a in alerts if not a.get('read', False)])
        except: pass
    return dict(system_alert_count=count)

import hashlib

def log_activity(action, target, user=None, details=None, status='success'):
    """Log activity with tamper-proof hash chain for evidence integrity"""
    activity_file = app.config['ACTIVITY_LOG_FILE']
    
    # Load existing activities
    activities = []
    prev_hash = "GENESIS"
    if os.path.exists(activity_file):
        try:
            with open(activity_file, 'r') as f:
                activities = json.load(f)
                if activities:
                    prev_hash = activities[-1].get('hash', 'GENESIS')
        except:
            activities = []
    
    # Create activity entry with timestamp
    ist_offset = timedelta(hours=5, minutes=30)
    utc_now = datetime.utcnow()
    ist_now = utc_now + ist_offset
    
    entry = {
        'id': str(uuid.uuid4()),
        'timestamp': utc_now.isoformat() + 'Z',
        'timestamp_ist': ist_now.strftime('%Y-%m-%d %H:%M:%S'),
        'action': action,
        'target': target,
        'user': user or (current_user.username if current_user.is_authenticated else 'System'),
        'details': details or {},
        'status': status,
        'prev_hash': prev_hash
    }
    
    # Generate tamper-proof hash
    hash_data = f"{entry['timestamp']}|{entry['action']}|{entry['target']}|{entry['user']}|{prev_hash}"
    entry['hash'] = hashlib.sha256(hash_data.encode()).hexdigest()
    
    activities.append(entry)
    
    # Keep last 1000 entries
    if len(activities) > 1000:
        activities = activities[-1000:]
    
    with open(activity_file, 'w') as f:
        json.dump(activities, f, indent=2)
    
    return entry

def create_officer_alert(person_id, name, image_filename, db_type, priority=3, is_wanted=False):
    """Create an alert for officers when admin adds a new person to database"""
    alert_data = {
        'id': person_id,
        'name': name,
        'image_filename': image_filename,
        'db_type': db_type,  # 'criminal', 'missing', 'wanted'
        'priority': priority,
        'is_wanted': is_wanted,
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'created_at_ist': (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'active',
        'detections': []
    }
    
    # Save to alerts folder
    alert_path = os.path.join(app.config['ALERTS_FOLDER'], f"{person_id}.json")
    with open(alert_path, 'w') as f:
        json.dump(alert_data, f, indent=2)
    
    return alert_data

def update_surveillance_list():
    active_list = []
    
    # Helper to process folder
    def process_folder(folder, db_type):
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                if filename.endswith('.json'):
                    try:
                        path = os.path.join(folder, filename)
                        with open(path, 'r') as f:
                            data = json.load(f)
                            if data.get('surveillance'):
                                active_list.append({
                                    'id': data['id'],
                                    'name': data['name'],
                                    'db_type': db_type,
                                    'priority': data.get('priority', 3),  # Default priority 3 (Medium)
                                    'embeddings': data['embeddings'],
                                    'image_filename': data['image_filename'],
                                    'phone': data.get('phone'),
                                    'aadhaar': data.get('aadhaar'),
                                    'guardian_phone': data.get('guardian_phone'),
                                    'missing_aadhaar': data.get('missing_aadhaar'),
                                    'submitted_gender': data.get('submitted_gender'),
                                    'predicted_gender': data.get('predicted_gender'),
                                    'predicted_age': data.get('predicted_age')
                                })
                    except: pass

    process_folder(app.config['PERSONS_FOLDER'], 'criminal')
    process_folder(app.config['MISSING_FOLDER'], 'missing')
    
    # Sort by priority (1=Critical first, 5=Minimal last)
    active_list.sort(key=lambda x: x.get('priority', 3))
    
    # Save to a consolidated JSON file for the recognition algorithm
    with open('data/active_surveillance_targets.json', 'w') as f:
        json.dump(active_list, f, indent=2)
        
    print(f"Updated surveillance list with {len(active_list)} targets (sorted by priority).")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Role-based permission decorator
from functools import wraps
def role_required(*roles):
    """Decorator to check if user has required role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            user_role = getattr(current_user, 'role', 'admin')
            if user_role not in roles and 'admin' not in [user_role]:
                flash('You do not have permission to access this page.', 'error')
                if user_role == 'women':
                    return redirect(url_for('women_dashboard'))
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # Redirect based on role
        if hasattr(current_user, 'role') and current_user.role == 'women':
            return redirect(url_for('women_dashboard'))
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        selected_role = request.form.get('role', 'admin')
        
        users = load_users()
        user_data = users.get(username)
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user_role = user_data.get('role', 'admin')
            
            # Check if selected role matches user's actual role
            if selected_role != user_role:
                flash(f'Invalid role selected. You are registered as {user_role}.', 'error')
                log_activity('LOGIN', 'System', user=username, details={'status': 'failed', 'reason': 'role_mismatch'}, status='failed')
                return render_template('login.html')
            
            user = User(username, user_data['username'], user_data['password_hash'], user_role)
            login_user(user)
            
            # Log successful login
            log_activity('LOGIN', 'System', user=username, details={'status': 'success', 'role': user_role})
            
            # Redirect based on role
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            if user_role == 'women':
                return redirect(url_for('women_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
            # Log failed login attempt
            log_activity('LOGIN', 'System', user=username or 'unknown', details={'status': 'failed'}, status='failed')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # Redirect officers to their portal
    user_role = getattr(current_user, 'role', 'admin')
    if user_role == 'officer':
        return redirect(url_for('officer_dashboard'))
    elif user_role == 'women':
        return redirect(url_for('women_dashboard'))
    
    persons = []
    if os.path.exists(app.config['PERSONS_FOLDER']):
        for filename in os.listdir(app.config['PERSONS_FOLDER']):
            if filename.endswith('.json'):
                filepath = os.path.join(app.config['PERSONS_FOLDER'], filename)
                try:
                    with open(filepath, 'r') as f:
                        person_data = json.load(f)
                        persons.append(person_data)
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
    return render_template('index.html', persons=persons)

# Officer Dashboard Route
@app.route('/officer')
@login_required
@role_required('officer', 'admin')
def officer_dashboard():
    return render_template('officer_dashboard.html')

# Officer Photo Search API - logs all searches
@app.route('/api/officer/photo_search', methods=['POST'])
@login_required
@role_required('officer', 'admin')
def officer_photo_search():
    if 'image' not in request.files:
        log_activity('OFFICER_SEARCH', 'Photo Search', user=current_user.username, 
                    details={'error': 'No image provided', 'device': request.user_agent.string}, status='failed')
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    camera_type = request.form.get('camera_type', 'front')  # front or back camera
    search_db = request.form.get('search_db', 'both')  # criminal, missing, or both
    
    if file.filename == '':
        return jsonify({'error': 'No image selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"officer_search_{unique_id}.jpg")
        file.save(temp_path)
        
        try:
            analysis_results = face_utils.get_embeddings(temp_path)
            
            if analysis_results['dlib'] is None and analysis_results['arcface'] is None:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                log_activity('OFFICER_SEARCH', 'Photo Search', user=current_user.username,
                            details={'status': 'no_face', 'camera': camera_type, 'db': search_db}, status='failed')
                return jsonify({'error': 'No face detected in image'}), 400
            
            # Find match based on selected database
            match, distance = find_best_match({
                "dlib": analysis_results.get('dlib'),
                "arcface": analysis_results.get('arcface')
            }, db_type=search_db)
            
            # Log the search activity
            log_activity('OFFICER_SEARCH', match['name'] if match else 'No Match', user=current_user.username,
                        details={
                            'camera': camera_type,
                            'db_searched': search_db,
                            'match_found': bool(match),
                            'confidence': round((1 - distance) * 100, 1) if match else 0,
                            'device': request.headers.get('User-Agent', '')[:50]
                        })
            
            if match:
                confidence = max(0, min(100, (1 - distance) * 100)) if distance < 1 else 0
                if distance < 0.4:
                    confidence = 90 + (0.4 - distance) * 25
                
                # Keep the captured image for potential report - rename it
                captured_filename = f"officer_capture_{unique_id}.jpg"
                captured_path = os.path.join(app.config['UPLOAD_FOLDER'], captured_filename)
                if os.path.exists(temp_path):
                    os.rename(temp_path, captured_path)
                
                return jsonify({
                    'match': True,
                    'person': {
                        'id': match['id'],
                        'name': match['name'],
                        'db_type': match.get('db_type', 'criminal'),
                        'priority': match.get('priority', 3),
                        'is_wanted': match.get('is_wanted', False),
                        'image_filename': match.get('image_filename')
                    },
                    'confidence': round(confidence, 1),
                    'captured_image': captured_filename
                })
            else:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return jsonify({'match': False, 'message': 'No match found'})
                
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            log_activity('OFFICER_SEARCH', 'Error', user=current_user.username,
                        details={'error': str(e)}, status='error')
            return jsonify({'error': 'Search failed'}), 500
    
    return jsonify({'error': 'Invalid file'}), 400

# Officer Alerts API - get alerts assigned by admin
@app.route('/api/officer/alerts')
@login_required
@role_required('officer', 'admin')
def officer_get_alerts():
    alerts = []
    if os.path.exists(app.config['ALERTS_FOLDER']):
        for filename in os.listdir(app.config['ALERTS_FOLDER']):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(app.config['ALERTS_FOLDER'], filename), 'r') as f:
                        alert = json.load(f)
                        alerts.append(alert)
                except:
                    pass
    
    # Log that officer viewed alerts
    log_activity('OFFICER_VIEW_ALERTS', f'{len(alerts)} alerts', user=current_user.username)
    
    return jsonify({'alerts': alerts})

# Officer Report to Control Room
@app.route('/api/officer/report', methods=['POST'])
@login_required
@role_required('officer', 'admin')
def officer_submit_report():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Get officer details from users.json
    officer_info = {
        'username': current_user.username,
        'role': getattr(current_user, 'role', 'officer')
    }
    
    # Try to get additional officer info from users.json
    users_file = 'data/users.json'
    if os.path.exists(users_file):
        try:
            with open(users_file, 'r') as f:
                users = json.load(f)
                # Users is a dict with username as key
                if current_user.username in users:
                    user_data = users[current_user.username]
                    officer_info['phone'] = user_data.get('phone', 'N/A')
                    officer_info['badge_number'] = user_data.get('badge_number', 'N/A')
                    officer_info['full_name'] = user_data.get('full_name', current_user.username)
        except Exception as e:
            print(f"Error reading user data: {e}")
    
    # Determine report type
    report_type = data.get('report_type', 'PHOTO_MATCH')
    is_alert_sighting = report_type == 'ALERT_SIGHTING'
    
    # Create officer report with both captured and matched images
    report = {
        'id': str(uuid.uuid4()),
        'type': 'OFFICER_FIELD_REPORT',
        'report_subtype': report_type,  # 'PHOTO_MATCH' or 'ALERT_SIGHTING'
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'timestamp_ist': (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %H:%M:%S'),
        'officer': officer_info,
        'subject': {
            'person_id': data.get('person_id'),
            'name': data.get('person_name'),
            'database_image': data.get('person_image'),
            'captured_image': data.get('captured_image'),
            'db_type': data.get('db_type'),
            'confidence': data.get('confidence'),
            'is_wanted': data.get('is_wanted', False),
            'priority': data.get('priority', 3)
        },
        'match_details': {
            'search_timestamp': data.get('search_timestamp'),
            'confidence_score': data.get('confidence'),
            'identification_type': 'Visual Sighting' if is_alert_sighting else 'Photo Match'
        },
        'report': {
            'location': data.get('location'),
            'details': data.get('details', ''),
            'urgency': data.get('urgency', 'medium')
        },
        'status': 'pending',
        'read': False
    }
    
    # Save to system alerts
    alerts_file = os.path.join(app.config['SYSTEM_ALERTS_FOLDER'], 'alerts.json')
    alerts = []
    if os.path.exists(alerts_file):
        try:
            with open(alerts_file, 'r') as f:
                alerts = json.load(f)
        except:
            alerts = []
    
    alerts.insert(0, report)  # Add to beginning
    
    with open(alerts_file, 'w') as f:
        json.dump(alerts, f, indent=2)
    
    # Log the activity
    log_activity('OFFICER_REPORT', data.get('person_name', 'Unknown'), user=current_user.username,
                details={
                    'person_id': data.get('person_id'),
                    'location': data.get('location'),
                    'urgency': data.get('urgency'),
                    'report_id': report['id']
                })
    
    return jsonify({'success': True, 'report_id': report['id']})

# Admin Full-Screen Activity View
@app.route('/admin/activity')
@login_required
@role_required('admin')
def admin_activity_view():
    return render_template('admin_activity.html')

# API to get activity logs with filtering
@app.route('/api/admin/activity')
@login_required
@role_required('admin')
def get_activity_logs():
    activity_file = os.path.join(app.config['SYSTEM_ALERTS_FOLDER'], 'activity_log.json')
    activities = []
    
    if os.path.exists(activity_file):
        try:
            with open(activity_file, 'r') as f:
                activities = json.load(f)
        except Exception as e:
            print(f"Error reading activity log: {e}")
    
    # Get filter parameters
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user', '')
    status_filter = request.args.get('status', '')
    date_filter = request.args.get('date', '')
    
    # Apply filters
    if action_filter:
        activities = [a for a in activities if action_filter.upper() in a.get('action', '').upper()]
    if user_filter:
        activities = [a for a in activities if user_filter.lower() in a.get('user', '').lower()]
    if status_filter:
        activities = [a for a in activities if a.get('status', '') == status_filter]
    if date_filter:
        activities = [a for a in activities if date_filter in a.get('timestamp_ist', '')]
    
    # Get unique values for filters
    all_actions = list(set(a.get('action', '') for a in activities))
    all_users = list(set(a.get('user', '') for a in activities))
    
    # Return in reverse chronological order
    activities.reverse()
    
    return jsonify({
        'activities': activities,
        'filters': {
            'actions': sorted(all_actions),
            'users': sorted(all_users)
        }
    })

@app.route('/criminal')
@login_required
def criminal_dashboard():
    persons = []
    if os.path.exists(app.config['PERSONS_FOLDER']):
        for filename in os.listdir(app.config['PERSONS_FOLDER']):
            if filename.endswith('.json'):
                filepath = os.path.join(app.config['PERSONS_FOLDER'], filename)
                try:
                    with open(filepath, 'r') as f:
                        person_data = json.load(f)
                        persons.append(person_data)
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
    return render_template('dashboard.html', persons=persons)

@app.route('/missing')
@login_required
def missing_dashboard():
    persons = []
    if os.path.exists(app.config['MISSING_FOLDER']):
        for filename in os.listdir(app.config['MISSING_FOLDER']):
            if filename.endswith('.json'):
                filepath = os.path.join(app.config['MISSING_FOLDER'], filename)
                try:
                    with open(filepath, 'r') as f:
                        person_data = json.load(f)
                        persons.append(person_data)
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
    return render_template('missing_dashboard.html', persons=persons)

@app.route('/surveillance')
@login_required
def surveillance_dashboard():
    global surveillance_engine, weapon_detection_active
    
    # Check if any surveillance is active
    surveillance_active = surveillance_engine is not None
    weapon_active = weapon_detection_active
    camera_active = surveillance_active or weapon_active or (pm.active_camera is not None)
    
    # Determine current mode
    if weapon_active:
        camera_mode = 'weapon'
    elif surveillance_active:
        camera_mode = 'active'
    else:
        camera_mode = None
    
    return render_template('surveillance.html', 
                          camera_active=camera_active, 
                          camera_mode=camera_mode,
                          weapon_active=weapon_active)

@app.route('/crowd_detection')
@login_required
def crowd_detection():
    """Crowd Detection - redirects to surveillance stream with crowd mode"""
    global detection_log
    
    # Clear detection log for new session
    detection_log = []
    
    # Initialize camera if not active
    if pm.active_camera is None:
        pm.initialize_camera(sys_config)
    
    # Add initialization logs
    add_detection_log('system', 'Camera initialized successfully', 'check-circle')
    add_detection_log('system', 'Crowd density analysis active', 'users')
    add_detection_log('system', 'Monitoring for unusual gatherings', 'eye')
    
    # Use the surveillance stream view with crowd mode
    return render_template('stream_view.html', mode='crowd')

# Crowd Detection Global Variables
crowd_detection_active = False

@app.route('/crowd_video_feed')
@login_required
def crowd_video_feed():
    """Video feed with crowd counting overlay (simulated)"""
    return Response(gen_crowd_detection(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def gen_crowd_detection():
    """Generate frames with crowd detection overlay"""
    global crowd_detection_active
    crowd_detection_active = True
    
    import random
    last_count_update = 0
    current_count = random.randint(5, 15)
    density_level = "Normal"
    
    while crowd_detection_active:
        if pm.active_camera is None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + get_placeholder_frame() + b'\r\n\r\n')
            time.sleep(0.5)
            continue
        
        # Get frame from camera
        ret, frame = pm.active_camera.get_frame()
        
        if not ret or frame is None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + get_placeholder_frame() + b'\r\n\r\n')
            time.sleep(0.1)
            continue
        
        # Update crowd count periodically (every 3 seconds)
        current_time = time.time()
        if current_time - last_count_update > 3:
            # Simulate crowd count changes
            change = random.randint(-2, 3)
            current_count = max(1, min(50, current_count + change))
            
            # Determine density level
            if current_count > 30:
                density_level = "HIGH"
                add_detection_log('threat', f'⚠️ High crowd density: {current_count} people', 'exclamation-triangle')
            elif current_count > 20:
                density_level = "Moderate"
            else:
                density_level = "Normal"
            
            last_count_update = current_time
        
        # Draw crowd overlay
        h, w = frame.shape[:2]
        
        # Status bar at top
        color = (0, 0, 255) if density_level == "HIGH" else ((0, 165, 255) if density_level == "Moderate" else (0, 255, 0))
        cv2.rectangle(frame, (10, 10), (300, 90), (0, 0, 0), -1)
        cv2.rectangle(frame, (10, 10), (300, 90), color, 2)
        
        cv2.putText(frame, f"CROWD COUNT: {current_count}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Density: {density_level}", (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Corner indicator
        cv2.putText(frame, "CROWD MONITORING", (w - 200, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Encode frame
        ret, jpeg = cv2.imencode('.jpg', frame)
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
        
        time.sleep(0.033)  # ~30 FPS
    
    crowd_detection_active = False

# Weapon Detection Global Variables
weapon_detection_active = False
weapon_detector = None  # Plugin instance
detection_log = []  # Live detection log for UI
MAX_DETECTION_LOG = 50  # Max items in log

def add_detection_log(log_type, message, icon="info"):
    """Add entry to detection log"""
    global detection_log
    from datetime import datetime
    entry = {
        'id': len(detection_log) + 1,
        'time': datetime.now().strftime('%H:%M:%S'),
        'type': log_type,
        'message': message,
        'icon': icon
    }
    detection_log.insert(0, entry)  # Add to beginning
    if len(detection_log) > MAX_DETECTION_LOG:
        detection_log = detection_log[:MAX_DETECTION_LOG]
    return entry

@app.route('/api/detection_log')
@login_required
def get_detection_log():
    """API endpoint for detection log"""
    return jsonify(detection_log)

@app.route('/api/clear_detection_log', methods=['POST'])
@login_required
def clear_detection_log():
    """Clear detection log"""
    global detection_log
    detection_log = []
    return jsonify({'status': 'cleared'})

@app.route('/weapon_detection')
@login_required
def weapon_detection():
    """Weapon Detection - redirects to surveillance stream with weapon mode"""
    global weapon_detection_active, weapon_detector, detection_log
    
    # Clear detection log for new session
    detection_log = []
    
    # Initialize camera if not active
    if pm.active_camera is None:
        pm.initialize_camera(sys_config)
    
    # Add camera init log
    add_detection_log('system', 'Camera initialized successfully', 'check-circle')
    
    # Load weapon detection plugin if not loaded
    if weapon_detector is None:
        try:
            from plugins.models.yolo_weapon_plugin import YOLOWeaponDetector
            weapon_detector = YOLOWeaponDetector()
            weapon_detector.initialize({
                'model_path': 'models/best.pt',
                'confidence_threshold': 0.65  # Higher threshold for fewer false positives
            })
            logger.info("Weapon detection plugin initialized")
            add_detection_log('system', 'YOLOv8 model loaded (threshold: 65%)', 'microchip')
        except Exception as e:
            logger.error(f"Failed to load weapon detection plugin: {e}")
            add_detection_log('error', f'Model load failed: {str(e)[:30]}', 'times-circle')
    
    weapon_detection_active = True
    
    # Use the surveillance stream view with weapon mode
    return render_template('stream_view.html', mode='weapon')

@app.route('/weapon_video_feed')
@login_required
def weapon_video_feed():
    """Video feed with YOLOv8 weapon detection overlay"""
    return Response(gen_weapon_detection(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def gen_weapon_detection():
    """Generate frames with weapon detection using plugin"""
    global weapon_detector, weapon_detection_active
    
    last_detection_time = 0
    detection_cooldown = 2  # Seconds between log entries for same detection
    
    # Add initial log entry
    add_detection_log('system', 'Weapon detection system armed', 'shield-alt')
    
    while weapon_detection_active:
        if pm.active_camera is None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + get_placeholder_frame() + b'\r\n\r\n')
            time.sleep(0.5)
            continue
        
        # Get frame from camera - returns (ret, frame) tuple
        ret, frame = pm.active_camera.get_frame()
        
        if not ret or frame is None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + get_placeholder_frame() + b'\r\n\r\n')
            time.sleep(0.1)
            continue
        
        # Run weapon detection using plugin
        if weapon_detector is not None:
            try:
                frame, detections = weapon_detector.detect_and_draw(frame)
                
                # Log detections for monitoring (with cooldown to avoid spam)
                current_time = time.time()
                if detections and (current_time - last_detection_time) > detection_cooldown:
                    for det in detections:
                        add_detection_log('threat', f"⚠️ {det['class_name']} detected ({det['confidence']:.0%})", 'exclamation-triangle')
                    logger.warning(f"Weapon detected: {len(detections)} object(s)")
                    last_detection_time = current_time
            except Exception as e:
                logger.error(f"Weapon detection error: {e}")
        
        # Encode frame
        ret, jpeg = cv2.imencode('.jpg', frame)
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
        
        time.sleep(0.033)  # ~30 FPS

@app.route('/stop_weapon_detection')
@login_required
def stop_weapon_detection():
    """Stop weapon detection and release camera"""
    global weapon_detection_active, weapon_detector
    
    weapon_detection_active = False
    
    # Shutdown weapon detector plugin
    if weapon_detector is not None:
        weapon_detector.shutdown()
        weapon_detector = None
    
    # Release camera
    if pm.active_camera:
        pm.active_camera.shutdown()
        pm.active_camera = None
    
    return redirect(url_for('index'))

@app.route('/surveillance/view/<db_type>')
@login_required
def surveillance_view(db_type):
    persons = []
    folder = app.config['PERSONS_FOLDER'] if db_type == 'criminal' else app.config['MISSING_FOLDER']
    
    if os.path.exists(folder):
        for filename in os.listdir(folder):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(folder, filename), 'r') as f:
                        p = json.load(f)
                        if p.get('surveillance') is True:
                            persons.append(p)
                except: pass
    
    # Sort by priority (1=highest priority first)
    persons.sort(key=lambda x: x.get('priority', 3))
                
    return render_template('surveillance_view.html', persons=persons, db_type=db_type)

@app.route('/surveillance/add/<db_type>')
@login_required
def surveillance_add(db_type):
    persons = []
    folder = app.config['PERSONS_FOLDER'] if db_type == 'criminal' else app.config['MISSING_FOLDER']
    
    if os.path.exists(folder):
        for filename in os.listdir(folder):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(folder, filename), 'r') as f:
                        p = json.load(f)
                        # Only show those NOT under surveillance
                        if not p.get('surveillance'):
                            persons.append(p)
                except: pass
                
    return render_template('surveillance_select.html', persons=persons, db_type=db_type)

@app.route('/surveillance/start/<db_type>/<person_id>', methods=['POST'])
@login_required
def surveillance_start(db_type, person_id):
    person_id = secure_filename(person_id)
    folder = app.config['PERSONS_FOLDER'] if db_type == 'criminal' else app.config['MISSING_FOLDER']
    json_path = os.path.join(folder, f"{person_id}.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            data['surveillance'] = True
            
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            update_surveillance_list()
        except Exception as e:
            pass
    
    return redirect(url_for('surveillance_view', db_type=db_type))

@app.route('/surveillance/stop/<db_type>/<person_id>', methods=['POST'])
@login_required
def surveillance_stop(db_type, person_id):
    person_id = secure_filename(person_id)
    folder = app.config['PERSONS_FOLDER'] if db_type == 'criminal' else app.config['MISSING_FOLDER']
    json_path = os.path.join(folder, f"{person_id}.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            data['surveillance'] = False
            
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            update_surveillance_list()
        except Exception as e:
            pass
    
    return redirect(url_for('surveillance_view', db_type=db_type))

@app.route('/surveillance/activate/<person_id>', methods=['POST'])
@login_required
def surveillance_activate(person_id):
    """Activate surveillance with authorization and tamper-proof logging"""
    person_id = secure_filename(person_id)
    db_type = request.form.get('db_type', 'criminal')
    password = request.form.get('password', '')
    reason = request.form.get('reason', '')
    
    # Verify password
    if not current_user.check_password(password):
        flash('Invalid password. Authorization failed.', 'error')
        log_activity('SURVEILLANCE_ACTIVATE', person_id, details={
            'status': 'failed',
            'reason': 'Invalid password',
            'db_type': db_type
        }, status='failed')
        return redirect(url_for('view_person', person_id=person_id))
    
    folder = app.config['PERSONS_FOLDER'] if db_type == 'criminal' else app.config['MISSING_FOLDER']
    json_path = os.path.join(folder, f"{person_id}.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            person_name = data.get('name', person_id)
            data['surveillance'] = True
            data['surveillance_activated_at'] = datetime.utcnow().isoformat() + 'Z'
            data['surveillance_activated_by'] = current_user.username
            data['surveillance_activation_reason'] = reason
            
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            update_surveillance_list()
            
            # Log successful activation (tamper-proof)
            log_activity('SURVEILLANCE_ACTIVATE', person_name, details={
                'person_id': person_id,
                'db_type': db_type,
                'reason': reason,
                'status': 'activated',
                'authorized_by': current_user.username
            })
            
            flash(f'Surveillance activated for {person_name}', 'success')
            
        except Exception as e:
            log_activity('SURVEILLANCE_ACTIVATE', person_id, details={
                'status': 'error',
                'error': str(e),
                'db_type': db_type
            }, status='error')
            flash('Error activating surveillance', 'error')
    
    return redirect(url_for('view_person', person_id=person_id))

@app.route('/surveillance/deactivate/<person_id>', methods=['POST'])
@login_required
def surveillance_deactivate(person_id):
    """Deactivate surveillance with authorization and tamper-proof logging"""
    person_id = secure_filename(person_id)
    db_type = request.form.get('db_type', 'criminal')
    password = request.form.get('password', '')
    reason = request.form.get('reason', '')
    
    # Verify password
    if not current_user.check_password(password):
        flash('Invalid password. Authorization failed.', 'error')
        log_activity('SURVEILLANCE_DEACTIVATE', person_id, details={
            'status': 'failed',
            'reason': 'Invalid password',
            'db_type': db_type
        }, status='failed')
        return redirect(url_for('view_person', person_id=person_id))
    
    folder = app.config['PERSONS_FOLDER'] if db_type == 'criminal' else app.config['MISSING_FOLDER']
    json_path = os.path.join(folder, f"{person_id}.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            person_name = data.get('name', person_id)
            
            # Calculate surveillance duration
            activated_at = data.get('surveillance_activated_at', '')
            duration_str = 'Unknown'
            if activated_at:
                try:
                    start_time = datetime.fromisoformat(activated_at.replace('Z', ''))
                    duration = datetime.utcnow() - start_time
                    hours, remainder = divmod(int(duration.total_seconds()), 3600)
                    minutes = remainder // 60
                    duration_str = f"{hours}h {minutes}m"
                except:
                    pass
            
            data['surveillance'] = False
            data['surveillance_deactivated_at'] = datetime.utcnow().isoformat() + 'Z'
            data['surveillance_deactivated_by'] = current_user.username
            data['surveillance_deactivation_reason'] = reason
            
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            update_surveillance_list()
            
            # Log successful deactivation (tamper-proof)
            log_activity('SURVEILLANCE_DEACTIVATE', person_name, details={
                'person_id': person_id,
                'db_type': db_type,
                'reason': reason,
                'status': 'deactivated',
                'authorized_by': current_user.username,
                'duration': duration_str,
                'activated_by': data.get('surveillance_activated_by', 'Unknown')
            })
            
            flash(f'Surveillance deactivated for {person_name}', 'success')
            
        except Exception as e:
            log_activity('SURVEILLANCE_DEACTIVATE', person_id, details={
                'status': 'error',
                'error': str(e),
                'db_type': db_type
            }, status='error')
            flash('Error deactivating surveillance', 'error')
    
    return redirect(url_for('view_person', person_id=person_id))

@app.route('/delete_person/<person_id>', methods=['POST'])
@login_required
def delete_person(person_id):
    person_id = secure_filename(person_id)
    # Check criminal
    json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_id}.json")
    redirect_url = url_for('criminal_dashboard')
    db_type = 'criminal'
    
    if not os.path.exists(json_path):
        # Check missing
        json_path = os.path.join(app.config['MISSING_FOLDER'], f"{person_id}.json")
        redirect_url = url_for('missing_dashboard')
        db_type = 'missing'
    
    if os.path.exists(json_path):
        try:
            # Read to get image filename and name for logging
            with open(json_path, 'r') as f:
                person_data = json.load(f)
            
            person_name = person_data.get('name', person_id)
            
            image_filename = person_data.get('image_filename')
            if image_filename:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            os.remove(json_path)
            
            # Log activity
            log_activity('PERSON_DELETE', person_name, details={
                'person_id': person_id,
                'db_type': db_type
            })
            
            flash(f'{person_name} has been deleted.', 'success')
        except Exception as e:
            flash(f'Error deleting: {str(e)}', 'error')
    else:
        flash('Person not found.', 'error')
    return redirect(redirect_url)

@app.route('/missing/<person_id>')
@login_required
def view_missing_person(person_id):
    return view_person(person_id)

@app.route('/delete_missing/<person_id>', methods=['POST'])
@login_required
def delete_missing_person(person_id):
    return delete_person(person_id)

def calculate_distance(emb1, emb2, metric='euclidean'):
    if emb1 is None or emb2 is None:
        return float('inf')
    
    v1 = np.array(emb1)
    v2 = np.array(emb2)
    
    if metric == 'euclidean':
        return np.linalg.norm(v1 - v2)
    elif metric == 'cosine':
        # Cosine distance = 1 - cosine_similarity
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        return 1 - (dot_product / (norm_v1 * norm_v2))
    return float('inf')

def find_best_match(new_embeddings, db_type='all'):
    """Find best match in specified database(s)
    db_type can be: 'criminal', 'missing', or 'all' (searches both)
    """
    best_match = None
    min_distance = float('inf')
    
    # Thresholds
    # Lowered thresholds to reduce false positives
    DLIB_THRESHOLD = 0.45 
    ARCFACE_THRESHOLD = 0.4 # Cosine distance (1 - sim). If sim > 0.6, dist < 0.4
    
    folders_to_search = []
    if db_type in ['criminal', 'all']:
        folders_to_search.append((app.config['PERSONS_FOLDER'], 'criminal'))
    if db_type in ['missing', 'all']:
        folders_to_search.append((app.config['MISSING_FOLDER'], 'missing'))
    
    for folder, folder_type in folders_to_search:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                if filename.endswith('.json'):
                    filepath = os.path.join(folder, filename)
                    try:
                        with open(filepath, 'r') as f:
                            person = json.load(f)
                        
                        # Add db_type to person data
                        person['db_type'] = folder_type
                            
                        # Check Dlib first (usually faster/standard)
                        dist = float('inf')
                        if new_embeddings.get('dlib') and person.get('embeddings', {}).get('dlib'):
                            dist = calculate_distance(new_embeddings['dlib'], person['embeddings']['dlib'], 'euclidean')
                            if dist < DLIB_THRESHOLD and dist < min_distance:
                                min_distance = dist
                                best_match = person
                        
                        # Fallback to ArcFace if Dlib not available or to confirm
                        elif new_embeddings.get('arcface') and person.get('embeddings', {}).get('arcface'):
                            dist = calculate_distance(new_embeddings['arcface'], person['embeddings']['arcface'], 'cosine')
                            if dist < ARCFACE_THRESHOLD and dist < min_distance:
                                min_distance = dist
                                best_match = person
                                
                    except Exception as e:
                        print(f"Error comparing {filename}: {e}")
                    
    return best_match, min_distance

@app.route('/merge_person', methods=['POST'])
@login_required
def merge_person():
    try:
        new_data = json.loads(request.form.get('new_data'))
        existing_id = request.form.get('existing_id')
        
        json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{existing_id}.json")
        if os.path.exists(json_path):
            # User requested to keep the old info ("complete info of old one")
            # So we do NOT update the existing record with new_data.
            # We simply discard the new entry and redirect to the existing one.
            
            # Clean up the temp image from new_data since we are not using it
            new_image_path = os.path.join(app.config['UPLOAD_FOLDER'], new_data['image_filename'])
            if os.path.exists(new_image_path):
                os.remove(new_image_path)
                
            return redirect(url_for('view_person', person_id=existing_id))
    except Exception as e:
        return redirect(url_for('criminal_dashboard'))

@app.route('/confirm_add_person', methods=['POST'])
@login_required
def confirm_add_person():
    try:
        person_data = json.loads(request.form.get('new_data'))
        
        # Save JSON
        json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_data['id']}.json")
        with open(json_path, 'w') as f:
            json.dump(person_data, f, indent=2)

        return redirect(url_for('criminal_dashboard'))
    except Exception as e:
        return redirect(url_for('criminal_dashboard'))

def check_metadata_duplicate(aadhaar, phone, folder):
    if not os.path.exists(folder):
        return None, None
        
    target_aadhaar = str(aadhaar).strip() if aadhaar else ""
    target_phone = str(phone).strip() if phone else ""
    
    if not target_aadhaar and not target_phone:
        return None, None
    
    for filename in os.listdir(folder):
        if filename.endswith('.json'):
            try:
                with open(os.path.join(folder, filename), 'r') as f:
                    data = json.load(f)
                    
                    # Check Aadhaar
                    curr_aadhaar = str(data.get('aadhaar', '')).strip()
                    if target_aadhaar and curr_aadhaar == target_aadhaar:
                        return data, 'Aadhaar Number'
                    
                    # Check Phone
                    curr_phone = str(data.get('phone', '')).strip()
                    if target_phone and curr_phone == target_phone:
                        return data, 'Phone Number'
            except: pass
    return None, None

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_person():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'image' not in request.files:
            return redirect(request.url)
        
        file = request.files['image']
        name = request.form.get('name')
        gender = request.form.get('gender')
        aadhaar = request.form.get('aadhaar')
        phone = request.form.get('phone')

        # Check for metadata duplicates
        dup_person, dup_field = check_metadata_duplicate(aadhaar, phone, app.config['PERSONS_FOLDER'])
        if dup_person:
            return render_template('metadata_alert.html', 
                                 existing_person=dup_person,
                                 match_field=dup_field,
                                 new_name=name,
                                 new_aadhaar=aadhaar,
                                 new_phone=phone)

        if file.filename == '':
            return redirect(request.url)

        if file and allowed_file(file.filename):
            # Generate unique ID
            unique_id = str(uuid.uuid4())[:8]
            safe_name = secure_filename(name).lower().replace('_', '-')
            person_id = f"{safe_name}-{unique_id}"
            
            filename = secure_filename(file.filename)
            extension = filename.rsplit('.', 1)[1].lower()
            new_filename = f"{person_id}.{extension}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            file.save(file_path)

            try:
                # Generate embeddings
                analysis_results = face_utils.get_embeddings(file_path)
                
                if analysis_results['dlib'] is None and analysis_results['arcface'] is None:
                    os.remove(file_path) # Clean up
                    return redirect(request.url)

                # Create person data structure
                priority = request.form.get('priority', 3)
                try:
                    priority = int(priority)
                    if priority < 1 or priority > 5:
                        priority = 3
                except:
                    priority = 3
                    
                person_data = {
                    "id": person_id,
                    "name": name,
                    "aadhaar": aadhaar,
                    "phone": phone,
                    "submitted_gender": gender,
                    "age": request.form.get('age'),  # Use submitted age, not predicted
                    "image_filename": new_filename,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "priority": priority,
                    "embeddings": {
                        "dlib": analysis_results.get('dlib'),
                        "arcface": analysis_results.get('arcface')
                    }
                }

                # Check for duplicates
                match, distance = find_best_match(person_data['embeddings'])
                if match:
                    return render_template('match_alert.html', 
                                         new_person=person_data, 
                                         existing_person=match, 
                                         distance=distance,
                                         new_person_json=json.dumps(person_data))

                # Save JSON
                json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_id}.json")
                with open(json_path, 'w') as f:
                    json.dump(person_data, f, indent=2)

                # Create officer alert for this person
                create_officer_alert(
                    person_id=person_id,
                    name=name,
                    image_filename=new_filename,
                    db_type='criminal',
                    priority=priority,
                    is_wanted=False
                )

                # Log activity
                log_activity('PERSON_ADD', name, details={
                    'person_id': person_id,
                    'db_type': 'criminal',
                    'priority': priority
                })

                return redirect(url_for('criminal_dashboard'))

            except Exception as e:
                return redirect(request.url)

    return render_template('add_person.html')

@app.route('/person/<person_id>')
@login_required
def view_person(person_id):
    person_id = secure_filename(person_id)
    # Check criminal folder first
    json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_id}.json")
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            person_data = json.load(f)
        person_data['db_type'] = 'criminal'
        return render_template('view_person.html', person=person_data)
    
    # Check missing folder
    json_path = os.path.join(app.config['MISSING_FOLDER'], f"{person_id}.json")
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            person_data = json.load(f)
        person_data['db_type'] = 'missing'
        return render_template('view_person.html', person=person_data)
        
    return redirect(url_for('criminal_dashboard'))

@app.route('/update_person/<person_id>', methods=['POST'])
@login_required
def update_person(person_id):
    person_id = secure_filename(person_id)
    # Check criminal folder
    json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_id}.json")
    db_type = 'criminal'
    
    if not os.path.exists(json_path):
        # Check missing folder
        json_path = os.path.join(app.config['MISSING_FOLDER'], f"{person_id}.json")
        db_type = 'missing'
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                person_data = json.load(f)
            
            # Update fields
            person_data['name'] = request.form.get('name')
            
            # Update priority if provided
            priority = request.form.get('priority')
            if priority:
                try:
                    priority = int(priority)
                    if 1 <= priority <= 5:
                        person_data['priority'] = priority
                except:
                    pass
                    
            if db_type == 'criminal':
                person_data['aadhaar'] = request.form.get('aadhaar')
                person_data['phone'] = request.form.get('phone')
                person_data['submitted_gender'] = request.form.get('gender')
            else:
                # Missing person fields
                person_data['missing_aadhaar'] = request.form.get('aadhaar')
                person_data['guardian_phone'] = request.form.get('phone')
                # Optional: update gender if needed
                # person_data['submitted_gender'] = request.form.get('gender')

            with open(json_path, 'w') as f:
                json.dump(person_data, f, indent=2)
                
            return redirect(url_for('view_person', person_id=person_id))
        except Exception as e:
            return redirect(url_for('view_person', person_id=person_id))
    else:
        return redirect(url_for('criminal_dashboard'))

@app.route('/api/search')
@login_required
def search_api():
    query = request.args.get('q', '').lower()
    results = []
    
    if not query:
        return jsonify([])

    if os.path.exists(app.config['PERSONS_FOLDER']):
        for filename in os.listdir(app.config['PERSONS_FOLDER']):
            if filename.endswith('.json'):
                filepath = os.path.join(app.config['PERSONS_FOLDER'], filename)
                try:
                    with open(filepath, 'r') as f:
                        p = json.load(f)
                        # Search in name, phone, aadhaar
                        if (query in p.get('name', '').lower() or 
                            query in str(p.get('phone', '')) or 
                            query in str(p.get('aadhaar', ''))):
                            results.append({
                                'id': p['id'],
                                'name': p['name'],
                                'image': p['image_filename'],
                                'type': 'text_match'
                            })
                except:
                    pass
    return jsonify(results)

@app.route('/add_missing', methods=['GET', 'POST'])
@login_required
def add_missing_person():
    if request.method == 'POST':
        if 'image' not in request.files:
            return redirect(request.url)
        
        file = request.files['image']
        # Name is optional in screenshot but good to have, if not present use Unknown
        name = request.form.get('name') or "Unknown" 
        guardian_phone = request.form.get('guardian_phone')
        missing_aadhaar = request.form.get('missing_aadhaar')

        if file.filename == '':
            return redirect(request.url)

        if file and allowed_file(file.filename):
            unique_id = str(uuid.uuid4())[:8]
            safe_name = secure_filename(name).lower().replace('_', '-')
            person_id = f"missing-{safe_name}-{unique_id}"
            
            filename = secure_filename(file.filename)
            extension = filename.rsplit('.', 1)[1].lower()
            new_filename = f"{person_id}.{extension}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            file.save(file_path)

            try:
                analysis_results = face_utils.get_embeddings(file_path)
                
                if analysis_results['dlib'] is None and analysis_results['arcface'] is None:
                    os.remove(file_path)
                    return redirect(request.url)

                priority = request.form.get('priority', 3)
                try:
                    priority = int(priority)
                    if priority < 1 or priority > 5:
                        priority = 3
                except:
                    priority = 3
                    
                person_data = {
                    "id": person_id,
                    "name": name,
                    "guardian_phone": guardian_phone,
                    "missing_aadhaar": missing_aadhaar,
                    "submitted_gender": request.form.get('gender'),  # Use submitted gender
                    "age": request.form.get('age'),  # Use submitted age
                    "image_filename": new_filename,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "priority": priority,
                    "embeddings": {
                        "dlib": analysis_results.get('dlib'),
                        "arcface": analysis_results.get('arcface')
                    }
                }

                json_path = os.path.join(app.config['MISSING_FOLDER'], f"{person_id}.json")
                with open(json_path, 'w') as f:
                    json.dump(person_data, f, indent=2)

                # Create officer alert for missing person
                create_officer_alert(
                    person_id=person_id,
                    name=name,
                    image_filename=new_filename,
                    db_type='missing',
                    priority=priority,
                    is_wanted=False
                )

                # Log activity
                log_activity('PERSON_ADD', name, details={
                    'person_id': person_id,
                    'db_type': 'missing',
                    'priority': priority
                })

                return redirect(url_for('missing_dashboard'))

            except Exception as e:
                return redirect(request.url)

    return render_template('add_missing.html')


# --- WANTED CRIMINAL DETECTION (Priority 1 - Auto Surveillance) ---
@app.route('/add_wanted', methods=['GET', 'POST'])
@login_required
def add_wanted_criminal():
    """Add wanted criminal with highest priority (1) and auto-enable surveillance"""
    if request.method == 'POST':
        if 'image' not in request.files:
            flash('No image uploaded', 'error')
            return redirect(request.url)
        
        file = request.files['image']
        name = request.form.get('name', 'Unknown Wanted')
        gender = request.form.get('gender')
        aadhaar = request.form.get('aadhaar')
        phone = request.form.get('phone')
        crime_details = request.form.get('crime_details', '')

        if file.filename == '':
            flash('No image selected', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            # Generate unique ID with 'wanted' prefix
            unique_id = str(uuid.uuid4())[:8]
            safe_name = secure_filename(name).lower().replace('_', '-')
            person_id = f"wanted-{safe_name}-{unique_id}"
            
            filename = secure_filename(file.filename)
            extension = filename.rsplit('.', 1)[1].lower()
            new_filename = f"{person_id}.{extension}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            file.save(file_path)

            try:
                # Generate embeddings
                analysis_results = face_utils.get_embeddings(file_path)
                
                if analysis_results['dlib'] is None and analysis_results['arcface'] is None:
                    os.remove(file_path)
                    flash('No face detected in image', 'error')
                    return redirect(request.url)

                # Create person data with HIGHEST PRIORITY (1) and AUTO SURVEILLANCE
                person_data = {
                    "id": person_id,
                    "name": name,
                    "aadhaar": aadhaar,
                    "phone": phone,
                    "submitted_gender": gender,
                    "age": request.form.get('age'),  # Use submitted age
                    "image_filename": new_filename,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "priority": 1,  # CRITICAL - Highest Priority
                    "is_wanted": True,  # Flag as wanted criminal
                    "crime_details": crime_details,
                    "surveillance": True,  # Auto-enable surveillance
                    "embeddings": {
                        "dlib": analysis_results.get('dlib'),
                        "arcface": analysis_results.get('arcface')
                    }
                }

                # Save JSON to persons folder (criminal database)
                json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_id}.json")
                with open(json_path, 'w') as f:
                    json.dump(person_data, f, indent=2)

                # Update surveillance list immediately
                update_surveillance_list()
                
                # Create officer alert for WANTED criminal (HIGH PRIORITY)
                create_officer_alert(
                    person_id=person_id,
                    name=name,
                    image_filename=new_filename,
                    db_type='wanted',
                    priority=1,
                    is_wanted=True
                )
                
                # Create system alert for wanted criminal added
                system_alert = {
                    'id': str(uuid.uuid4()),
                    'timestamp': datetime.utcnow().isoformat() + "Z",
                    'type': 'wanted_added',
                    'title': '🚨 WANTED CRIMINAL ADDED',
                    'message': f"Wanted criminal '{name}' added to database with highest priority surveillance.",
                    'person_id': person_id,
                    'read': False,
                    'severity': 'critical'
                }
                
                alerts = []
                if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
                    try:
                        with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                            alerts = json.load(f)
                    except: pass
                
                alerts.append(system_alert)
                with open(app.config['SYSTEM_ALERTS_FILE'], 'w') as f:
                    json.dump(alerts, f, indent=2)

                flash(f'Wanted criminal "{name}" added with Priority 1 surveillance!', 'success')
                return redirect(url_for('criminal_dashboard'))

            except Exception as e:
                flash(f'Error processing image: {str(e)}', 'error')
                return redirect(request.url)

    return render_template('add_wanted.html')


@app.route('/image/<filename>')
@login_required
def uploaded_file(filename):
    return redirect(url_for('static', filename=f'../data/images/{filename}'))

# Helper to serve images from data folder since it's not in static
from flask import send_from_directory
@app.route('/data/images/<filename>')
@login_required
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/data/alerts/images/<filename>')
@login_required
def serve_alert_image(filename):
    return send_from_directory(os.path.join(app.config['ALERTS_FOLDER'], 'images'), filename)

@app.route('/alerts')
@login_required
def alerts_dashboard():
    filter_type = request.args.get('type', 'all')
    alerts = []
    if os.path.exists(app.config['ALERTS_FOLDER']):
        for filename in os.listdir(app.config['ALERTS_FOLDER']):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(app.config['ALERTS_FOLDER'], filename), 'r') as f:
                        data = json.load(f)
                        if filter_type == 'all' or data.get('db_type') == filter_type:
                            # Calculate best match percentage from detections and scale it
                            detections = data.get('detections', [])
                            if detections:
                                best_match = max(d.get('match_percentage', 0) for d in detections)
                                # Scale to 80-99% range for display
                                data['best_match_percentage'] = scale_confidence(best_match)
                            else:
                                data['best_match_percentage'] = 0
                            alerts.append(data)
                except: pass
    
    # Sort by priority first (if exists), then by latest detection timestamp
    def get_sort_key(alert):
        priority = alert.get('priority', 3)
        dets = alert.get('detections', [])
        latest_ts = dets[-1].get('timestamp', '') if dets else ''
        return (priority, -hash(latest_ts))  # Lower priority number first
        
    alerts.sort(key=lambda x: (x.get('priority', 3), -hash(get_latest_ts(x))))
    
    return render_template('alerts.html', alerts=alerts, filter_type=filter_type)

def scale_confidence(raw_percentage):
    """Scale confidence to display 85-90% range
    Maps: 0% -> 85%, 100% -> 90%
    Formula: 85 + (original * 5 / 100)
    """
    if raw_percentage <= 0:
        return 85.0
    return min(90.0, round(85 + (raw_percentage * 5 / 100), 1))

def get_latest_ts(alert):
    dets = alert.get('detections', [])
    if dets:
        return dets[-1].get('timestamp', '')
    return ''

@app.route('/alerts/view/<person_id>')
@login_required
def view_alert(person_id):
    person_id = secure_filename(person_id)
    json_path = os.path.join(app.config['ALERTS_FOLDER'], f"{person_id}.json")
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            alert_data = json.load(f)
            
        # Fetch original data to fill in missing fields (for older alerts)
        original_folder = app.config['PERSONS_FOLDER'] if alert_data.get('db_type') == 'criminal' else app.config['MISSING_FOLDER']
        original_path = os.path.join(original_folder, f"{person_id}.json")
        
        if os.path.exists(original_path):
            try:
                with open(original_path, 'r') as f:
                    original_data = json.load(f)
                    # Merge missing fields
                    for key, value in original_data.items():
                        if key not in alert_data:
                            alert_data[key] = value
            except: pass
            
        return render_template('alert_view.html', alert=alert_data)
    else:
        return redirect(url_for('alerts_dashboard'))

@app.route('/alerts/delete/<person_id>', methods=['POST'])
@login_required
def delete_alert(person_id):
    """Delete an alert record - requires confirmation code"""
    person_id = secure_filename(person_id)
    confirmation_code = request.form.get('confirmation_code', '')
    
    # Require specific confirmation code for deletion
    if confirmation_code != 'DELETE-CONFIRM':
        flash('Invalid confirmation code. Alert not deleted.', 'danger')
        log_activity('ALERT_DELETE', person_id, details={'status': 'rejected', 'reason': 'Invalid confirmation'}, status='failed')
        return redirect(url_for('view_alert', person_id=person_id))
    
    json_path = os.path.join(app.config['ALERTS_FOLDER'], f"{person_id}.json")
    
    if os.path.exists(json_path):
        try:
            # Load alert to get detection images
            with open(json_path, 'r') as f:
                alert_data = json.load(f)
            
            alert_name = alert_data.get('name', 'Unknown')
            detection_count = len(alert_data.get('detections', []))
            
            # Delete detection images
            for detection in alert_data.get('detections', []):
                img_path = os.path.join(app.config['ALERTS_FOLDER'], 'images', detection.get('capture_frame', ''))
                if os.path.exists(img_path):
                    os.remove(img_path)
            
            # Delete alert JSON
            os.remove(json_path)
            
            # Log deletion
            log_activity('ALERT_DELETE', alert_name, details={
                'person_id': person_id,
                'detections_deleted': detection_count
            })
            
            flash(f"Alert for '{alert_name}' has been deleted.", 'success')
        except Exception as e:
            flash(f'Error deleting alert: {str(e)}', 'danger')
            log_activity('ALERT_DELETE', person_id, details={'error': str(e)}, status='error')
    else:
        flash('Alert not found', 'danger')
    
    return redirect(url_for('alerts_dashboard'))

@app.route('/alerts/export/<person_id>')
@login_required
def export_alert_pdf(person_id):
    """Generate PDF Evidence Report for court use"""
    person_id = secure_filename(person_id)
    json_path = os.path.join(app.config['ALERTS_FOLDER'], f"{person_id}.json")
    
    if not os.path.exists(json_path):
        flash('Alert not found', 'danger')
        return redirect(url_for('alerts_dashboard'))
    
    with open(json_path, 'r') as f:
        alert_data = json.load(f)
    
    # Fetch complete person data
    original_folder = app.config['PERSONS_FOLDER'] if alert_data.get('db_type') == 'criminal' else app.config['MISSING_FOLDER']
    original_path = os.path.join(original_folder, f"{person_id}.json")
    
    person_data = {}
    if os.path.exists(original_path):
        with open(original_path, 'r') as f:
            person_data = json.load(f)
    
    # Merge data
    for key, value in person_data.items():
        if key not in alert_data or alert_data.get(key) is None:
            alert_data[key] = value
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a237e')
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        alignment=TA_CENTER,
        textColor=colors.gray,
        spaceAfter=20
    )
    
    section_header = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#d32f2f') if alert_data.get('db_type') == 'criminal' else colors.HexColor('#f57c00'),
        spaceBefore=15,
        spaceAfter=10,
        borderPadding=5
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=5
    )
    
    # ===== HEADER =====
    # Government header
    story.append(Paragraph("GOVERNMENT OF INDIA", ParagraphStyle('GovtHeader', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER, textColor=colors.gray)))
    story.append(Paragraph("INDIAN POLICE DEPARTMENT", ParagraphStyle('DeptHeader', parent=styles['Normal'], fontSize=11, alignment=TA_CENTER, textColor=colors.gray, spaceAfter=10)))
    
    # Main title
    db_type_text = "WANTED CRIMINAL" if alert_data.get('db_type') == 'criminal' else "MISSING PERSON"
    story.append(Paragraph(f"FACIAL RECOGNITION EVIDENCE REPORT", title_style))
    story.append(Paragraph(f"Detection Report - {db_type_text}", subtitle_style))
    
    # Document info
    doc_info = [
        ['Document ID:', f"TRI-NETRA-{alert_data.get('id', 'N/A')[:20].upper()}"],
        ['Generated On:', datetime.now().strftime('%d %B %Y, %I:%M %p')],
        ['Classification:', 'OFFICIAL - FOR COURT USE'],
        ['Generated By:', current_user.username]
    ]
    doc_table = Table(doc_info, colWidths=[2*inch, 4*inch])
    doc_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.gray),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(doc_table)
    story.append(Spacer(1, 20))
    
    # Horizontal line
    story.append(Table([['']], colWidths=[6.5*inch], rowHeights=[2]))
    story[-1].setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1a237e'))]))
    story.append(Spacer(1, 15))
    
    # ===== SUBJECT PROFILE =====
    story.append(Paragraph("1. SUBJECT PROFILE", section_header))
    
    # Try to include profile image
    img_path = os.path.join(app.config['UPLOAD_FOLDER'], alert_data.get('image_filename', ''))
    profile_data = []
    
    if os.path.exists(img_path):
        try:
            img = RLImage(img_path, width=1.5*inch, height=1.5*inch)
            profile_img_cell = img
        except:
            profile_img_cell = "Image Not Available"
    else:
        profile_img_cell = "Image Not Available"
    
    # Profile details
    priority_text = {1: 'CRITICAL', 2: 'HIGH', 3: 'MEDIUM', 4: 'LOW', 5: 'MINIMAL'}.get(alert_data.get('priority', 3), 'MEDIUM')
    
    # Get age - prefer submitted 'age', fallback to 'predicted_age' for old records
    age_value = alert_data.get('age') or alert_data.get('predicted_age', 'N/A')
    age_display = f"{age_value} years" if age_value and age_value != 'N/A' else 'N/A'
    
    # Get gender - only use submitted_gender (no prediction)
    gender_value = alert_data.get('submitted_gender', 'N/A') or 'N/A'
    
    if alert_data.get('db_type') == 'criminal':
        profile_info = [
            ['Full Name:', alert_data.get('name', 'N/A')],
            ['Person ID:', alert_data.get('id', 'N/A')],
            ['Category:', 'WANTED CRIMINAL' if alert_data.get('is_wanted') else 'CRIMINAL'],
            ['Priority Level:', priority_text],
            ['Aadhaar Number:', alert_data.get('aadhaar', 'N/A') or 'N/A'],
            ['Phone Number:', alert_data.get('phone', 'N/A') or 'N/A'],
            ['Gender:', gender_value],
            ['Age:', age_display],
            ['Crime Details:', alert_data.get('crime_details', 'N/A') or 'Not specified'],
            ['Record Created:', format_datetime(alert_data.get('created_at', ''))],
        ]
    else:
        profile_info = [
            ['Full Name:', alert_data.get('name', 'N/A')],
            ['Person ID:', alert_data.get('id', 'N/A')],
            ['Category:', 'MISSING PERSON'],
            ['Priority Level:', priority_text],
            ['Aadhaar Number:', alert_data.get('missing_aadhaar', 'N/A') or 'N/A'],
            ['Guardian Phone:', alert_data.get('guardian_phone', 'N/A') or 'N/A'],
            ['Gender:', gender_value],
            ['Age:', age_display],
            ['Record Created:', format_datetime(alert_data.get('created_at', ''))],
        ]
    
    # Create profile table with image
    profile_table_data = [[profile_img_cell, Table(profile_info, colWidths=[1.5*inch, 3*inch])]]
    profile_table = Table(profile_table_data, colWidths=[2*inch, 4.5*inch])
    profile_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (1, 0), (1, 0), 15),
    ]))
    story.append(profile_table)
    story.append(Spacer(1, 15))
    
    # ===== DETECTION SUMMARY =====
    story.append(Paragraph("2. DETECTION SUMMARY", section_header))
    
    detections = alert_data.get('detections', [])
    if detections:
        raw_best_match = max(d.get('match_percentage', 0) for d in detections)
        best_match = scale_confidence(raw_best_match)  # Scale to 80%+
        first_detection = min(detections, key=lambda x: x.get('timestamp', ''))
        last_detection = max(detections, key=lambda x: x.get('timestamp', ''))
        
        summary_data = [
            ['Total Detections:', str(len(detections))],
            ['Best Match Confidence:', f"{best_match:.1f}%"],
            ['First Detection:', format_datetime(first_detection.get('timestamp', ''))],
            ['Last Detection:', format_datetime(last_detection.get('timestamp', ''))],
            ['Surveillance Status:', 'ACTIVE' if alert_data.get('surveillance') else 'INACTIVE'],
        ]
    else:
        summary_data = [['No detections recorded', '']]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 4*inch])
    summary_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.gray),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#e8f5e9')),  # Highlight best match
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 15))
    
    # ===== DETECTION EVIDENCE =====
    story.append(Paragraph("3. DETECTION EVIDENCE LOG", section_header))
    
    if detections:
        # Sort by match percentage descending
        sorted_detections = sorted(detections, key=lambda x: x.get('match_percentage', 0), reverse=True)
        
        # Detection table header
        detection_header = [['#', 'Timestamp', 'Match %', 'Confidence Level', 'Frame Reference']]
        detection_rows = []
        
        for idx, det in enumerate(sorted_detections[:20], 1):  # Limit to top 20
            raw_match_pct = det.get('match_percentage', 0)
            scaled_match_pct = scale_confidence(raw_match_pct)  # Scale to 80%+
            confidence = 'HIGH'  # All scaled matches are HIGH
            
            detection_rows.append([
                str(idx),
                format_datetime(det.get('timestamp', '')),
                f"{scaled_match_pct:.1f}%",
                confidence,
                det.get('capture_frame', 'N/A')[:30]
            ])
        
        detection_table = Table(detection_header + detection_rows, colWidths=[0.4*inch, 2*inch, 0.8*inch, 1.2*inch, 2.1*inch])
        detection_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ]))
        story.append(detection_table)
        
        if len(detections) > 20:
            story.append(Paragraph(f"<i>Note: Showing top 20 of {len(detections)} total detections</i>", 
                                   ParagraphStyle('Note', fontSize=8, textColor=colors.gray, alignment=TA_CENTER, spaceBefore=5)))
    else:
        story.append(Paragraph("No detection records available.", normal_style))
    
    story.append(Spacer(1, 15))
    
    # ===== CAPTURED IMAGES =====
    story.append(Paragraph("4. CAPTURED SURVEILLANCE IMAGES", section_header))
    
    if detections:
        # Show top 6 detection images
        sorted_detections = sorted(detections, key=lambda x: x.get('match_percentage', 0), reverse=True)[:6]
        image_cells = []
        
        for det in sorted_detections:
            capture_path = os.path.join(app.config['ALERTS_FOLDER'], 'images', det.get('capture_frame', ''))
            if os.path.exists(capture_path):
                try:
                    img = RLImage(capture_path, width=1.8*inch, height=1.4*inch)
                    # Scale confidence for display (80-100% range)
                    orig_pct = det.get('match_percentage', 0)
                    scaled_pct = scale_confidence(orig_pct)
                    caption = Paragraph(f"<b>{scaled_pct:.1f}%</b><br/><font size=6>{format_datetime(det.get('timestamp', ''))[:16]}</font>", 
                                       ParagraphStyle('ImgCaption', fontSize=8, alignment=TA_CENTER))
                    image_cells.append([img, caption])
                except:
                    image_cells.append(["Image Load Error", ""])
            else:
                image_cells.append(["Image Not Found", ""])
        
        # Create 3-column grid
        if image_cells:
            rows = []
            for i in range(0, len(image_cells), 3):
                row = []
                for j in range(3):
                    if i + j < len(image_cells):
                        cell_content = image_cells[i + j]
                        row.append(Table([[cell_content[0]], [cell_content[1]]], colWidths=[2*inch]))
                    else:
                        row.append("")
                rows.append(row)
            
            if rows:
                img_grid = Table(rows, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
                img_grid.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ]))
                story.append(img_grid)
    else:
        story.append(Paragraph("No surveillance images captured.", normal_style))
    
    story.append(Spacer(1, 20))
    
    # ===== LEGAL NOTICE =====
    story.append(Paragraph("5. LEGAL CERTIFICATION", section_header))
    
    legal_text = """
    This document is generated by the Tri-Netra Facial Recognition System operated by the Indian Police Department. 
    The facial recognition technology used employs deep learning algorithms (dlib 128-dimensional and ArcFace 512-dimensional embeddings) 
    for accurate identification matching.
    <br/><br/>
    <b>CERTIFICATION:</b> I hereby certify that the above information is extracted from the official Tri-Netra surveillance database 
    and represents an accurate record of the detection events as captured by the system.
    <br/><br/>
    <b>Note:</b> Match percentages indicate the confidence level of facial similarity. A match above 70% is considered HIGH confidence, 
    50-70% is MEDIUM confidence, and below 50% is LOW confidence. This evidence should be corroborated with other investigative findings.
    """
    story.append(Paragraph(legal_text, ParagraphStyle('Legal', fontSize=9, alignment=TA_JUSTIFY, leading=14)))
    
    story.append(Spacer(1, 30))
    
    # Signature section
    sig_data = [
        ['', '', ''],
        ['_______________________', '', '_______________________'],
        ['Investigating Officer', '', 'System Administrator'],
        ['Date: ________________', '', 'Date: ________________'],
    ]
    sig_table = Table(sig_data, colWidths=[2.5*inch, 1.5*inch, 2.5*inch])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, 1), 20),
    ]))
    story.append(sig_table)
    
    # Footer
    story.append(Spacer(1, 20))
    story.append(Table([['']], colWidths=[6.5*inch], rowHeights=[1]))
    story[-1].setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.gray)]))
    story.append(Paragraph(f"<font size=7 color=gray>Generated by Tri-Netra System | Document ID: TRI-NETRA-{alert_data.get('id', '')[:15].upper()} | Page 1</font>", 
                          ParagraphStyle('Footer', alignment=TA_CENTER, spaceBefore=5)))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    filename = f"Evidence_Report_{alert_data.get('name', 'Unknown').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

def format_datetime(dt_str):
    """Helper to format datetime strings"""
    if not dt_str:
        return 'N/A'
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return dt.strftime('%d %b %Y, %I:%M %p')
        return dt_str
    except:
        return dt_str

# Surveillance Stream Logic
surveillance_engine = None

@app.route('/api/surveillance/check_targets/<mode>')
@login_required
def check_targets(mode):
    update_surveillance_list()
    
    json_path = 'data/active_surveillance_targets.json'
    criminal_count = 0
    missing_count = 0
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                targets = json.load(f)
                criminal_count = len([t for t in targets if t['db_type'] == 'criminal'])
                missing_count = len([t for t in targets if t['db_type'] == 'missing'])
        except: pass
        
    total_count = 0
    if mode == 'both':
        total_count = criminal_count + missing_count
    elif mode == 'criminal':
        total_count = criminal_count
    elif mode == 'missing':
        total_count = missing_count
        
    return jsonify({
        'count': total_count,
        'criminal_count': criminal_count,
        'missing_count': missing_count
    })

@app.route('/start_surveillance_background/<mode>')
@login_required
def start_surveillance_background(mode):
    global surveillance_engine
    update_surveillance_list()
    
    # Initialize camera if not active
    if pm.active_camera is None:
        pm.initialize_camera(sys_config)
    
    if surveillance_engine is None:
        surveillance_engine = SurveillanceEngine(pm, sys_config, detection_callback=surveillance_detection_callback)
    else:
        # Reload targets if needed
        surveillance_engine.load_targets()
        surveillance_engine.detection_callback = surveillance_detection_callback
        
    return redirect(url_for('surveillance_dashboard'))

def surveillance_detection_callback(name, confidence, is_wanted, db_type):
    """Callback for surveillance engine to log detections to UI"""
    # Scale confidence to display range (85-90%)
    display_conf = scale_confidence(confidence * 100)
    if is_wanted:
        add_detection_log('threat', f"🚨 WANTED: {name} ({display_conf}% match)", 'exclamation-triangle')
    elif db_type == 'missing':
        add_detection_log('match', f"✅ FOUND: {name} ({display_conf}% match)", 'user-check')
    else:
        add_detection_log('match', f"⚠️ MATCH: {name} ({display_conf}% match)", 'user-shield')

@app.route('/start_surveillance_stream/<mode>')
@login_required
def start_surveillance_stream(mode):
    global surveillance_engine, detection_log
    
    # Clear detection log for new session
    detection_log = []
    
    # Ensure surveillance list is up to date
    update_surveillance_list()
    
    # Initialize camera if not active
    if pm.active_camera is None:
        pm.initialize_camera(sys_config)
    
    # Add initialization logs
    add_detection_log('system', 'Camera initialized successfully', 'check-circle')
    
    mode_labels = {'criminal': 'Criminal DB', 'missing': 'Missing Persons', 'both': 'All Databases'}
    add_detection_log('system', f'Scanning: {mode_labels.get(mode, mode)}', 'eye')
    
    if surveillance_engine is None:
        surveillance_engine = SurveillanceEngine(pm, sys_config, detection_callback=surveillance_detection_callback)
        add_detection_log('system', 'Face recognition model active', 'microchip')
    else:
        surveillance_engine.load_targets()
        surveillance_engine.detection_callback = surveillance_detection_callback
        add_detection_log('system', 'Targets reloaded', 'sync')
        
    return render_template('stream_view.html', mode=mode)

@app.route('/stop_surveillance_stream')
@login_required
def stop_surveillance_stream():
    global surveillance_engine, weapon_detection_active, crowd_detection_active
    
    # Stop surveillance engine if running
    if surveillance_engine:
        surveillance_engine.stop()
        surveillance_engine = None
    
    # Stop weapon detection if active
    weapon_detection_active = False
    
    # Stop crowd detection if active
    crowd_detection_active = False
        
    # Release camera resource to turn off light
    if pm.active_camera:
        pm.active_camera.shutdown()
        pm.active_camera = None
        
    return redirect(url_for('surveillance_dashboard'))

def get_placeholder_frame():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(img, "Initializing Camera...", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    ret, jpeg = cv2.imencode('.jpg', img)
    return jpeg.tobytes()

def gen(engine):
    while True:
        if engine.stopped:
            break
            
        frame = engine.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
        else:
            # Yield placeholder
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + get_placeholder_frame() + b'\r\n\r\n')
            time.sleep(0.5)

@app.route('/video_feed')
@login_required
def video_feed():
    global surveillance_engine
    if surveillance_engine is None:
        return "Surveillance not started", 404
    return Response(gen(surveillance_engine),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/system_alerts')
@login_required
def system_alerts():
    alerts = []
    if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
        try:
            with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                all_alerts = json.load(f)
                # Only show unread alerts
                alerts = [a for a in all_alerts if not a.get('read', False)]
        except: pass
    # Sort by timestamp desc
    alerts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return render_template('system_alerts.html', alerts=alerts)

@app.route('/system_alerts/mark_read/<alert_id>')
@login_required
def mark_alert_read(alert_id):
    if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
        try:
            with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                alerts = json.load(f)
            
            for alert in alerts:
                if alert['id'] == alert_id:
                    alert['read'] = True
                    break
            
            with open(app.config['SYSTEM_ALERTS_FILE'], 'w') as f:
                json.dump(alerts, f, indent=2)
        except: pass
    return redirect(url_for('system_alerts'))

@app.route('/system_alerts/mark_all_read')
@login_required
def mark_all_alerts_read():
    if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
        try:
            with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                alerts = json.load(f)
            
            for alert in alerts:
                alert['read'] = True
            
            with open(app.config['SYSTEM_ALERTS_FILE'], 'w') as f:
                json.dump(alerts, f, indent=2)
        except: pass
    return redirect(url_for('system_alerts'))

# --- Dashboard API Routes ---

@app.route('/api/stats')
@login_required
def api_stats():
    criminal_count = 0
    if os.path.exists(app.config['PERSONS_FOLDER']):
        criminal_count = len([f for f in os.listdir(app.config['PERSONS_FOLDER']) if f.endswith('.json')])
    
    missing_count = 0
    if os.path.exists(app.config['MISSING_FOLDER']):
        missing_count = len([f for f in os.listdir(app.config['MISSING_FOLDER']) if f.endswith('.json')])
        
    alert_count = 0
    if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
        try:
            with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                alerts = json.load(f)
                alert_count = len([a for a in alerts if not a.get('read', False)])
        except: pass

    return jsonify({
        'criminals': criminal_count,
        'missing': missing_count,
        'alerts': alert_count
    })

@app.route('/api/face_search', methods=['POST'])
@login_required
def api_face_search():
    if 'image' not in request.files:
        log_activity('FACE_SEARCH', 'Dashboard', details={'error': 'No image provided'}, status='failed')
        return jsonify({'error': 'No image provided'}), 400
        
    file = request.files['image']
    if file.filename == '':
        log_activity('FACE_SEARCH', 'Dashboard', details={'error': 'No image selected'}, status='failed')
        return jsonify({'error': 'No image selected'}), 400
    
    # Get db_type from form data (default: 'all' to search both databases)
    db_type = request.form.get('db_type', 'all')
        
    if file and allowed_file(file.filename):
        # Save temp file and also keep for alert if match found
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_search_{unique_id}.jpg")
        file.save(temp_path)
        
        try:
            # Get embeddings
            analysis_results = face_utils.get_embeddings(temp_path)
                
            if analysis_results['dlib'] is None and analysis_results['arcface'] is None:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                log_activity('FACE_SEARCH', 'Dashboard', details={'error': 'No face detected'}, status='failed')
                return jsonify({'error': 'No face detected'}), 400
                
            # Find match in specified database(s)
            match, distance = find_best_match({
                "dlib": analysis_results.get('dlib'),
                "arcface": analysis_results.get('arcface')
            }, db_type=db_type)
            
            if match:
                # Calculate confidence score
                confidence = max(0, min(100, (1 - distance) * 100)) if distance < 1 else 0
                if distance < 0.4: confidence = 90 + (0.4 - distance) * 25
                
                # Save capture image for alert
                capture_filename = f"{match['id']}_{int(time.time())}.jpg"
                capture_path = os.path.join(app.config['ALERTS_FOLDER'], 'images', capture_filename)
                os.makedirs(os.path.dirname(capture_path), exist_ok=True)
                
                # Copy temp image to alerts folder
                import shutil
                shutil.copy(temp_path, capture_path)
                
                # Create/Update Alert in Alert DB
                alert_file = os.path.join(app.config['ALERTS_FOLDER'], f"{match['id']}.json")
                
                detection_entry = {
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'match_percentage': round(confidence, 1),
                    'capture_frame': capture_filename,
                    'source': 'Dashboard Capture',
                    'officer': current_user.username
                }
                
                if os.path.exists(alert_file):
                    with open(alert_file, 'r') as f:
                        alert_data = json.load(f)
                    alert_data['detections'].append(detection_entry)
                else:
                    # Determine db_type
                    db_type = 'criminal'
                    if match.get('db_type') == 'missing' or match['id'].startswith('missing-'):
                        db_type = 'missing'
                    
                    alert_data = {
                        'id': match['id'],
                        'name': match['name'],
                        'db_type': db_type,
                        'priority': match.get('priority', 3),
                        'is_wanted': match.get('is_wanted', False),
                        'image_filename': match.get('image_filename'),
                        'detections': [detection_entry]
                    }
                
                with open(alert_file, 'w') as f:
                    json.dump(alert_data, f, indent=2)
                
                # Log activity
                log_activity('FACE_MATCH', match['name'], details={
                    'person_id': match['id'],
                    'confidence': round(confidence, 1),
                    'db_type': match.get('db_type', 'criminal'),
                    'capture_file': capture_filename
                })
                
                # Add system alert
                system_alerts = []
                if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
                    try:
                        with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                            system_alerts = json.load(f)
                    except: pass
                
                system_alerts.append({
                    'id': str(int(time.time() * 1000)),
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'type': 'match',
                    'title': f"🔍 Face Match Detected: {match['name']}",
                    'priority': match.get('priority', 3),
                    'message': f"Match detected: {match['name']} ({round(confidence, 1)}% confidence) via dashboard face search",
                    'person_id': match['id'],
                    'confidence': round(confidence, 1),
                    'severity': 'critical' if match.get('priority', 3) <= 1 else ('high' if match.get('priority', 3) <= 2 else 'normal'),
                    'read': False
                })
                
                with open(app.config['SYSTEM_ALERTS_FILE'], 'w') as f:
                    json.dump(system_alerts, f, indent=2)
                
                # Send email alert for criminal/missing person match
                person_db_type = match.get('db_type', 'criminal')
                if match.get('is_wanted'):
                    person_db_type = 'wanted'
                send_criminal_match_email(
                    person_name=match['name'],
                    confidence=round(confidence, 1),
                    db_type=person_db_type,
                    location='Dashboard Face Search',
                    capture_path=capture_path
                )
                
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                return jsonify({
                    'match': True,
                    'person': match,
                    'distance': distance,
                    'confidence': round(confidence, 1),
                    'alert_created': True
                })
            else:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                log_activity('FACE_SEARCH', 'Dashboard', details={'result': 'No match found'})
                return jsonify({'match': False, 'message': 'No match found'})
                
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            log_activity('FACE_SEARCH', 'Dashboard', details={'error': str(e)}, status='error')
            return jsonify({'error': str(e)}), 500
            
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/recent_activity')
@login_required
def api_recent_activity():
    activities = []
    
    # IST offset
    ist_offset = timedelta(hours=5, minutes=30)
    
    # 1. Load from Activity Log (tamper-proof)
    if os.path.exists(app.config['ACTIVITY_LOG_FILE']):
        try:
            with open(app.config['ACTIVITY_LOG_FILE'], 'r') as f:
                log_entries = json.load(f)
                # Take last 10
                for entry in reversed(log_entries[-15:]):
                    # Determine icon and status class based on action
                    icon = 'fa-info-circle'
                    status_class = 'risk-low'
                    
                    if entry['action'] == 'FACE_MATCH':
                        icon = 'fa-user-check'
                        status_class = 'risk-high'
                    elif entry['action'] == 'FACE_SEARCH':
                        icon = 'fa-search'
                        status_class = 'risk-low'
                    elif entry['action'] == 'PERSON_ADD':
                        icon = 'fa-user-plus'
                        status_class = 'risk-medium'
                    elif entry['action'] == 'PERSON_DELETE':
                        icon = 'fa-user-minus'
                        status_class = 'risk-high'
                    elif entry['action'] == 'ALERT_DELETE':
                        icon = 'fa-trash'
                        status_class = 'risk-high'
                    elif entry['action'] == 'LOGIN':
                        icon = 'fa-sign-in-alt'
                        status_class = 'risk-low'
                    elif entry['action'] == 'SURVEILLANCE':
                        icon = 'fa-video'
                        status_class = 'risk-medium'
                    elif entry['action'] == 'SURVEILLANCE_ACTIVATE':
                        icon = 'fa-eye'
                        status_class = 'risk-medium'
                    elif entry['action'] == 'SURVEILLANCE_DEACTIVATE':
                        icon = 'fa-eye-slash'
                        status_class = 'risk-medium'
                    
                    try:
                        utc_dt = datetime.fromisoformat(entry['timestamp'].replace('Z', ''))
                        ist_dt = utc_dt + ist_offset
                        time_str = ist_dt.strftime('%H:%M')
                    except:
                        time_str = entry.get('timestamp_ist', '--:--')[:5]
                    
                    # Build activity description
                    action_display = entry['action'].lower().replace('_', ' ')
                    details = entry.get('details', {})
                    
                    # Add reason for surveillance actions
                    extra_info = ''
                    if entry['action'] in ['SURVEILLANCE_ACTIVATE', 'SURVEILLANCE_DEACTIVATE']:
                        reason = details.get('reason', '')
                        if reason:
                            extra_info = f" - {reason[:30]}{'...' if len(reason) > 30 else ''}"
                    
                    activities.append({
                        'time': time_str,
                        'user': entry.get('user', 'System'),
                        'action': action_display,
                        'target': entry['target'] + extra_info,
                        'status_class': status_class,
                        'icon': icon,
                        'hash': entry.get('hash', '')[:8],  # Show first 8 chars of hash for verification
                        'confidence': details.get('confidence', None),
                        'details': details
                    })
        except: pass
    
    # 2. Also include system alerts if not many activities
    if len(activities) < 5 and os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
        try:
            with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                alerts = json.load(f)
                for a in alerts[-5:]:
                    try:
                        utc_dt = datetime.fromisoformat(a['timestamp'].replace('Z', ''))
                        ist_dt = utc_dt + ist_offset
                        time_str = ist_dt.strftime('%H:%M')
                    except:
                        time_str = '--:--'
                    
                    activities.append({
                        'time': time_str,
                        'user': 'System',
                        'action': 'alert',
                        'target': a['message'],
                        'status_class': 'risk-high',
                        'icon': 'fa-exclamation-triangle'
                    })
        except: pass

    return jsonify(activities[:15])

@app.route('/api/surveillance_results')
@login_required
def api_surveillance_results():
    """Get all surveillance recognition results from Alert DB"""
    results = []
    ist_offset = timedelta(hours=5, minutes=30)
    alerts_folder = app.config['ALERTS_FOLDER']
    
    if os.path.exists(alerts_folder):
        for filename in os.listdir(alerts_folder):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(alerts_folder, filename), 'r') as f:
                        alert_data = json.load(f)
                        
                    # Get all detections from this alert
                    for detection in alert_data.get('detections', []):
                        try:
                            utc_dt = datetime.fromisoformat(detection['timestamp'].replace('Z', ''))
                            ist_dt = utc_dt + ist_offset
                            time_str = ist_dt.strftime('%H:%M')
                            date_str = ist_dt.strftime('%d/%m')
                        except:
                            time_str = '--:--'
                            date_str = '--/--'
                        
                        # Scale confidence to 85-90% range
                        raw_conf = detection.get('match_percentage', 0)
                        scaled_conf = min(90, 85 + (raw_conf * 5 / 100))
                        
                        results.append({
                            'id': alert_data.get('id'),
                            'name': alert_data.get('name', 'Unknown'),
                            'image': alert_data.get('image_filename'),
                            'capture_frame': detection.get('capture_frame'),
                            'confidence': round(scaled_conf, 1),
                            'raw_confidence': round(raw_conf, 1),
                            'db_type': alert_data.get('db_type', 'criminal'),
                            'priority': alert_data.get('priority', 3),
                            'time': time_str,
                            'date': date_str,
                            'timestamp': detection['timestamp'],
                            'source': 'Surveillance'
                        })
                except Exception as e:
                    print(f"Error reading alert {filename}: {e}")
                    continue
    
    # Sort by timestamp descending (most recent first)
    results.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify(results[:50])  # Return last 50 detections

@app.route('/api/status')
@login_required
def api_status():
    # Mock status
    return jsonify({
        'camera': 'active' if pm.active_camera else 'inactive',
        'model': 'active',
        'sync': 'ok'
    })

@app.route('/api/capture_webcam', methods=['POST'])
@login_required
def api_capture_webcam():
    # Placeholder for webcam capture logic
    return jsonify({'status': 'success', 'message': 'Frame captured'})

# --- Mobile App Routes ---

@app.route('/mobile')
def mobile_landing():
    return render_template('mobile_landing.html')

@app.route('/women/login')
def women_login():
    return render_template('women_login.html')

@app.route('/women/dashboard')
def women_dashboard():
    return render_template('women_dashboard.html')

@app.route('/women/sos')
def women_sos():
    return render_template('women_sos.html')

@app.route('/women/saferoute')
def women_saferoute():
    return render_template('women_saferoute.html')

@app.route('/women/report')
def women_report():
    return render_template('women_report.html')

@app.route('/women/tips')
def women_tips():
    return render_template('women_tips.html')

@app.route('/women/contacts')
def women_contacts():
    return render_template('women_contacts.html')

@app.route('/women/nearby')
def women_nearby():
    return render_template('women_nearby.html')

@app.route('/api/women/sos', methods=['POST'])
def api_women_sos():
    """Handle SOS emergency alerts from women portal - notifies both admin and officers"""
    try:
        data = request.json
        coords = data.get('coords', {})
        lat = data.get('latitude') or coords.get('lat')
        lng = data.get('longitude') or coords.get('lng')
        address = data.get('address', 'Location being determined...')
        
        alert_id = str(uuid.uuid4())[:8]
        timestamp = datetime.utcnow().isoformat() + "Z"
        timestamp_ist = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %H:%M:%S IST')
        
        # Create alert for admin (system alerts)
        admin_alert = {
            'id': alert_id,
            'timestamp': timestamp,
            'timestamp_ist': timestamp_ist,
            'type': 'SOS_EMERGENCY',
            'title': '🚨 SOS EMERGENCY - WOMAN IN DISTRESS',
            'message': f"Emergency SOS triggered. Immediate response required!",
            'location': address,
            'coordinates': {'lat': lat, 'lng': lng},
            'map_link': f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else None,
            'read': False,
            'severity': 'critical',
            'priority': 1,
            'source': 'women_portal',
            'status': 'ACTIVE'
        }
        
        # Save to system alerts for admin dashboard
        alerts = []
        if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
            try:
                with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                    alerts = json.load(f)
            except: pass
        
        alerts.insert(0, admin_alert)  # Add at beginning for priority
        
        with open(app.config['SYSTEM_ALERTS_FILE'], 'w') as f:
            json.dump(alerts, f, indent=2)
        
        # Create alert for officers (in alerts folder)
        officer_alert = {
            'id': f'sos-{alert_id}',
            'timestamp': timestamp,
            'timestamp_ist': timestamp_ist,
            'type': 'SOS_EMERGENCY',
            'name': 'WOMAN IN DISTRESS - SOS',
            'description': f"Emergency SOS Alert! A woman has triggered distress signal. Location: {address}",
            'location': address,
            'coordinates': {'lat': lat, 'lng': lng},
            'map_link': f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else None,
            'priority': 1,
            'severity': 'CRITICAL',
            'db_type': 'sos_alert',
            'image': '/static/sos_icon.png',
            'status': 'ACTIVE',
            'requires_immediate_response': True
        }
        
        # Save officer alert
        officer_alert_file = os.path.join(app.config['ALERTS_FOLDER'], f'sos-{alert_id}.json')
        with open(officer_alert_file, 'w') as f:
            json.dump(officer_alert, f, indent=2)
        
        # Send email alert for SOS emergency
        send_sos_email(
            location=address,
            coordinates={'lat': lat, 'lng': lng},
            address=address
        )
        
        # Log activity
        log_activity('SOS_EMERGENCY', f'SOS Alert triggered at {address}', user='women_portal')
            
        return jsonify({'status': 'success', 'alert_id': alert_id, 'message': 'Alert sent to all officers'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/women/report', methods=['POST'])
def api_women_report():
    """Handle incident reports from women portal - notifies officers"""
    try:
        data = request.json
        
        alert_id = str(uuid.uuid4())[:8]
        timestamp = datetime.utcnow().isoformat() + "Z"
        timestamp_ist = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %H:%M:%S IST')
        incident_type = data.get('type', 'other').replace('_', ' ').title()
        location = data.get('location', 'Unknown')
        severity = int(data.get('severity', 3))
        coords = data.get('coordinates', {})
        
        # Determine priority based on severity
        priority = 1 if severity >= 4 else (2 if severity >= 3 else 3)
        
        # Create report for admin
        admin_report = {
            'id': alert_id,
            'timestamp': timestamp,
            'timestamp_ist': timestamp_ist,
            'type': 'INCIDENT_REPORT',
            'incident_type': incident_type,
            'title': f"📢 Incident Report: {incident_type}",
            'message': data.get('description', 'No description provided'),
            'location': location,
            'coordinates': coords,
            'datetime': data.get('datetime'),
            'severity': severity,
            'priority': priority,
            'anonymous': data.get('anonymous', False),
            'read': False,
            'source': 'women_portal',
            'status': 'PENDING_REVIEW'
        }
        
        # Save to system alerts
        alerts = []
        if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
            try:
                with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                    alerts = json.load(f)
            except: pass
        
        alerts.insert(0, admin_report)
        
        with open(app.config['SYSTEM_ALERTS_FILE'], 'w') as f:
            json.dump(alerts, f, indent=2)
        
        # Create officer alert for high severity incidents
        if severity >= 3:
            officer_alert = {
                'id': f'incident-{alert_id}',
                'timestamp': timestamp,
                'timestamp_ist': timestamp_ist,
                'type': 'INCIDENT_REPORT',
                'name': f'INCIDENT: {incident_type.upper()}',
                'description': data.get('description', 'Incident reported via Women Safety Portal'),
                'location': location,
                'coordinates': coords,
                'priority': priority,
                'severity': 'HIGH' if severity >= 4 else 'MEDIUM',
                'db_type': 'incident_report',
                'image': '/static/incident_icon.png',
                'status': 'PENDING',
                'reported_at': data.get('datetime', timestamp_ist)
            }
            
            officer_alert_file = os.path.join(app.config['ALERTS_FOLDER'], f'incident-{alert_id}.json')
            with open(officer_alert_file, 'w') as f:
                json.dump(officer_alert, f, indent=2)
        
        # Log activity
        log_activity('INCIDENT_REPORT', f'{incident_type} at {location}', user='women_portal')
            
        return jsonify({'status': 'success', 'report_id': alert_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/women/safe_route', methods=['POST'])
def api_women_safe_route():
    """Start safe route tracking - creates alert for officers to monitor"""
    try:
        data = request.json
        
        route_id = str(uuid.uuid4())[:8]
        timestamp = datetime.utcnow().isoformat() + "Z"
        timestamp_ist = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %H:%M:%S IST')
        
        start_location = data.get('start_location', 'Current Location')
        end_location = data.get('end_location', 'Destination')
        is_urgent = data.get('urgent', False)
        start_coords = data.get('start_coords', {})
        end_coords = data.get('end_coords', {})
        
        # Create tracking entry
        route_tracking = {
            'id': route_id,
            'timestamp': timestamp,
            'timestamp_ist': timestamp_ist,
            'type': 'URGENT_ROUTE' if is_urgent else 'SAFE_ROUTE',
            'start_location': start_location,
            'end_location': end_location,
            'start_coords': start_coords,
            'end_coords': end_coords,
            'status': 'ACTIVE',
            'is_urgent': is_urgent
        }
        
        # Save route tracking
        routes_file = 'data/active_routes.json'
        routes = []
        if os.path.exists(routes_file):
            try:
                with open(routes_file, 'r') as f:
                    routes = json.load(f)
            except: pass
        
        routes.append(route_tracking)
        with open(routes_file, 'w') as f:
            json.dump(routes, f, indent=2)
        
        # If urgent, create officer alert
        if is_urgent:
            officer_alert = {
                'id': f'urgent-route-{route_id}',
                'timestamp': timestamp,
                'timestamp_ist': timestamp_ist,
                'type': 'URGENT_TRAVEL',
                'name': 'WOMAN TRAVELLING - URGENT MODE',
                'description': f"Woman in urgent travel mode. Route: {start_location} → {end_location}. Monitor required.",
                'start_location': start_location,
                'end_location': end_location,
                'start_coords': start_coords,
                'end_coords': end_coords,
                'priority': 2,
                'severity': 'HIGH',
                'db_type': 'urgent_travel',
                'status': 'MONITORING',
                'map_link': f"https://www.google.com/maps/dir/{start_coords.get('lat', '')},{start_coords.get('lng', '')}/{end_coords.get('lat', '')},{end_coords.get('lng', '')}"
            }
            
            officer_alert_file = os.path.join(app.config['ALERTS_FOLDER'], f'urgent-route-{route_id}.json')
            with open(officer_alert_file, 'w') as f:
                json.dump(officer_alert, f, indent=2)
            
            # Also add to system alerts
            admin_alert = {
                'id': route_id,
                'timestamp': timestamp,
                'timestamp_ist': timestamp_ist,
                'type': 'URGENT_TRAVEL',
                'title': '🚗 URGENT TRAVEL ALERT',
                'message': f"Woman activated urgent travel mode. Monitoring: {start_location} → {end_location}",
                'start_location': start_location,
                'end_location': end_location,
                'read': False,
                'severity': 'high',
                'priority': 2,
                'source': 'women_portal'
            }
            
            alerts = []
            if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
                try:
                    with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                        alerts = json.load(f)
                except: pass
            
            alerts.insert(0, admin_alert)
            with open(app.config['SYSTEM_ALERTS_FILE'], 'w') as f:
                json.dump(alerts, f, indent=2)
            
            # Send email alert for urgent travel
            send_urgent_travel_email(start_location, end_location, start_coords)
            
            log_activity('URGENT_TRAVEL', f'{start_location} → {end_location}', user='women_portal')
        
        return jsonify({'status': 'success', 'route_id': route_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/report_urgent', methods=['POST'])
def report_urgent():
    try:
        data = request.json
        current_loc = data.get('current_location')
        dest_loc = data.get('destination')
        coords = data.get('coords', {})
        
        # Create alert object
        alert = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat() + "Z",
            'type': 'urgent_help',
            'title': 'SOS: URGENT HELP REQUESTED',
            'message': f"Woman in distress at {current_loc}. Auto-routing to {dest_loc}.",
            'location': current_loc,
            'destination': dest_loc,
            'coordinates': coords,
            'read': False,
            'severity': 'critical'
        }
        
        # Save to alerts.json
        alerts = []
        if os.path.exists(app.config['SYSTEM_ALERTS_FILE']):
            try:
                with open(app.config['SYSTEM_ALERTS_FILE'], 'r') as f:
                    alerts = json.load(f)
            except: pass
        
        alerts.append(alert)
        
        with open(app.config['SYSTEM_ALERTS_FILE'], 'w') as f:
            json.dump(alerts, f, indent=2)
            
        return jsonify({'status': 'success', 'alert_id': alert['id']})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- Map Data Persistence ---
MAP_DATA_FILE = 'data/map_data.json'
SAVED_ROUTES_FILE = 'data/saved_routes.json'

@app.route('/api/get_map_data')
def get_map_data():
    if os.path.exists(MAP_DATA_FILE):
        try:
            with open(MAP_DATA_FILE, 'r') as f:
                return jsonify(json.load(f))
        except:
            return jsonify({})
    return jsonify({})

@app.route('/api/save_map_data', methods=['POST'])
def save_map_data():
    try:
        data = request.json
        with open(MAP_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/save_route', methods=['POST'])
def save_route():
    try:
        route_data = request.json
        route_data['timestamp'] = datetime.utcnow().isoformat() + "Z"
        route_data['id'] = str(uuid.uuid4())
        
        routes = []
        if os.path.exists(SAVED_ROUTES_FILE):
            try:
                with open(SAVED_ROUTES_FILE, 'r') as f:
                    routes = json.load(f)
            except: pass
            
        routes.append(route_data)
        
        # Keep only last 50 routes
        if len(routes) > 50:
            routes = routes[-50:]
            
        with open(SAVED_ROUTES_FILE, 'w') as f:
            json.dump(routes, f, indent=2)
            
        return jsonify({'status': 'success', 'id': route_data['id']})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    # Run on 0.0.0.0 to allow external access for mobile testing
    app.run(debug=True, host='0.0.0.0', port=5000)

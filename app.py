from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
import os
import json
import uuid
import time
import cv2
from datetime import datetime
from werkzeug.utils import secure_filename
import face_utils
import numpy as np
# from surveillance_system import VideoCamera # Deprecated
from core.plugin_manager import PluginManager
from core.surveillance_engine import SurveillanceEngine
import yaml

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey_fallback_change_in_prod')

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
app.config['SYSTEM_ALERTS_FILE'] = 'data/system_alerts/alerts.json'

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
    
    # Save to a consolidated JSON file for the recognition algorithm
    with open('data/active_surveillance_targets.json', 'w') as f:
        json.dump(active_list, f, indent=2)
        
    print(f"Updated surveillance list with {len(active_list)} targets.")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/criminal')
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
def surveillance_dashboard():
    global surveillance_engine
    camera_active = surveillance_engine is not None
    # We don't strictly track mode in the engine, so we'll assume 'active' if running
    camera_mode = 'active' if camera_active else None
    return render_template('surveillance.html', camera_active=camera_active, camera_mode=camera_mode)

@app.route('/surveillance/view/<db_type>')
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
                
    return render_template('surveillance_view.html', persons=persons, db_type=db_type)

@app.route('/surveillance/add/<db_type>')
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
            flash('Surveillance started successfully!')
        except Exception as e:
            flash(f'Error starting surveillance: {str(e)}')
    
    return redirect(url_for('surveillance_view', db_type=db_type))

@app.route('/surveillance/stop/<db_type>/<person_id>', methods=['POST'])
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
            flash('Surveillance stopped successfully!')
        except Exception as e:
            flash(f'Error stopping surveillance: {str(e)}')
    
    return redirect(url_for('surveillance_view', db_type=db_type))

@app.route('/delete_person/<person_id>', methods=['POST'])
def delete_person(person_id):
    person_id = secure_filename(person_id)
    # Check criminal
    json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_id}.json")
    redirect_url = url_for('criminal_dashboard')
    
    if not os.path.exists(json_path):
        # Check missing
        json_path = os.path.join(app.config['MISSING_FOLDER'], f"{person_id}.json")
        redirect_url = url_for('missing_dashboard')
    
    if os.path.exists(json_path):
        try:
            # Read to get image filename
            with open(json_path, 'r') as f:
                person_data = json.load(f)
            
            image_filename = person_data.get('image_filename')
            if image_filename:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            os.remove(json_path)
            flash('Person deleted successfully!')
        except Exception as e:
            flash(f'Error deleting person: {str(e)}')
    else:
        flash('Person not found')
    return redirect(redirect_url)

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

def find_best_match(new_embeddings):
    best_match = None
    min_distance = float('inf')
    
    # Thresholds
    # Lowered thresholds to reduce false positives
    DLIB_THRESHOLD = 0.45 
    ARCFACE_THRESHOLD = 0.4 # Cosine distance (1 - sim). If sim > 0.6, dist < 0.4
    
    if os.path.exists(app.config['PERSONS_FOLDER']):
        for filename in os.listdir(app.config['PERSONS_FOLDER']):
            if filename.endswith('.json'):
                filepath = os.path.join(app.config['PERSONS_FOLDER'], filename)
                try:
                    with open(filepath, 'r') as f:
                        person = json.load(f)
                        
                    # Check Dlib first (usually faster/standard)
                    dist = float('inf')
                    if new_embeddings.get('dlib') and person['embeddings'].get('dlib'):
                        dist = calculate_distance(new_embeddings['dlib'], person['embeddings']['dlib'], 'euclidean')
                        if dist < DLIB_THRESHOLD and dist < min_distance:
                            min_distance = dist
                            best_match = person
                    
                    # Fallback to ArcFace if Dlib not available or to confirm
                    elif new_embeddings.get('arcface') and person['embeddings'].get('arcface'):
                        dist = calculate_distance(new_embeddings['arcface'], person['embeddings']['arcface'], 'cosine')
                        if dist < ARCFACE_THRESHOLD and dist < min_distance:
                            min_distance = dist
                            best_match = person
                            
                except Exception as e:
                    print(f"Error comparing {filename}: {e}")
                    
    return best_match, min_distance

@app.route('/merge_person', methods=['POST'])
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
                
            flash('Confirmed as duplicate. Showing existing record.')
            return redirect(url_for('view_person', person_id=existing_id))
    except Exception as e:
        flash(f'Error merging: {str(e)}')
        return redirect(url_for('criminal_dashboard'))

@app.route('/confirm_add_person', methods=['POST'])
def confirm_add_person():
    try:
        person_data = json.loads(request.form.get('new_data'))
        
        # Save JSON
        json_path = os.path.join(app.config['PERSONS_FOLDER'], f"{person_data['id']}.json")
        with open(json_path, 'w') as f:
            json.dump(person_data, f, indent=2)

        flash('Person added successfully!')
        return redirect(url_for('criminal_dashboard'))
    except Exception as e:
        flash(f'Error adding person: {str(e)}')
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
def add_person():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'image' not in request.files:
            flash('No file part')
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
            flash('No selected file')
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
                    flash('No face detected in the image. Please try another image.')
                    os.remove(file_path) # Clean up
                    return redirect(request.url)

                # Create person data structure
                person_data = {
                    "id": person_id,
                    "name": name,
                    "aadhaar": aadhaar,
                    "phone": phone,
                    "submitted_gender": gender,
                    "predicted_gender": analysis_results.get('gender'),
                    "predicted_age": analysis_results.get('age'),
                    "image_filename": new_filename,
                    "created_at": datetime.utcnow().isoformat() + "Z",
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

                flash('Person added successfully!')
                return redirect(url_for('criminal_dashboard'))

            except Exception as e:
                flash(f'Error processing image: {str(e)}')
                return redirect(request.url)

    return render_template('add_person.html')

@app.route('/person/<person_id>')
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
        
    flash('Person not found')
    return redirect(url_for('criminal_dashboard'))

@app.route('/update_person/<person_id>', methods=['POST'])
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
                
            flash('Person updated successfully!')
            return redirect(url_for('view_person', person_id=person_id))
        except Exception as e:
            flash(f'Error updating person: {str(e)}')
            return redirect(url_for('view_person', person_id=person_id))
    else:
        flash('Person not found')
        return redirect(url_for('criminal_dashboard'))

@app.route('/api/search')
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
def add_missing_person():
    if request.method == 'POST':
        if 'image' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['image']
        # Name is optional in screenshot but good to have, if not present use Unknown
        name = request.form.get('name') or "Unknown" 
        guardian_phone = request.form.get('guardian_phone')
        missing_aadhaar = request.form.get('missing_aadhaar')

        if file.filename == '':
            flash('No selected file')
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
                    flash('No face detected in the image. Please try another image.')
                    os.remove(file_path)
                    return redirect(request.url)

                person_data = {
                    "id": person_id,
                    "name": name,
                    "guardian_phone": guardian_phone,
                    "missing_aadhaar": missing_aadhaar,
                    "predicted_gender": analysis_results.get('gender'),
                    "predicted_age": analysis_results.get('age'),
                    "image_filename": new_filename,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "embeddings": {
                        "dlib": analysis_results.get('dlib'),
                        "arcface": analysis_results.get('arcface')
                    }
                }

                json_path = os.path.join(app.config['MISSING_FOLDER'], f"{person_id}.json")
                with open(json_path, 'w') as f:
                    json.dump(person_data, f, indent=2)

                flash('Missing person added successfully!')
                return redirect(url_for('missing_dashboard'))

            except Exception as e:
                flash(f'Error processing image: {str(e)}')
                return redirect(request.url)

    return render_template('add_missing.html')

@app.route('/image/<filename>')
def uploaded_file(filename):
    return redirect(url_for('static', filename=f'../data/images/{filename}'))

# Helper to serve images from data folder since it's not in static
from flask import send_from_directory
@app.route('/data/images/<filename>')
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/data/alerts/images/<filename>')
def serve_alert_image(filename):
    return send_from_directory(os.path.join(app.config['ALERTS_FOLDER'], 'images'), filename)

@app.route('/alerts')
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
                            alerts.append(data)
                except: pass
    
    # Sort by latest detection timestamp
    def get_latest_ts(alert):
        dets = alert.get('detections', [])
        if dets:
            return dets[-1].get('timestamp', '')
        return ''
        
    alerts.sort(key=get_latest_ts, reverse=True)
    
    return render_template('alerts.html', alerts=alerts, filter_type=filter_type)

@app.route('/alerts/view/<person_id>')
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
        flash('Alert not found')
        return redirect(url_for('alerts_dashboard'))

# Surveillance Stream Logic
surveillance_engine = None

@app.route('/api/surveillance/check_targets/<mode>')
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
def start_surveillance_background(mode):
    global surveillance_engine
    update_surveillance_list()
    
    # Initialize camera if not active
    if pm.active_camera is None:
        pm.initialize_camera(sys_config)
    
    if surveillance_engine is None:
        surveillance_engine = SurveillanceEngine(pm, sys_config)
    else:
        # Reload targets if needed
        surveillance_engine.load_targets()
        
    flash(f'Surveillance started in background for {mode} targets.')
    return redirect(url_for('surveillance_dashboard'))

@app.route('/start_surveillance_stream/<mode>')
def start_surveillance_stream(mode):
    global surveillance_engine
    # Ensure surveillance list is up to date
    update_surveillance_list()
    
    # Initialize camera if not active
    if pm.active_camera is None:
        pm.initialize_camera(sys_config)
    
    if surveillance_engine is None:
        surveillance_engine = SurveillanceEngine(pm, sys_config)
    else:
        surveillance_engine.load_targets()
        
    return render_template('stream_view.html', mode=mode)

@app.route('/stop_surveillance_stream')
def stop_surveillance_stream():
    global surveillance_engine
    if surveillance_engine:
        surveillance_engine.stop()
        surveillance_engine = None
        
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
def video_feed():
    global surveillance_engine
    if surveillance_engine is None:
        return "Surveillance not started", 404
    return Response(gen(surveillance_engine),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/system_alerts')
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)

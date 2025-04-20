from flask import Flask, render_template, request, redirect, session, flash, jsonify, url_for
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage
import datetime
import os
import uuid


# Firebase Initialization
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'final-605dd.appspot.com'
                      # ✅ Corrected bucket domain
})
db = firestore.client()
bucket = storage.bucket()

# Flask App Initialization
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_COOKIE_NAME'] = 'session'
app.config['SESSION_TYPE'] = 'filesystem'  # Use file-based session storage, or use 'redis' or 'memcached' for scalability



# Home Route
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about_us')
def about_us():
    return render_template('about_us.html')

@app.route('/home')
def home():
    return render_template('home.html')


# Google Login (Firebase Auth + Firestore)
@app.route('/google-login', methods=['POST'])
def google_login():
    data = request.get_json()
    id_token = data.get("idToken")

    if not id_token:
        return jsonify({"success": False, "error": "Missing ID token"}), 400

    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name')
        picture = decoded_token.get('picture')

        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            role = user_data.get("role")

            if role:
                redirect_url = url_for('mentor_dashboard') if role == 'mentor' else url_for('learner_dashboard')
                return jsonify({"success": True, "redirect": redirect_url, "role": role})
            else:
                return jsonify({"success": True, "needsRole": True, "redirect": url_for('select_role')})
        else:
            user_ref.set({
                "email": email,
                "name": name,
                "picture": picture,
                "uid": uid,
                "createdAt": firestore.SERVER_TIMESTAMP
            })
            return jsonify({"success": True, "needsRole": True, "redirect": url_for('select_role')})

    except Exception as e:
        print("Firebase Error:", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']  # 'mentor' or 'learner'

        try:
            # Create Firebase Auth user
            user = auth.create_user(email=email, password=password)

            # Store the user data in Firestore with role and name
            user_data = {
                'name': name,
                'email': email,
                'role': role,
                'uid': user.uid,
                'createdAt': firestore.SERVER_TIMESTAMP  # This will be handled properly by Firestore
            }

            # Add the user data to Firestore
            db.collection('users').document(user.uid).set(user_data)

            # Store user data in session
            session['user'] = {
                'uid': user.uid,
                'email': email,
                'role': role,
                'name': name
            }

            flash('Signup successful!')

            # Redirect user based on role
            if role == 'mentor':
                return redirect(url_for('mentor_dashboard'))
            else:
                return redirect(url_for('learner_dashboard'))

        except Exception as e:
            flash(f"Error: {str(e)}")
            return redirect(url_for('signup'))

    return render_template('signup.html')



# Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            # Sign in with Firebase Auth
            user = auth.get_user_by_email(email)
            # If password is correct, check Firestore for the role
            user_doc = db.collection('users').document(user.uid).get()

            if user_doc.exists:
                user_data = user_doc.to_dict()
                session['user'] = user_data
                role = user_data.get('role')

                # Redirect based on role
                if role == 'mentor':
                    return redirect(url_for('mentor_dashboard'))
                elif role == 'learner':
                    return redirect(url_for('learner_dashboard'))
                else:
                    flash("Role not assigned.")
                    return redirect(url_for('login'))

            else:
                flash("User data not found.")
                return redirect(url_for('login'))

        except Exception as e:
            flash(f"Error: {str(e)}")
            return redirect(url_for('login'))

    return render_template('login.html')



@app.route('/session_Login', methods=['POST'])
def session_login():
    try:
        data = request.get_json()
        id_token = data['idToken']
        role = data['role']  # Role sent from frontend

        # Verify the ID Token with Firebase Admin SDK
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']

        # Fetch the user data from Firestore
        user_ref = db.collection('users').document(uid)
        user_data = user_ref.get()

        if user_data.exists:
            user = user_data.to_dict()
            user_role = role  # Use the role passed from frontend directly

            # Store user details in the session
            session['user'] = {'uid': uid, 'role': user_role}

            # Return success and the user's role
            return jsonify({
                'success': True,
                'role': user_role
            })
        else:
            return jsonify({
                'success': False,
                'message': "User not found in Firestore"
            }), 404
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error: {str(e)}"
        }), 400


# Role Selection
@app.route('/select-role', methods=['GET', 'POST'])
def select_role():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        role = request.form.get('role')
        uid = user['uid']

        db.collection('users').document(uid).update({'role': role})
        session['user']['role'] = role

        return redirect(url_for('mentor_dashboard' if role == 'mentor' else 'learner_dashboard'))

    return render_template('select_role.html', name=user.get('name'))


# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# Dashboards
@app.route('/mentor_dashboard')
def mentor_dashboard():
    if 'user' not in session or session['user']['role'] != 'mentor':
        return redirect(url_for('login'))

    uid = session['user']['uid']
    # You could fetch courses here if needed for the dashboard

    return render_template('mentor_dashboard.html', user=session['user'], name=session['user'].get('name'))



@app.route('/learner_dashboard')
def learner_dashboard():
    if 'user' not in session or session['user']['role'] != 'learner':
        return redirect(url_for('login'))
    return render_template('learner_dashboard.html', user=session['user'], name=session['user'].get('name'))



@app.route('/entrepreneur_dashboard')
def entrepreneur_dashboard():
    # If you're storing pitches in a 'pitches' collection
    pitches_ref = db.collection('pitches').order_by('submitted_at', direction=firestore.Query.DESCENDING)
    pitches = []

    try:
        for doc in pitches_ref.stream():
            pitch = doc.to_dict()
            pitch['submitted_at'] = pitch.get('submitted_at', datetime.datetime.now())  # fallback
            pitch['id'] = doc.id

            # Optional: Get rating if stored under a subcollection or list
            ratings = pitch.get('ratings', [])  # Adjust if ratings are stored elsewhere
            pitch['ratings'] = ratings

            pitches.append(pitch)

    except Exception as e:
        print("Error fetching pitches:", e)
        flash("Failed to load pitches.", "danger")

    return render_template("entrepreneur_dashboard.html", pitches=pitches)


@app.route('/my_courses')
def my_courses():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    user_id = user['uid']

    # Fetch user document
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        return "User not found", 404

    user_data = user_doc.to_dict()
    enrolled_courses = user_data.get('enrolled_courses', [])
    course_count = len(enrolled_courses)

    return render_template('my_courses.html', courses=enrolled_courses, course_count=course_count)



# Mentor add
@app.route('/add_course', methods=['POST'])
def add_course():
    data = request.get_json()

    course_title = data.get('course_title')
    course_description = data.get('course_description')
    video_link = data.get('video_link')
    thumbnail_url = data.get('thumbnail_url')

    # Save these to your database
    print("Received Course:", course_title, video_link, thumbnail_url)

    # Example: save to SQLite or Firestore here

    return jsonify({'status': 'success'}), 200




@app.route('/mentor/pitches', methods=['GET', 'POST'])
def view_pitches():
    if request.method == 'POST':
        # Get pitch ID and rating from the form
        pitch_id = request.form.get('pitch_id')
        rating = int(request.form.get('rating'))
        
        # Update the mentor rating for the pitch in Firestore
        pitch_ref = db.collection('pitches').document(pitch_id)
        pitch_ref.update({
            'mentor_rating': rating
        })
        return redirect(url_for('view_pitches'))  # Reload the page after submission

    # Fetch all available pitches
    pitches_ref = db.collection('pitches')
    pitches = pitches_ref.stream()  # Get all pitches from Firestore

    pitch_data = []
    for pitch in pitches:
        pitch_dict = pitch.to_dict()
        pitch_data.append({
            'id': pitch.id,
            'title': pitch_dict['title'],
            'description': pitch_dict['description'],
            'mentor_rating': pitch_dict.get('mentor_rating', None)
        })
    
    return render_template('mentor_pitches.html', pitches=pitch_data)



# E-Learning course list
@app.route('/e_learning', methods=['GET'])
def e_learning():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    courses_ref = db.collection('courses')
    courses = courses_ref.stream()
    course_list = []

    for course in courses:
        course_data = course.to_dict()
        course_data['id'] = course.id
        course_data['image'] = course_data.get('image_url', '')  # Optional image
        course_list.append(course_data)

    return render_template('e_learning.html', courses=course_list)


# Enroll in Course
@app.route('/enroll', methods=['POST'])
def enroll():
    if 'user' not in session:
        flash("Please log in first.")
        return redirect(url_for('login'))

    course_id = request.form.get('course_id')
    user = session['user']

    course_ref = db.collection('courses').document(course_id)
    course_doc = course_ref.get()

    if not course_doc.exists:
        flash("Course not found.")
        return redirect(url_for('e_learning'))

    course_data = course_doc.to_dict()
    course_entry = {'id': course_id, 'name': course_data.get('title', 'Untitled Course')}

    user_ref = db.collection('users').document(user['uid'])
    user_doc = user_ref.get()

    if user_doc.exists:
        enrolled_courses = user_doc.to_dict().get('enrolled_courses', [])

        if any(c['id'] == course_id for c in enrolled_courses):
            flash("You are already enrolled in this course.")
        else:
            enrolled_courses.append(course_entry)
            user_ref.update({'enrolled_courses': enrolled_courses})
            flash("Successfully enrolled!")
    else:
        user_ref.set({
            'name': user['name'],
            'email': user['email'],
            'enrolled_courses': [course_entry]
        })
        flash("Successfully enrolled!")

    return redirect(url_for('learner_dashboard'))

  # Placeholder for pitches data

@app.route('/learner/pitch', methods=['GET'])
def pitch_page():
    user_name = session.get('user', {}).get('name', 'Unknown')
    pitches_ref = db.collection('pitches').where('learner_name', '==', user_name)
    pitches = [doc.to_dict() for doc in pitches_ref.stream()]
    return render_template('entrepreneur_dashboard.html', pitches=pitches)


@app.route('/submit_pitch', methods=['POST'])
def submit_pitch():
    startup_name = request.form['startup_name']
    description = request.form['description']
    sector = request.form['sector']
    stage = request.form['stage']

    pitch_data = {
        "title": startup_name,
        "description": description,
        "sector": sector,
        "stage": stage,
        "learner_name": session['user'].get('name', 'Unknown') if 'user' in session else 'Unknown',
        "submitted_at": datetime.datetime.utcnow()
,
        "ratings": []
    }

    db.collection("pitches").add(pitch_data)

    return redirect(url_for('pitch_page'))

@app.route('/user_profile', methods=['GET', 'POST']) 
def user_profile():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('user_profile.html', user=session['user'])




if __name__ == '__main__':
    app.run(debug=True)

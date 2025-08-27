import random
import os
import jwt
from werkzeug.security import check_password_hash, generate_password_hash
from flask import Flask, request, jsonify
from model import db, User, QuizSession
from flask_cors import CORS
import time
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  
db.init_app(app)
CORS(app)

with app.app_context():
    db.create_all()

# In-memory quiz sessions
anonymous_sessions = {}

# function to generate math questions
def math_question():
    left = random.randint(1, 9)
    right = random.randint(1, 9)
    operand = ["+", "*", "-"]
    operator = random.choice(operand)
    expr = f"{left}{operator}{right}"
    ans = eval(expr)
    return expr, ans

@app.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json()
        if not data or not data.get('email_address') or not data.get('password'):
            return jsonify({"error": "Email and password are required"}), 400

        hashed_pw = generate_password_hash(data['password'])
        user = User(email_address=data['email_address'], password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        return jsonify({"message": "User registered successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login_user():
    try:
        data = request.get_json()
        email = data.get('email_address')
        password = data.get('password')

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        user = User.query.filter_by(email_address=email).first()
        if user and check_password_hash(user.password, password):
            token = jwt.encode({"user_id": user.id}, app.config['SECRET_KEY'], algorithm="HS256")
            return jsonify({"token": token}), 200

        return jsonify({"error": "Invalid email or password"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Start a new quiz session
@app.route('/quiz/start', methods=['POST'])
def start_quiz():
    token = request.headers.get('Authorization')
    user_id = None
    user_email = None
    
    if token:
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            user_id = payload['user_id']
            user_email = payload.get('email', 'Unknown')
        except:
            pass
    
    data = request.get_json()
    attempts = data.get('attempts', 5)  # Default to 5 if not provided
    
    # Validate attempts
    if not isinstance(attempts, int) or attempts < 1 or attempts > 20:
        return jsonify({"error": "Attempts must be between 1 and 20"}), 400

    expr, ans = math_question()
    # session_id = str(user_id)

    # Initialize quiz session
    session_data = {
        "user_id": user_id,
        "user_email": user_email,
        "score": 0,
        "total_questions": attempts,
        "current_question": 1,
        "correct_answers": 0,
        "start_time": time.time(),
        "current_answer": ans,
        "questions_answered": 0
    }

    if user_id:
        # Authenticated user - save to database
        session_id = str(uuid.uuid4())
        quiz_session = QuizSession(
            session_id=session_id,
            user_id=user_id,
            total_questions=attempts,
            correct_answers=0,
            time_taken=0,
            accuracy=0
        )
        db.session.add(quiz_session)
        db.session.commit()
        
        session_data["db_session_id"] = session_id
        anonymous_sessions[session_id] = session_data
    else:
        # Anonymous user - save to memory
        session_id = str(uuid.uuid4())
        anonymous_sessions[session_id] = session_data

    return jsonify({
        "session_id": session_id,
        "question": expr,
        "question_number": 1,
        "total_questions": attempts,
        "message": f"Quiz started with {attempts} questions"
    }), 200

# Submit an answer
@app.route('/quiz/answer', methods=['POST'])
def submit_answer():
    data = request.get_json()
    session_id = data.get('session_id')
    user_answer = data.get("answer")

    if not session_id:
        return jsonify({"error": "Session ID is required"}), 400

    if user_answer is None:
        return jsonify({"error": "Answer is required"}), 400


    try:
        user_answer = int(user_answer)
    except ValueError:
        return jsonify({"error": "Answer must be a number"}), 400

    # Get session data
    session = anonymous_sessions.get(session_id)
    if not session:
        return jsonify({"error": "Invalid session. Please start a new quiz."}), 400
    

    correct = user_answer == session["current_answer"]
    session["questions_answered"] += 1
    
    if correct:
        session["correct_answers"] += 1

    session["current_question"] += 1

    # Check if quiz is finished
    if session["current_question"] > session["total_questions"]:
        end_time = time.time()
        total_time = round(end_time - session["start_time"], 2)
        score = session["correct_answers"]
        total_questions = session["total_questions"]
        
        # Calculate accuracy percentage
        accuracy = round((score / total_questions) * 100, 2) if total_questions > 0 else 0

        # Save to database if user is authenticated
        if session.get("user_id") and session.get("db_session_id"):
            try:
                quiz_session = QuizSession.query.filter_by(session_id=session["db_session_id"]).first()
                if quiz_session:
                    quiz_session.correct_answers = score
                    quiz_session.time_taken = total_time
                    quiz_session.accuracy = accuracy
                    db.session.commit()
            except Exception as e:
                db.session.rollback()

        # Clean up session
        if session_id in anonymous_sessions:
            del anonymous_sessions[session_id]

        
        return jsonify({
            "message": "Quiz finished",
            "score": score,
            "total_questions": total_questions,
            "accuracy": accuracy,
            "time_taken": total_time,
            "time_unit": "seconds"
        }), 200
    
    expr, ans = math_question()
    session["current_answer"] = ans

    return jsonify({
        "question": expr,
        "question_number": session["current_question"],
        "total_questions": session["total_questions"],
        "correct": correct,
        "feedback": "Correct!" if correct else "Wrong answer!"
    }), 200

# Get user history (requires authentication)
@app.route('/user/history', methods=['GET'])
def get_user_history():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({"error": "Authentication required to view history"}), 401

    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        user_id = payload['user_id']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    try:
        # Get user's quiz history
        quiz_sessions = QuizSession.query.filter_by(user_id=user_id).order_by(QuizSession.created_at.desc()).all()
        
        history = []
        total_accuracy = 0
        total_sessions = len(quiz_sessions)
        
        for session in quiz_sessions:
            history.append({
                "session_id": session.session_id,
                "total_questions": session.total_questions,
                "correct_answers": session.correct_answers,
                "accuracy": session.accuracy,
                "time_taken": session.time_taken,
                "date": session.created_at.isoformat()
            })
            total_accuracy += session.accuracy
        
        overall_accuracy = round(total_accuracy / total_sessions, 2) if total_sessions > 0 else 0
        
        return jsonify({
            "history": history,
            "overall_accuracy": overall_accuracy,
            "total_sessions": total_sessions
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/quiz/status', methods=['GET'])
def quiz_status():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({"error": "Token is required"}), 401

    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        user_id = payload['user_id']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    
    session_id = str(user_id)
    session = quiz_sessions.get(session_id)
    if not session:
        return jsonify({"error": "No active quiz session"}), 400

    elapsed_time = round(time.time() - session["start_time"], 2)
    
    return jsonify({
        "current_question": session["current_question"],
        "total_questions": session["total_questions"],
        "questions_answered": session["questions_answered"],
        "correct_answers": session["correct_answers"],
        "elapsed_time": elapsed_time,
        "time_unit": "seconds"
    }), 200

if __name__ == '__main__':
    app.run(debug=True)
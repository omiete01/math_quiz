import random
import jwt
from werkzeug.security import check_password_hash, generate_password_hash
from flask import Flask, request, jsonify
from model import db, User
# import requests
import time

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
app.app_context().push()

@app.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json()

        if not data or not data.get('email_address') or not data.get('password'):
            return {"error": "Email address and password are required"}, 400
        
        password = generate_password_hash(data['password'])
        user = User(email_address=data['email_address'], password=password)
        db.session.add(user)
        db.session.commit()

        return jsonify({"message": "User registered successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login_user():
    try:
        data = request.get_json()
        email_address = data.get('email_address')
        password = data.get('password')

        if not email_address or not password:
            return {"error": "Email address and password are required"}, 400
        user = User.query.filter_by(email_address=email_address).first()

        if user and check_password_hash(user.password, password):
            token = jwt.encode({"user_id": user.id}, app.config['SECRET_KEY'], algorithm="HS256")
            return {"token": token}, 200
        return {"error": "Invalid email address or password"}, 401
    except Exception as e:  
        return jsonify({"error": str(e)}), 500

@app.route('/quiz', methods=['GET', 'PUT'])
def math_quiz():

    # user_name = request.args.get("name", "Guest")
    # user_name = login_user()

    # print(f"\nHello, {user_name}! Welcome to the Math Quiz.")
    # attempts = request.args.get("attempts", 5, type=int)
    attempts = 5
    count = 0

    print("Ready to start? (y/n)")
    if input().lower() == "y":
        start_time = time.time()
    else:
        return {"message": "Quiz not started"}, 400

    for i in range(attempts):
        expr, ans = math_question()
        
        while True:
            print(f"\n{expr}?")
            user_ans = input("Ans: ")
            
            if user_ans == str(ans):
                count += 1
                print("Correct Answer.")
                break
            else:
                print(f"Thats not right. The correct answer is {ans}")
                break
    end_time = time.time()
                
    print(f"Thanks for attempting the quiz. Your score is {count} out of {attempts}")
    print(f"Time taken: {end_time - start_time} seconds")

def math_question():
    left = random.randint(1,9)
    right = random.randint(1,9)
    operand = ["+", "*", "-"] #"/"
    
    operator = random.choice(operand)
        
    expr = str(left) + operator + str(right)
    ans = eval(expr)
    
    return expr, ans

if __name__ == '__main__':
    app.run(debug=True)

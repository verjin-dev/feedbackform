import os

# Define the new Flask backend structure to generate
backend_structure = {
    "backend": [
        "app/models",
        "app/routes",
        "app/services",
        "app/utils",
        "migrations",
    ]
}

# Create directories
for root, subdirs in backend_structure.items():
    for subdir in subdirs:
        os.makedirs(os.path.join("C:\\Users\\verji\\OneDrive\\Documents\\GitHub\\feedbackform\\Rework", subdir), exist_ok=True)

# Create essential files with boilerplate/stubs
essential_files = {
    "backend/run.py": '''from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
''',

    "backend/app/__init__.py": '''from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from .config import Config

db = SQLAlchemy()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)
    jwt.init_app(app)

    from .routes.auth_routes import auth_bp
    from .routes.feedback_routes import feedback_bp
    from .routes.admin_routes import admin_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(feedback_bp, url_prefix="/api/feedback")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    return app
''',

    "backend/app/config.py": '''import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URI", "mysql+pymysql://user:pass@localhost/feedback_db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret")
''',

    "backend/requirements.txt": '''flask
flask-cors
flask-jwt-extended
flask-sqlalchemy
flask-migrate
pymysql
python-dotenv
'''
}

# Write files
for file_path, content in essential_files.items():
    with open(f"C:\\Users\\verji\\OneDrive\\Documents\\GitHub\\feedbackform\\Rework\\{file_path}", "w") as f:
        f.write(content)

# Return confirmation and list of generated files
os.listdir("C:\\Users\\verji\\OneDrive\\Documents\\GitHub\\feedbackform\\Rework\\backend")
# Fixing path: creating base backend directory explicitly
os.makedirs("C:\\Users\\verji\\OneDrive\\Documents\\GitHub\\feedbackform\\Rework\\app", exist_ok=True)

# Retry writing files after directory is created
for file_path, content in essential_files.items():
    full_path = os.path.join("C:\\Users\\verji\\OneDrive\\Documents\\GitHub\\feedbackform\\Rework", file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(content)

# Show final structure
os.listdir("C:\\Users\\verji\\OneDrive\\Documents\\GitHub\\feedbackform\\Rework\\backend")
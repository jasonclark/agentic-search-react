from flask import Flask

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'any-random-string-here'
    
    from app.routes import main
    app.register_blueprint(main)
    
    return app
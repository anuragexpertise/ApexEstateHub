from app import create_app, create_dash_app

# Create Flask application
flask_app = create_app(os.getenv('FLASK_CONFIG', 'production'))

# Create and mount Dash application
dash_app = create_dash_app(flask_app)

# Expose for Gunicorn
server = flask_app

if __name__ == '__main__':
    flask_app.run(host='0.0.0.0', port=8050, debug=False)
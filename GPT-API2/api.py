from flask import Flask
from app.config import BASE_DIR, HOST, PORT
from app.routes import bp

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)



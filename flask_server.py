from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def health_check():
    return "OK"

if __name__ == "__main__":
    # שירות יקשיב על כל כתובת IP (0.0.0.0) בפורט 8080
    app.run(host='0.0.0.0', port=8080)

import os
from flask import Flask
from flask_restx import Api
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-production")
CORS(app, resources={r"/*": {"origins": "*"}})

api = Api(app, version="1.0", title="Podeo Cliq Service", prefix="/api", doc=False, serve_spec=False)
from webhook.podeo_webhook import ns
api.add_namespace(ns)


@app.route("/", endpoint="base_status")
def base_status():
    return {"status": "ok"}, 200


@app.route("/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
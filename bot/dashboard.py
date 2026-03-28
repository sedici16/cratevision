"""Flask dashboard for CrateVision analytics."""
import logging
from flask import Flask, render_template, jsonify
from bot import db

logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__, template_folder="../templates")

    @app.route("/")
    def index():
        return render_template(
            "dashboard.html",
            stats=db.get_stats(),
            searches_over_time=db.get_searches_over_time(),
            verdict_dist=db.get_verdict_distribution(),
            top_artists=db.get_top_artists(),
            recent=db.get_recent_searches(),
            users=db.get_users(),
        )

    @app.route("/api/stats")
    def api_stats():
        return jsonify(db.get_stats())

    @app.route("/api/searches")
    def api_searches():
        return jsonify(db.get_recent_searches())

    @app.route("/api/verdicts")
    def api_verdicts():
        return jsonify(db.get_verdict_distribution())

    @app.route("/api/artists")
    def api_artists():
        return jsonify(db.get_top_artists())

    @app.route("/api/users")
    def api_users():
        return jsonify(db.get_users())

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)

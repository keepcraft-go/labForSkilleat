from flask import Flask
from .db import init_db, close_db
from .routes.quiz import quiz_bp
from .routes.hall import hall_bp
from .routes.landing import landing_bp
from .routes.schedule import schedule_bp
from .routes.collab import collab_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret-change"

    with app.app_context():
        init_db()

    app.teardown_appcontext(close_db)
    app.register_blueprint(landing_bp)
    app.register_blueprint(quiz_bp, url_prefix="/quiz")
    app.register_blueprint(hall_bp, url_prefix="/hall")
    app.register_blueprint(schedule_bp)
    app.register_blueprint(collab_bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

from app.main import create_app
from app.services.news import get_tech_news


def main():
    app = create_app()
    with app.app_context():
        get_tech_news()
        print("[OK] news cache warmed")


if __name__ == "__main__":
    main()

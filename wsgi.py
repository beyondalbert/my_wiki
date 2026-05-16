"""Production WSGI entry point."""
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app

application = create_app(os.getenv("FLASK_CONFIG", "production"))

"""Vercel serverless entry point — imports the FastAPI app."""

import sys
import os

# Add the server directory to the path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

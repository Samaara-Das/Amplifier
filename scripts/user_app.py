"""Local creator app — slim FastAPI on localhost:5222.

Entry point preserved so existing references to `python scripts/user_app.py` keep working.
"""

import uvicorn
from utils.local_server import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5222)

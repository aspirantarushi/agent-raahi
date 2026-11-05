"""Test settings.

- The app opens on Home for everyone; most screen tests start on "New case".
- Tests never touch real data: storage is always local files, and anything the app saves during a
  test (with no folder given) goes to a throw-away folder, not the app's own folders or Supabase.
- Groq (the backup AI) is never called with a real key, except by the live test in test_groq.py.
- Settings are never read from the real .env or .streamlit/secrets.toml (RAAHI_TEST), and there is no
  clinic passcode, so screen tests don't need to sign in (tests/test_tracker_screens.py sets one).
"""

import os
import tempfile

os.environ.setdefault("RAAHI_START_SCREEN", "New case")
os.environ["RAAHI_STORAGE"] = "local"
os.environ["RAAHI_TEST"] = "1"  # settings come only from the environment: never the real secrets file
os.environ["RAAHI_DATA_DIR"] = tempfile.mkdtemp(prefix="raahi-test-")
os.environ.pop("CLINIC_PASSCODE", None)
# Never call the real Groq service from tests: an empty value stops llm._load_dotenv reading the real
# key from .env. The one live Groq test reads the key itself (tests/test_groq.py).
os.environ["GROQ_API_KEY"] = ""

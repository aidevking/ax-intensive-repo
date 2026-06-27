from dotenv import load_dotenv
load_dotenv()
import os
has_openai = bool(os.environ.get("OPENAI_API_KEY"))
print("OPENAI_API_KEY set:", has_openai)

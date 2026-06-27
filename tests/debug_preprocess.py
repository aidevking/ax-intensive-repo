import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from backend.services.analyze_service import AnalyzeService

svc = AnalyzeService()
df = svc.preprocess("com.shinhan.sbanking", force=True)
print("processed rows:", len(df))
print("cols:", df.columns.tolist())
print("is_short:", df['is_short'].sum())
print("rating dist:", df['rating'].value_counts().sort_index().to_dict())

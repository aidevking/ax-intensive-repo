import warnings
warnings.filterwarnings("ignore")
import pandas as pd

df = pd.read_parquet("backend/data/raw/google_play_com.shinhan.sbanking_20260620.parquet")
print("rows:", len(df))
print("columns:", list(df.columns))
print("rating range:", df["rating"].min(), "~", df["rating"].max())
print("null review_text:", df["review_text"].isna().sum())
print("null review_id:", df["review_id"].isna().sum())
print("duplicates:", df.duplicated(subset=["app_id","review_id"]).sum())

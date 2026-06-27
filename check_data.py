import pandas as pd
import sys

df = pd.read_parquet('backend/data/raw/google_play_com.shinhan.sbanking_20260620.parquet')
print('행 수:', len(df))
print('컬럼:', df.columns.tolist())
print('rating 분포:', df['rating'].value_counts().sort_index().to_dict())
for i in range(5):
    row = df.iloc[i]
    print(f'리뷰{i}: rating={row["rating"]}, text={row["review_text"][:80]}')

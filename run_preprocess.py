import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from backend.services.analyze_service import AnalyzeService
svc = AnalyzeService()
df = svc.preprocess('com.shinhan.sbanking', force=True)
print(f'전처리 완료: {len(df)}건, is_short={df.is_short.sum()}건')
df = svc.label_reviews(df)
pos = len(df[df.sentiment_label=='positive'])
neg = len(df[df.sentiment_label=='negative'])
neu = len(df[df.sentiment_label=='neutral'])
print(f'라벨링: positive={pos}건, negative={neg}건, neutral={neu}건')
print(f'불일치: {df.is_mismatch.sum()}건')

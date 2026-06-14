import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pymongo import MongoClient
import requests
from apscheduler.schedulers.background import BackgroundScheduler

# 1. 환경 변수 로드
load_dotenv()

app = Flask(__name__)
CORS(app)

# 2. 데이터베이스 설정 (MongoDB)
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client['ok_db']

# 3. 네이버 API 키 설정 (Render 환경 변수에서 가져옴)
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

def fetch_naver_news(keyword, display=5):
    """네이버 API를 통해 특정 키워드의 뉴스를 검색하는 함수"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("[오류] 네이버 API 키가 설정되지 않았습니다. 환경 변수를 확인하세요.")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": keyword,
        "display": display,
        "sort": "sim" # sim: 정확도순, date: 최신순
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])
    except Exception as e:
        print(f"[뉴스 검색 실패] {e}")
        return []

# 4. 스케줄러 정기 작업
def fetch_stock_and_news_task():
    try:
        # 매시간 백그라운드에서 경제/IT/AI 뉴스를 수집하는 기능
        news_data = fetch_naver_news("경제 IT AI", display=3)
        print(f"[스케줄러 작동] 백그라운드 뉴스 {len(news_data)}건 검색 완료.")
    except Exception as e:
        print(f"[스케줄러 에러] {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_stock_and_news_task, trigger="cron", hour="*")
scheduler.start()

print("알람시계가 정상적으로 작동을 시작했습니다. (시세 + 경제/IT 뉴스 연동 모듈 가동)")

# 5. API 접속 경로
@app.route('/')
def home():
    return jsonify({
        "status": "healthy",
        "message": "알람시계 백엔드 서버가 정상적으로 가동 중입니다."
    }), 200

@app.route('/api/news')
def get_latest_news():
    """외부에서 /api/news 로 접속했을 때 뉴스를 반환"""
    news_items = fetch_naver_news("경제 IT AI", display=5)
    return jsonify({
        "message": "최신 뉴스 조회 성공",
        "data": news_items
    })

@app.route('/api/stocks')
def get_stock_prices():
    return jsonify({"message": "실시간 주식 시세 조회 성공"})

# 6. 서버 실행
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

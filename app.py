from flask import Flask, jsonify
from flask_cors import CORS
import os
import requests
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)

NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
MONGO_URI = os.environ.get('MONGO_URI')

try:
    client = MongoClient(MONGO_URI)
    db = client['smartu3s_mong']
    news_collection = db['news']
    history_collection = db['history']
except Exception as e:
    print("MongoDB 연결 에러:", e)

# ★ 자동 수집을 수행하는 함수 (매일 정해진 시간에 실행됨)
def collect_daily_data():
    try:
        # 1. 네이버 뉴스 수집
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
        }
        params = {"query": "경제 IT AI", "display": 5, "sort": "date"}
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        articles = data.get("items", [])
        if articles:
            news_collection.insert_many(articles)
        
        # 2. 누적 기록(History) 데이터베이스에 오늘의 수집 결과 저장
        seoul_time = datetime.now(pytz.timezone('Asia/Seoul'))
        history_record = {
            "collected_at": seoul_time.strftime("%Y-%m-%d %H:%M:%S"),
            "news_count": len(articles),
            "status": "자동 수집 성공"
        }
        history_collection.insert_one(history_record)
        print("자동 수집 및 기록 저장 완료:", history_record)
        
    except Exception as e:
        print("자동 수집 에러:", str(e))

# ★ 스케줄러(타이머) 설정: 한국 시간 기준 매일 15시 30분에 작동
scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Seoul'))
scheduler.add_job(func=collect_daily_data, trigger="cron", hour=15, minute=30)
scheduler.start()

@app.route('/')
def home():
    return "OK Backend Server is Running with Scheduler!"

@app.route('/api/news')
def get_news():
    # 수동 뉴스 조회 유지
    articles = list(news_collection.find({}, {'_id': 0}).sort('_id', -1).limit(5))
    return jsonify({"message": "DB에서 뉴스 불러오기 성공", "data": articles})

@app.route('/api/history')
def get_history():
    try:
        history_data = list(history_collection.find({}, {'_id': 0}).sort('collected_at', -1).limit(30))
        return jsonify({"status": "success", "history": history_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ★ 당장 테스트해볼 수 있는 '강제 수집' 스위치 추가
@app.route('/api/force_collect')
def force_collect():
    collect_daily_data()
    return jsonify({"message": "수동으로 자동 수집 함수를 실행했습니다! 화면을 새로고침 해보세요."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

from flask import Flask, jsonify
from flask_cors import CORS
import os
import requests
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import yfinance as yf

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
            
        # 2. ETF 시세 수집 (1일 -> 5일치 데이터 확보 후 최신값 추출로 변경)
        etf_price = 0
        try:
            ticker = yf.Ticker("458730.KS")
            todays_data = ticker.history(period="5d") 
            if not todays_data.empty:
                etf_price = int(todays_data['Close'].iloc[-1]) # 가장 최신 종가
        except Exception as e:
            print("ETF 시세 수집 에러:", str(e))
        
        # 3. 누적 기록 저장
        seoul_time = datetime.now(pytz.timezone('Asia/Seoul'))
        history_record = {
            "collected_at": seoul_time.strftime("%Y-%m-%d %H:%M:%S"),
            "news_count": len(articles),
            "etf_price": etf_price,
            "post_office_rate": 4.2, 
            "kdb_rate": 3.5,         
            "status": "자동 수집 성공"
        }
        history_collection.insert_one(history_record)
        print("자동 수집 및 기록 저장 완료:", history_record)
        
    except Exception as e:
        print("자동 수집 에러:", str(e))

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Seoul'))
scheduler.add_job(func=collect_daily_data, trigger="cron", hour=15, minute=30)
scheduler.start()

@app.route('/')
def home():
    return "OK Backend Server is Running with 5d ETF Data!"

@app.route('/api/news')
def get_news():
    articles = list(news_collection.find({}, {'_id': 0}).sort('_id', -1).limit(5))
    return jsonify({"message": "DB에서 뉴스 불러오기 성공", "data": articles})

@app.route('/api/history')
def get_history():
    try:
        history_data = list(history_collection.find({}, {'_id': 0}).sort('collected_at', -1).limit(30))
        return jsonify({"status": "success", "history": history_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/force_collect')
def force_collect():
    collect_daily_data()
    return jsonify({"message": "수동으로 자동 수집(뉴스+ETF) 함수를 실행했습니다! 화면을 새로고침 해보세요."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

from flask import Flask, jsonify
from flask_cors import CORS
import os
import requests
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
from bs4 import BeautifulSoup

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

def get_tiger_price():
    """네이버 금융에서 TIGER 미국배당다우존스 실시간 종가 크롤링"""
    try:
        url = "https://finance.naver.com/item/main.naver?code=458730"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.select_one('.no_today .no_up .blind')
        if price_tag:
            return int(price_tag.text.replace(',', ''))
    except Exception as e:
        print("네이버 시세 수집 에러:", e)
    return 0

def collect_daily_data():
    try:
        # 1. 네이버 뉴스 수집
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
        params = {"query": "경제 IT AI", "display": 5, "sort": "date"}
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        articles = data.get("items", [])
        if articles:
            news_collection.insert_many(articles)
            
        # 2. ETF 시세 수집 (크롤링 방식)
        etf_price = get_tiger_price()
        
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
    return "OK Backend Server is Running with Naver Crawler!"

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
    return jsonify({"message": "수동 수집 성공! 새로고침 하세요."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

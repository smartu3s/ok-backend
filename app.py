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

# 환경 변수 설정
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
MONGO_URI = os.environ.get('MONGO_URI')

# 한국투자증권 API 키
KIS_APP_KEY = os.environ.get('KIS_APP_KEY')
KIS_APP_SECRET = os.environ.get('KIS_APP_SECRET')

try:
    client = MongoClient(MONGO_URI)
    db = client['smartu3s_mong']
    news_collection = db['news']
    history_collection = db['history']
except Exception as e:
    print("MongoDB 연결 에러:", e)

def get_kis_access_token():
    """한국투자증권 API 접근 토큰 발급"""
    try:
        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SECRET
        }
        res = requests.post(url, headers=headers, json=body)
        if res.status_code == 200:
            return res.json().get("access_token")
    except Exception as e:
        print("한투 토큰 발급 에러:", e)
    return None

def get_tiger_price_kis(token):
    """한국투자증권 API를 이용한 TIGER 미국배당다우존스(458730) 시세 조회"""
    try:
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SECRET,
            "tr_id": "FHKST01010100" # 주식현재가 조회 TR ID
        }
        params = {
            "fid_cond_mrkt_div_code": "J", # J: 주식/ETF
            "fid_input_iscd": "458730"     # 종목코드
        }
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            if data.get("rt_cd") == "0":
                price_str = data["output"]["stck_prpr"] # 현재가
                return int(price_str)
    except Exception as e:
        print("한투 시세 조회 에러:", e)
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
            
        # 2. 한국투자증권 API 연동 ETF 시세 수집
        etf_price = 0
        if KIS_APP_KEY and KIS_APP_SECRET:
            token = get_kis_access_token()
            if token:
                etf_price = get_tiger_price_kis(token)
            else:
                print("한투 API 토큰 발급 실패")
        else:
            print("한투 API 키가 설정되지 않았습니다.")
        
        # 3. 누적 기록 저장
        seoul_time = datetime.now(pytz.timezone('Asia/Seoul'))
        history_record = {
            "collected_at": seoul_time.strftime("%Y-%m-%d %H:%M:%S"),
            "news_count": len(articles),
            "etf_price": etf_price,
            "post_office_rate": 4.2, 
            "kdb_rate": 3.5,         
            "status": "자동 수집 성공 (한투API)"
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
    return "OK Backend Server is Running with KIS API!"

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
    return jsonify({"message": "한국투자증권 API 수동 수집 성공! 새로고침 하세요."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

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

KIS_APP_KEY = os.environ.get('KIS_APP_KEY')
KIS_APP_SECRET = os.environ.get('KIS_APP_SECRET')

# 금감원 API 키 추가
FSS_API_KEY = os.environ.get('FSS_API_KEY')

try:
    client = MongoClient(MONGO_URI)
    db = client['smartu3s_mong']
    news_collection = db['news']
    history_collection = db['history']
except Exception as e:
    print("MongoDB 연결 에러:", e)

# 한투 토큰 캐싱
cached_kis_token = None
token_issued_at = None

def get_valid_kis_token():
    global cached_kis_token, token_issued_at
    now = datetime.now()
    if cached_kis_token and token_issued_at and (now - token_issued_at).total_seconds() < 20 * 3600:
        return cached_kis_token
        
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
            cached_kis_token = res.json().get("access_token")
            token_issued_at = now
            return cached_kis_token
    except Exception as e:
        print("한투 토큰 발급 에러:", e)
    return None

def get_tiger_price_kis(token):
    try:
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SECRET,
            "tr_id": "FHKST01010100"
        }
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": "458730"
        }
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            if data.get("rt_cd") == "0":
                return int(data["output"]["stck_prpr"])
    except Exception as e:
        print("한투 시세 조회 에러:", e)
    return 0

def get_fss_rates():
    """금융감독원 API를 통해 예금 금리(12개월 기준) 자동 수집"""
    kdb_rate = 3.5        # 금감원 서버 응답 실패 시 사용할 기본값
    post_office_rate = 4.2 # 우체국은 조회 대상 밖이므로 기본값 유지

    if not FSS_API_KEY:
        print("금감원 API 키가 없습니다. 기본 금리를 사용합니다.")
        return post_office_rate, kdb_rate

    try:
        url = "http://finlife.fss.or.kr/finlifeapi/depositProductsSearch.json"
        params = {
            "auth": FSS_API_KEY,
            "topFinGrpNo": "020000", # 020000: 시중은행
            "pageNo": 1
        }
        res = requests.get(url, params=params)
        if res.status_code == 200:
            data = res.json()
            base_list = data.get("result", {}).get("baseList", [])
            option_list = data.get("result", {}).get("optionList", [])
            
            # 산업은행의 상품 코드 찾기
            kdb_codes = [b["fin_prdt_cd"] for b in base_list if "산업은행" in b.get("kor_co_nm", "")]
            
            if kdb_codes:
                # 12개월(save_trm == "12") 만기 상품의 최고 기본 금리(intr_rate) 추출
                rates = [
                    opt["intr_rate"] for opt in option_list 
                    if opt["fin_prdt_cd"] in kdb_codes and opt["save_trm"] == "12" and opt["intr_rate"] is not None
                ]
                if rates:
                    kdb_rate = float(max(rates))
    except Exception as e:
        print("금감원 금리 조회 에러:", str(e))
        
    return post_office_rate, kdb_rate

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
            token = get_valid_kis_token()
            if token:
                etf_price = get_tiger_price_kis(token)
        
        # 3. 금감원 API 연동 금리 수집
        post_rate, kdb_rate = get_fss_rates()
        
        # 4. 누적 기록 저장
        seoul_time = datetime.now(pytz.timezone('Asia/Seoul'))
        history_record = {
            "collected_at": seoul_time.strftime("%Y-%m-%d %H:%M:%S"),
            "news_count": len(articles),
            "etf_price": etf_price,
            "post_office_rate": post_rate, 
            "kdb_rate": kdb_rate,         
            "status": "한투+금감원 자동 수집 성공"
        }
        history_collection.insert_one(history_record)
        print("수집 완료:", history_record)
        
    except Exception as e:
        print("자동 수집 에러:", str(e))

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Seoul'))
scheduler.add_job(func=collect_daily_data, trigger="cron", hour=15, minute=30)
scheduler.start()

@app.route('/')
def home():
    return "OK Backend Server with KIS & FSS API!"

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
    return jsonify({"message": "금융 데이터 전면 자동 수집 완료! 화면을 새로고침 하세요."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

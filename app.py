from flask import Flask, jsonify
from flask_cors import CORS
import os
import requests
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
from google import genai
import re

app = Flask(__name__)
CORS(app)

# 환경 변수 설정
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
MONGO_URI = os.environ.get('MONGO_URI')
KIS_APP_KEY = os.environ.get('KIS_APP_KEY')
KIS_APP_SECRET = os.environ.get('KIS_APP_SECRET')
FSS_API_KEY = os.environ.get('FSS_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

try:
    client_mongo = MongoClient(MONGO_URI)
    db = client_mongo['smartu3s_mong']
    news_collection = db['news']
    history_collection = db['history']
except Exception as e:
    print("MongoDB 연결 에러:", e, flush=True)

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
        print("한투 토큰 발급 에러:", e, flush=True)
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
        print("한투 시세 조회 에러:", e, flush=True)
    return 0

def get_fss_rates():
    kdb_rate = 3.5
    post_office_rate = 4.2
    if not FSS_API_KEY:
        return post_office_rate, kdb_rate

    try:
        url = "http://finlife.fss.or.kr/finlifeapi/depositProductsSearch.json"
        params = {"auth": FSS_API_KEY, "topFinGrpNo": "020000", "pageNo": 1}
        res = requests.get(url, params=params)
        if res.status_code == 200:
            data = res.json()
            base_list = data.get("result", {}).get("baseList", [])
            option_list = data.get("result", {}).get("optionList", [])
            
            kdb_codes = [b["fin_prdt_cd"] for b in base_list if "산업은행" in b.get("kor_co_nm", "")]
            if kdb_codes:
                rates = [
                    opt["intr_rate"] for opt in option_list 
                    if opt["fin_prdt_cd"] in kdb_codes and opt["save_trm"] == "12" and opt["intr_rate"] is not None
                ]
                if rates:
                    kdb_rate = float(max(rates))
    except Exception as e:
        print("금감원 금리 조회 에러:", str(e), flush=True)
    return post_office_rate, kdb_rate

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&')

def analyze_with_gemini(articles, etf_price, post_rate, kdb_rate):
    if not GEMINI_API_KEY:
        return "Gemini API 키가 설정되지 않아 분석을 건너뜁니다."
    
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        
        news_titles = "\n".join([f"- {clean_html(a.get('title', ''))}" for a in articles])
        
        prompt = f"""
        당신은 객관적이고 냉철한 금융 분석 AI입니다. 아래 제공된 오늘 수집된 데이터와 경제/IT 뉴스를 바탕으로,
        '원금 방어'와 '안정적인 현금 흐름 창출'이라는 두 가지 핵심 원칙에 따라 분석해 주세요.

        [오늘의 수집 데이터]
        - TIGER 미국배당다우존스 시세: {etf_price}원
        - 우체국 예금 금리: {post_rate}%
        - 산업은행 예금 금리: {kdb_rate}%
        
        [오늘의 핵심 뉴스 제목]
        {news_titles}

        위 정보를 바탕으로 다음 두 가지 항목을 작성해 주세요. 문장은 간결하고 명확하게 작성합니다.
        1. 현재 시장 흐름 요약 (3문장 이내)
        2. 안전 자산(예금)과 투자 자산(배당 ETF) 비율 조절에 대한 직관적인 제안
        """
        
        # 여기서 최신 모델인 1.5-flash를 사용합니다.
        response = ai_client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        return response.text
    except Exception as e:
        error_details = str(e)
        print("Gemini API 호출 에러:", error_details, flush=True)
        return f"🚨 AI 분석 중 오류가 발생했습니다.\n\n[상세 원인]: {error_details}"

def collect_daily_data():
    try:
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
        params = {"query": "경제 IT AI", "display": 5, "sort": "date"}
        response = requests.get(url, headers=headers, params=params)
        articles = response.json().get("items", [])
        if articles:
            news_collection.insert_many(articles)
            
        etf_price = 0
        if KIS_APP_KEY and KIS_APP_SECRET:
            token = get_valid_kis_token()
            if token:
                etf_price = get_tiger_price_kis(token)
        
        post_rate, kdb_rate = get_fss_rates()
        ai_summary = analyze_with_gemini(articles, etf_price, post_rate, kdb_rate)
        
        seoul_time = datetime.now(pytz.timezone('Asia/Seoul'))
        history_record = {
            "collected_at": seoul_time.strftime("%Y-%m-%d %H:%M:%S"),
            "news_count": len(articles),
            "etf_price": etf_price,
            "post_office_rate": post_rate, 
            "kdb_rate": kdb_rate,         
            "ai_analysis": ai_summary,
            "status": "AI 분석 완료"
        }
        history_collection.insert_one(history_record)
        print("수집 및 분석 완료", flush=True)
        
    except Exception as e:
        print("자동 수집 에러:", str(e), flush=True)

scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Seoul'))
scheduler.add_job(func=collect_daily_data, trigger="cron", hour=15, minute=30)
scheduler.start()

@app.route('/')
def home():
    return "OK Backend Server with Gemini AI!"

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

@app.route('/api/data', methods=['GET'])
def get_ai_data():
    try:
        latest_record = history_collection.find_one(sort=[("collected_at", -1)])
        if not latest_record:
            return jsonify({"error": "데이터가 없습니다."}), 404
        latest_record.pop('_id', None)
        return jsonify(latest_record)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/force_collect')
def force_collect():
    collect_daily_data()
    return jsonify({"message": "Gemini AI 분석 및 데이터 수집 완료! 화면을 새로고침 하세요."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

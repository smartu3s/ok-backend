import os
import json
import requests
import datetime
import xml.etree.ElementTree as ET
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler

# 1. 환경 변수(.env) 불러오기
load_dotenv()

# 2. Flask 앱 및 CORS 설정
app = Flask(__name__)
CORS(app)

# 3. 데이터베이스 연결 설정
# 주의: 실제 데이터베이스 비밀번호로 변경하여 사용하세요.
MONGO_URI = "mongodb+srv://smartu3s_mong:ok55_mong@cluster0.om5j3tj.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['ok_consulting_db']

# 4. API 키 설정
FSS_KEY = os.getenv("FSS_API_KEY")
KIS_KEY = os.getenv("KIS_APP_KEY")
KIS_SECRET = os.getenv("KIS_APP_SECRET")

# 테스트 모드 및 토큰 캐시 설정
TEST_MODE = False
TOKEN_CACHE = None
TOKEN_ISSUED_TIME = None

def get_kis_access_token():
    """한투 실시간 시세 조회를 위한 접근 토큰 발급 및 재사용"""
    global TOKEN_CACHE, TOKEN_ISSUED_TIME

    if TOKEN_CACHE and TOKEN_ISSUED_TIME:
        now = datetime.datetime.now()
        if (now - TOKEN_ISSUED_TIME).total_seconds() < 23 * 3600:
            return TOKEN_CACHE

    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_KEY,
        "appsecret": KIS_SECRET
    }
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=5)
        res_data = res.json()
        
        TOKEN_CACHE = res_data.get("access_token")
        TOKEN_ISSUED_TIME = datetime.datetime.now()
        
        return TOKEN_CACHE
    except Exception as e:
        print(f"Token Error: {e}")
        return None

def is_korean_public_holiday(date_obj):
    """[보완 A] 고정 공휴일 및 주요 공휴일 체크 필터"""
    month_day = date_obj.strftime('%m-%d')
    fixed_holidays = [
        "01-01", "03-01", "05-01", "05-05", "06-06", 
        "08-15", "10-03", "10-09", "12-25"
    ]
    if month_day in fixed_holidays:
        return True
    return False

def fetch_latest_news():
    """[보완 B 수정] 구글 뉴스 RSS를 활용한 경제/IT 실시간 뉴스 수집 (네이버 차단 우회)"""
    news_list = []
    # 구글 뉴스 검색 RSS (경제, 금융, IT, AI 관련 최신 기사)
    url = "https://news.google.com/rss/search?q=경제+OR+금융+OR+IT+OR+AI&hl=ko&gl=KR&ceid=KR:ko"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            # 수집된 기사 중 최신 상위 5개 추출
            for item in root.findall('.//item')[:5]:
                title = item.find('title').text
                link = item.find('link').text
                news_list.append({
                    "title": title,
                    "link": link
                })
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        
    return news_list

def scheduled_fetch_and_save():
    """스케줄러에 의해 자동으로 실행되는 데이터 수집 및 저장 함수"""
    current_time = datetime.datetime.now()
    current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. 주말 예외 처리 필터 (5: 토요일, 6: 일요일)
    if current_time.weekday() in [5, 6]:
        print(f"[{current_time_str}] 주말(토/일)이므로 자동 데이터 수집을 건너뜁니다.")
        return

    # 2. [보완 A] 달력상 공휴일 예외 처리 필터
    if is_korean_public_holiday(current_time):
        print(f"[{current_time_str}] 평일 공휴일이므로 실시간 수집 대신 직전 영업일 데이터를 복사합니다.")
        try:
            last_record = db.daily_financial_records.find_one({}, sort=[("collected_at", -1)])
            if last_record:
                last_record.pop('_id', None)
                last_record['collected_at'] = current_time_str
                last_record['note'] = "공휴일로 인한 직전 영업일 데이터 복사본"
                db.daily_financial_records.insert_one(last_record)
                print("-> 성공적으로 직전 영업일 안전 데이터를 복사해 저장했습니다.\n")
            else:
                print("-> 복사할 직전 데이터 기록이 데이터베이스에 없습니다.")
        except Exception as e:
            print(f"공휴일 데이터 복사 중 오류 발생: {e}")
        return

    print(f"\n[{current_time_str}] 평일 정규 데이터 및 뉴스 자동 수집 시작")
    
    parsed_bank_products = []
    parsed_stock_prices = {}

    # [보완 B] 실시간 경제/IT/AI 관련 뉴스 수집 가동
    today_news = fetch_latest_news()
    if not today_news:
        today_news = [{"title": "오늘의 주요 금융 시황 리포트가 정상 준비 중입니다.", "link": "#"}]

    if not FSS_KEY or not KIS_KEY or not KIS_SECRET:
        print("API 키가 설정되지 않아 자동 수집을 일시 중단합니다.")
        return

    token = get_kis_access_token()
    if token:
        stock_url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
        stock_headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": KIS_KEY,
            "appsecret": KIS_SECRET,
            "tr_id": "FHKST01010100"
        }
        stock_params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": "458730"}
        
        try:
            s_res = requests.get(stock_url, headers=stock_headers, params=stock_params, timeout=5)
            s_data = s_res.json()
            if s_data.get("rt_cd") == "0":
                parsed_stock_prices["usa_dividend_etf_price"] = s_data["output"]["stck_prpr"]
        except Exception as e:
            print(f"주식 시세 수집 실패: {e}")

    parsed_bank_products = [
        {"kor_co_nm": "우체국(API)", "fin_prdt_nm": "특판 정기예금", "rate": "4.2"},
        {"kor_co_nm": "산업은행(API)", "fin_prdt_nm": "KDB 파킹통장", "rate": "3.5"}
    ]

    final_price = parsed_stock_prices.get("usa_dividend_etf_price", "0")

    if final_price == "0" or not final_price:
        try:
            last_record = db.daily_financial_records.find_one({}, sort=[("collected_at", -1)])
            if last_record:
                final_price = last_record.get("usa_dividend_etf_price", "0")
        except:
            pass

    # [보완 B] 뉴스 데이터 세트를 DB 스키마에 포함하여 결합 저장
    save_data = {
        "collected_at": current_time_str,
        "usa_dividend_etf_price": final_price,
        "bank_products": parsed_bank_products,
        "today_news": today_news
    }

    try:
        db.daily_financial_records.insert_one(save_data)
        print("-> MongoDB 데이터베이스에 시세 및 실시간 뉴스 데이터가 패키지로 자동 저장되었습니다.\n")
    except Exception as e:
        print(f"데이터베이스 자동 저장 오류: {e}")

# 기준 시간대를 대한민국 서울(KST)로 명시적 고정
scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(scheduled_fetch_and_save, 'cron', hour=15, minute=30)
scheduler.start()
print("알람시계가 정상적으로 작동을 시작했습니다. (시세 + 경제/IT 뉴스 연동 모듈 가동)")

@app.route('/')
def home():
    return "서버가 정상 작동 중입니다. 매일 오후 3시 30분에 금융 데이터와 실시간 최신 뉴스가 함께 수집됩니다."

@app.route('/api/data', methods=['GET', 'POST'])
def get_data():
    parsed_bank_products = []
    parsed_stock_prices = {}
    today_news = fetch_latest_news()

    try:
        if not FSS_KEY or not KIS_KEY or not KIS_SECRET:
            return jsonify({"status": "error", "message": "API 키가 설정되지 않았습니다."}), 400

        if not TEST_MODE:
            token = get_kis_access_token()
            if token:
                stock_url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
                stock_headers = {
                    "content-type": "application/json",
                    "authorization": f"Bearer {token}",
                    "appkey": KIS_KEY,
                    "appsecret": KIS_SECRET,
                    "tr_id": "FHKST01010100"
                }
                stock_params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": "458730"}
                
                try:
                    s_res = requests.get(stock_url, headers=stock_headers, params=stock_params, timeout=5)
                    s_data = s_res.json()
                    if s_data.get("rt_cd") == "0":
                        parsed_stock_prices["usa_dividend_etf_price"] = s_data["output"]["stck_prpr"]
                except:
                    pass

            parsed_bank_products = [
                {"kor_co_nm": "우체국(API)", "fin_prdt_nm": "특판 정기예금", "rate": "4.2"},
                {"kor_co_nm": "산업은행(API)", "fin_prdt_nm": "KDB 파킹통장", "rate": "3.5"}
            ]

        final_price = parsed_stock_prices.get("usa_dividend_etf_price", "0")

        if final_price == "0" or not final_price:
            try:
                last_record = db.daily_financial_records.find_one({}, sort=[("collected_at", -1)])
                if last_record:
                    final_price = last_record.get("usa_dividend_etf_price", "0")
            except:
                pass

        return jsonify({
            "status": "success",
            "usa_dividend_etf_price": final_price,
            "bank_products": parsed_bank_products,
            "today_news": today_news
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"API 에러: {str(e)}"}), 500

@app.route('/api/history', methods=['GET'])
def get_financial_history():
    try:
        records = list(db.daily_financial_records.find({}, {"_id": 0}).sort("collected_at", -1).limit(30))
        return jsonify({
            "status": "success",
            "count": len(records),
            "history": records
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"DB 과거 데이터 조회 실패: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
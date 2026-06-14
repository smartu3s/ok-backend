import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pymongo import MongoClient
import requests
from apscheduler.schedulers.background import BackgroundScheduler

# 1. 환경 변수 로드 (.env 파일 및 서버 환경 변수 읽기)
load_dotenv()

app = Flask(__name__)

# 2. CORS 설정 (프론트엔드와 백엔드 간의 원활한 통신 허용)
CORS(app)

# 3. 데이터베이스 설정 (MongoDB 연결)
# Render 환경 변수에 MONGO_URI가 등록되어 있으면 해당 주소를 사용하고, 없으면 로컬 주소를 사용합니다.
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client['ok_db']  # 사용할 데이터베이스 이름

# 4. 스케줄러 정기 작업 정의 (주식 시세 및 뉴스 수집 로직)
def fetch_stock_and_news_task():
    """
    주기적으로 경제, IT, AI 분야 최신 뉴스 및 주식 시세 데이터를 
    수집하거나 업데이트하는 로직이 들어가는 공간입니다.
    """
    try:
        # 뉴스 및 주식 API 호출 코드 및 DB 저장 로직을 이 내부에 구현합니다.
        print("[스케줄러] 경제/IT/AI 뉴스 및 시세 데이터 동기화 완료")
    except Exception as e:
        print(f"[스케줄러 에러] 데이터 업데이트 중 오류 발생: {e}")

# 5. 알람시계 백그라운드 스케줄러 가동
scheduler = BackgroundScheduler()
# 예시: 매시간 정각마다(hour="*") 정기적으로 기능을 실행하도록 설정
scheduler.add_job(func=fetch_stock_and_news_task, trigger="cron", hour="*")
scheduler.start()

# 서버 시작 시 로그 출력 확인용 문구
print("알람시계가 정상적으로 작동을 시작했습니다. (시세 + 경제/IT 뉴스 연동 모듈 가동)")


# 6. API 라우트(웹 주소 접속 경로) 설정
@app.route('/')
def home():
    """서버가 살아있는지 체크하는 기본 경로"""
    return jsonify({
        "status": "healthy",
        "message": "알람시계 백엔드 서버가 정상적으로 가동 중입니다."
    }), 200

@app.route('/api/news')
def get_latest_news():
    """최신 뉴스 데이터를 데이터베이스나 API를 통해 가져와 앱에 제공하는 경로"""
    # 데이터 조회 로직 구현 가능
    return jsonify({"message": "최신 경제/IT/AI 뉴스 조회 성공"})

@app.route('/api/stocks')
def get_stock_prices():
    """주식 시세 정보를 앱에 제공하는 경로"""
    # 데이터 조회 로직 구현 가능
    return jsonify({"message": "실시간 주식 시세 조회 성공"})


# 7. 서버 실행 설정 (Render 배포용 포트 자동 바인딩)
if __name__ == '__main__':
    # Render 클라우드가 부여하는 포트 번호를 읽어오며, 기본값은 10000 포트를 사용합니다.
    port = int(os.environ.get("PORT", 10000))
    # host="0.0.0.0" 설정을 통해 외부 Render 게이트웨이와 연결 통로를 열어줍니다.
    app.run(host="0.0.0.0", port=port, debug=False)

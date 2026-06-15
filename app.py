from flask import Flask, jsonify
from flask_cors import CORS
import os
import requests
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)

# 1. 환경 변수 불러오기 (네이버 키 및 MongoDB 주소)
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
MONGO_URI = os.environ.get('MONGO_URI')

# 2. MongoDB 연결 설정
try:
    client = MongoClient(MONGO_URI)
    db = client['smartu3s_mong'] # 데이터베이스 선택
    news_collection = db['news'] # 뉴스 저장소
    history_collection = db['history'] # 과거 기록 저장소 추가
except Exception as e:
    print("MongoDB 연결 에러:", e)

@app.route('/')
def home():
    return "OK Backend Server is Running!"

@app.route('/api/news')
def get_news():
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": "경제 IT AI",
        "display": 5,
        "sort": "date"
    }
    
    try:
        # 네이버에서 뉴스 가져오기
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if "items" in data:
            articles = data["items"]
            
            # 수집한 뉴스를 MongoDB에 저장하기
            if articles:
                news_collection.insert_many(articles)
                
                # _id 일반 문자로 변환
                for article in articles:
                    article['_id'] = str(article['_id'])
                
            return jsonify({
                "message": "뉴스 수집 및 데이터베이스 저장 성공!", 
                "saved_count": len(articles),
                "data": articles
            })
        else:
            return jsonify({"error": "뉴스 검색 실패", "details": data})
            
    except Exception as e:
        return jsonify({"error": str(e)})

# ★ 과거 기록(History) 데이터를 화면으로 보내주는 새로운 통로 추가
@app.route('/api/history')
def get_history():
    try:
        # history 컬렉션에서 최근 30개의 데이터를 날짜 역순으로 가져옴
        history_data = list(history_collection.find({}, {'_id': 0}).sort('collected_at', -1).limit(30))
        return jsonify({
            "status": "success",
            "history": history_data
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

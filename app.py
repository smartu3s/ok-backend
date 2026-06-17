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
MONGO_URI = os.environ.get('MONGO_URI')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
# ... (기타 환경변수들 그대로 유지)

# MongoDB 연결
client_mongo = MongoClient(MONGO_URI)
db = client_mongo['smartu3s_mong']
news_collection = db['news']
history_collection = db['history']

# --- 데이터 반환 API (새로 추가됨) ---
@app.route('/api/data', methods=['GET'])
def get_ai_data():
    try:
        latest_record = history_collection.find_one(sort=[("collected_at", -1)])
        if not latest_record:
            return jsonify({"error": "데이터가 없습니다."}), 404
        
        # MongoDB 객체 ID 제거
        latest_record.pop('_id', None)
        return jsonify(latest_record)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- 기존 수집 및 분석 함수들 (기존 코드 그대로 붙여넣기) ---
# [여기에 기존의 get_valid_kis_token, get_tiger_price_kis, analyze_with_gemini 등 기존 함수들을 그대로 유지하세요]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

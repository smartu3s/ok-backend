const express = require('express');
const cors = require('cors');
const axios = require('axios');
require('dotenv').config();

const app = express();
app.use(cors({
    origin: ['https://ok-consulting.kr', 'https://www.ok-consulting.kr'],
    credentials: true
}));

// 발급받은 토큰과 만료 시간을 서버가 기억하도록 변수 생성
let kisAccessToken = null;
let tokenExpiry = null;

// 조회한 주식 가격과 캐시 만료 시간을 기억할 객체 생성
let priceCache = {};

// [함수] KIS API 토큰 발급 및 확인
async function getAccessToken() {
    const now = new Date();
    
    // 이미 발급받은 토큰이 있고, 아직 만료 전이라면 기존 토큰을 재사용합니다.
    if (kisAccessToken && tokenExpiry && now < tokenExpiry) {
        return kisAccessToken;
    }

    console.log("새로운 한국투자증권 토큰을 발급받습니다...");
    const response = await axios.post('https://openapi.koreainvestment.com:9443/oauth2/tokenP', {
        grant_type: 'client_credentials',
        appkey: process.env.KIS_KEY,
        appsecret: process.env.KIS_SECRET
    });

    kisAccessToken = response.data.access_token;
    
    // KIS 토큰은 24시간 유효합니다. 통신 지연 등 오류 방지를 위해 23시간 후 만료되는 것으로 안전하게 설정합니다.
    tokenExpiry = new Date(now.getTime() + 23 * 60 * 60 * 1000);
    
    return kisAccessToken;
}

// [API] 앱에서 주식 가격을 요청할 때 응답하는 주소
app.get('/api/price', async (req, res) => {
    const stockCode = req.query.code; // 예: 458730 (TIGER 미국배당다우존스)
    
    if (!stockCode) {
        return res.status(400).json({ success: false, message: '종목 코드가 필요합니다.' });
    }

    const now = new Date();
    
    // [핵심 캐시 로직] 해당 종목의 가격이 이미 캐시되어 있고 만료 전이라면 KIS를 호출하지 않고 기존 값을 즉시 반환합니다.
    if (priceCache[stockCode] && priceCache[stockCode].expiry > now) {
        console.log(`[${stockCode}] 캐시된 가격 반환: ${priceCache[stockCode].price}원 (KIS 추가 접속 없음)`);
        return res.json({ success: true, price: priceCache[stockCode].price, cached: true });
    }
    
    try {
        // 1. 토큰 가져오기 (알아서 새로 발급받거나 기존 것을 사용함)
        const token = await getAccessToken();
        
        // 2. 캐시가 없거나 만료된 경우에만 해당 종목의 실시간 현재가 조회
        console.log(`[${stockCode}] 캐시가 없거나 만료되어 한국투자증권 API에 직접 최신 가격을 요청합니다...`);
        const response = await axios.get('https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price', {
            headers: {
                'authorization': `Bearer ${token}`,
                'appkey': process.env.KIS_KEY,
                'appsecret': process.env.KIS_SECRET,
                'tr_id': 'FHKST01010100'
            },
            params: {
                FID_COND_MRKT_DIV_CODE: 'J',
                FID_INPUT_ISCD: stockCode
            }
        });

        // 3. 가격 데이터 파싱
        const price = response.data.output.stck_prpr;
        
        // [업그레이드] 새로 가져온 가격을 24시간 동안 기억하도록 캐시에 저장합니다. (하루 1회 통신)
        priceCache[stockCode] = {
            price: price,
            expiry: new Date(now.getTime() + 24 * 60 * 60 * 1000) 
        };
        
        console.log(`[${stockCode}] 현재가 갱신 완료: ${price}원 (캐시 저장 완료)`);
        res.json({ success: true, price: price, cached: false });
        
    } catch (error) {
        console.error("가격 조회 실패:", error);
        res.status(500).json({ success: false, message: '데이터를 가져오지 못했습니다.' });
    }
});

// 서버 실행
app.listen(3000, () => {
    console.log("🚀 백엔드 서버가 3000번 포트에서 정상 실행 중입니다!");
});

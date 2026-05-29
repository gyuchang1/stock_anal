import os
import datetime
import pandas as pd
import FinanceDataReader as fdr
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor, as_completed
import streamlit as st

# ==============================================================================
# 1. 스트림릿 앱 기본 설정 (스마트폰 화면에 맞게 꽉 차게)
# ==============================================================================
st.set_page_config(page_title="나만의 스나이퍼", layout="wide", initial_sidebar_state="collapsed")

# 세션 상태(Session State) 저장소: 앱이 새로고침 되어도 검색 결과를 기억하게 만듭니다.
if 'found_stocks' not in st.session_state:
    st.session_state['found_stocks'] = []
    st.session_state['found_tickers'] = {}
    st.session_state['scan_completed'] = False

DATA_FOLDER = "stock_data"
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

# ==============================================================================
# 2. 증분 업데이트 및 스캔 엔진 (기존과 동일)
# ==============================================================================
def update_and_load_data(ticker, start_year='2020-01-01'):
    file_path = f"{DATA_FOLDER}/{ticker}.csv"
    today = datetime.datetime.today()
    
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        if df.empty:
            os.remove(file_path)
            return update_and_load_data(ticker, start_year)
            
        last_date = df.index[-1]
        if last_date.date() >= today.date():
            return df
            
        next_day = (last_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        new_df = fdr.DataReader(ticker, next_day)
        
        if not new_df.empty:
            df = pd.concat([df, new_df])
            df = df[~df.index.duplicated(keep='last')]
            df.to_csv(file_path)
        return df
    else:
        df = fdr.DataReader(ticker, start_year)
        if not df.empty:
            df.to_csv(file_path)
        return df

def analyze_stock(ticker, name):
    try:
        df = update_and_load_data(ticker, '2020-01-01')
        if df is None or len(df) < 500: return None
            
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA240'] = df['Close'].rolling(window=240).mean()
        df['MA480'] = df['Close'].rolling(window=480).mean()
        df = df.dropna()
        
        if len(df) < 2: return None
            
        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        
        is_safe_trend = today['MA240'] > today['MA480']
        is_ma20_rising = today['MA20'] > yesterday['MA20']
        gap_from_ma20 = (today['Close'] - today['MA20']) / today['MA20']
        is_near_ma20 = 0 <= gap_from_ma20 <= 0.02 
        is_red_candle = today['Close'] > today['Open']
        is_volume_spiked = today['Volume'] > (yesterday['Volume'] * 1.5)
        
        body = abs(today['Close'] - today['Open'])
        lower_tail = min(today['Open'], today['Close']) - today['Low']
        #is_hammer = lower_tail >= (body * 2)
        
        if is_safe_trend and is_ma20_rising and is_near_ma20 and is_red_candle and is_volume_spiked: #and is_hammer:
            return ('pullback', name, ticker) 
        return None
    except Exception:
        return None

# ==============================================================================
# 3. 앱 화면 구성 (UI)
# ==============================================================================
st.title("🎯 주식 스나이퍼 대시보드")
st.markdown("**조건:** 240일 대세상승 ➕ 20일선 눌림목 ➕ 거래량 1.5배 )#➕ 망치형 캔들")

# 스캔 버튼 (스마트폰에서 터치하기 좋게 큼직하게 나옵니다)
if st.button("🚀 오늘 장 스캔 시작하기", use_container_width=True):
    kospi_list = fdr.StockListing('KOSPI')
    tickers = kospi_list['Code'].tolist()
    names = kospi_list['Name'].tolist()
    
    total_count = len(tickers)
    completed = 0
    pullback_stocks = []
    found_tickers = {}
    
    # 앱 화면에 진행률 바(Progress Bar) 표시
    progress_text = "종목 데이터를 스캔하고 있습니다..."
    my_bar = st.progress(0, text=progress_text)
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_stock = {executor.submit(analyze_stock, t, n): n for t, n in zip(tickers, names)}
        for future in as_completed(future_to_stock):
            completed += 1
            # 진행률 업데이트
            percent_complete = int((completed / total_count) * 100)
            my_bar.progress(percent_complete, text=f"스캔 중... {completed}/{total_count} 완료")
            
            result = future.result()
            if result:
                status, stock_name, ticker = result
                found_tickers[stock_name] = ticker
                if status == 'pullback':
                    pullback_stocks.append(stock_name)
                    
    # 스캔 결과를 세션에 저장
    st.session_state['found_stocks'] = pullback_stocks
    st.session_state['found_tickers'] = found_tickers
    st.session_state['scan_completed'] = True
    
    my_bar.empty() # 스캔이 끝나면 진행률 바 숨기기
    st.success("✅ 스캔이 완료되었습니다!")

st.divider() # 가로선 긋기

# ==============================================================================
# 4. 차트 렌더링 (모바일 최적화)
# ==============================================================================
if st.session_state['scan_completed']:
    found_stocks = st.session_state['found_stocks']
    
    if not found_stocks:
        st.warning("오늘은 모든 조건을 만족하는 종목이 없습니다. 푹 쉬세요! ☕")
    else:
        # 드롭다운 메뉴로 종목 선택 (스마트폰 터치 친화적)
        selected_stock = st.selectbox("📊 차트를 확인할 종목을 선택하세요:", found_stocks)
        
        target_ticker = st.session_state['found_tickers'][selected_stock]
        chart_df = update_and_load_data(target_ticker, '2020-01-01')
        
        chart_df['MA20'] = chart_df['Close'].rolling(window=20).mean()
        chart_df['MA60'] = chart_df['Close'].rolling(window=60).mean()
        chart_df['MA240'] = chart_df['Close'].rolling(window=240).mean()
        chart_df['MA480'] = chart_df['Close'].rolling(window=480).mean()
        chart_df = chart_df.dropna()
        
        # 선택한 '단 1개'의 종목 차트만 빠르고 가볍게 그립니다.
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        
        fig.add_trace(go.Candlestick(x=chart_df.index, open=chart_df['Open'], high=chart_df['High'], low=chart_df['Low'], close=chart_df['Close'], name='주가'), row=1, col=1)
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['MA20'], line=dict(color='green', width=1.5), name='20일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['MA60'], line=dict(color='purple', width=1.5), name='60일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['MA240'], line=dict(color='orange', width=2.5), name='240일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['MA480'], line=dict(color='blue', width=2.5), name='480일선'), row=1, col=1)
        
        colors = ['red' if row['Close'] >= row['Open'] else 'blue' for idx, row in chart_df.iterrows()]
        fig.add_trace(go.Bar(x=chart_df.index, y=chart_df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

        fig.update_layout(
            title=f"📈 {selected_stock} 종합 분석",
            yaxis_title='주가 (원)', yaxis2_title='거래량', xaxis2_title='날짜',
            xaxis_rangeslider_visible=False, template='plotly_white', height=600,
            margin=dict(l=10, r=10, t=50, b=10) # 모바일 화면 낭비를 줄이기 위한 여백 최소화
        )
        
        # 만들어진 차트를 앱 화면에 렌더링
        st.plotly_chart(fig, use_container_width=True)

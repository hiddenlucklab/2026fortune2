import streamlit as st 
import json
import re 
import os # <<< NameError 해결: os 모듈 추가
from datetime import datetime, date, time as dt_time
from typing import Dict, List
import google.generativeai as genai 
from math import floor # floor 함수를 명시적으로 임포트

# 🔧 2026년 리포트 생성용 상수 (현재 시스템 날짜 대신 사용)
TARGET_YEAR = 2026

# ==========================================================================
# 🛑 [START] 모듈 로드 및 API 키 로드 로직 (오류 발생 부분 수정)
# ==========================================================================

# 💡 Tier Import와 API 키 로직을 하나의 안전한 try 블록 안에 배치합니다.
try:
    # ----------------------------------------------------------------------
    # 1. TIER IMPORT (모듈화된 파일에서 핵심 로직을 가져옵니다.)
    # ----------------------------------------------------------------------
    from saju_data import TEN_GAN_PERSONA
    from saju_engine_final import SajuEngine, TIME_ZONE, calculate_pillar_sipsin
    from analysis_core_final import (
        get_final_ai_prompt, load_clinical_data, 
        analyze_ai_report, get_system_instruction, calculate_sewoon_sipsin
    )
    from report_generator import generate_report_html, generate_free_report_html, generate_premium_report_html
    
    # ----------------------------------------------------------------------
    # 2. API 키 로드 로직 (환경 변수 우선)
    # ----------------------------------------------------------------------
    
    # Codespaces Secrets (환경 변수)에서 GOOGLE_API_KEY 또는 GEMINI_API_KEY를 시도
    api_key_from_env = os.environ.get("GOOGLE_API_KEY")
    if not api_key_from_env:
        api_key_from_env = os.environ.get("GEMINI_API_KEY")

    api_key = api_key_from_env

    # 2순위: config.py 파일 (로컬 환경에서만 사용)
    CONFIGURED_API_KEY = None
    if not api_key:
        try:
            from config import GEMINI_API_KEY as CONFIGURED_API_KEY
            api_key = CONFIGURED_APIKEY
        except ImportError:
            pass # config.py 없으면 무시

    # 3순위: Streamlit Secrets 파일 (.streamlit/secrets.toml) 확인
    if not api_key:
        try:
            api_key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            api_key = ""
            
    # 최종적으로 키가 확보되었다면, session_state에 저장하고 SDK를 초기화합니다.
    if api_key:
        st.session_state['api_key'] = api_key
        # 🔑 Gemini SDK 초기화 (여기가 키를 사용하는 핵심 부분)
        genai.configure(api_key=api_key) 
    
    MODULES_READY = True

except ImportError as e:
    # 모듈 임포트 실패 시 (SyntaxError가 아닌 모듈 없음 오류만 여기서 잡힘)
    CONFIGURED_API_KEY = None
    st.error(f"❌ 아키텍처 파일 로드 실패: {e}. analysis_core_final.py에 analyze_ai_report, get_system_instruction 함수를 추가했는지 확인해주세요.")
    MODULES_READY = False

# ==========================================================================
# 🛑 [END] 모듈 로드 및 API 키 로드 로직
# ==========================================================================


# --------------------------------------------------------------------------
# UI 헬퍼 클래스 (Tier 1) - 오행 색상 및 간지 맵핑
# --------------------------------------------------------------------------
class UIEngineHelper:
    """Streamlit UI 표시를 위한 헬퍼 클래스"""
    def __init__(self):
        self.jiji_o_heng_map = {'寅': 'wood', '卯': 'wood', '辰': 'earth', '巳': 'fire', '午': 'fire', '未': 'earth', '申': 'metal', '酉': 'metal', '戌': 'earth', '亥': 'water', '子': 'water', '丑': 'earth', '甲':'wood', '乙':'wood', '丙':'fire', '丁':'fire', '戊':'earth', '己':'earth', '庚':'metal', '辛':'metal', '壬':'water', '癸':'water'}
        self.color_map = {'wood':'#388E3C', 'fire':'#D32F2F', 'earth':'#FBC02D', 'metal':'#757575', 'water':'#1976D2'}
        self.hanja_to_kr = {'甲':'갑', '乙':'을', '丙':'병', '丁':'정', '戊':'무', '己':'기', '庚':'경', '辛':'신', '壬':'임', '癸':'계', '子':'자', '丑':'축', '寅':'인', '卯':'묘', '辰':'진', '巳':'사', '午':'오', '未':'미', '申':'신', '酉':'유', '戌':'술', '亥':'해'}

    def get_color_class(self, char: str) -> str:
        oheng = self.jiji_o_heng_map.get(char)
        return self.color_map.get(oheng, '#555555')
    
    def get_kr(self, char: str) -> str:
        return self.hanja_to_kr.get(char, char)
    
UI_ENG = UIEngineHelper()


# 🚨 [최종 수정] Session State 초기화 로직을 Streamlit 스크립트의 최상단으로 이동합니다.
if 'api_key' not in st.session_state: st.session_state.api_key = "" # API 키 세션 상태 추가
if 'events_text' not in st.session_state: st.session_state.events_text = ""
if 'last_result' not in st.session_state: st.session_state.last_result = None
if 'manse_info' not in st.session_state: st.session_state.manse_info = None
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'curr_age' not in st.session_state: st.session_state.curr_age = None
if 'report_package_data' not in st.session_state: st.session_state.report_package_data = None
if 'customer_info' not in st.session_state: st.session_state.customer_info = {}


# --------------------------------------------------------------------------
# UI 렌더링 함수
# --------------------------------------------------------------------------
def render_expert_analysis(details: Dict, qa: Dict, final_message: str):
    """전문가용 상세 분석 내용을 Streamlit 대시보드에 표시합니다."""
    # (기존 UI 렌더링 로직 유지)
    sections = [
        ("💰 재물운 (Wealth Luck)", 'wealth_luck'), ("👔 직업/사업운 (Career/Business)", 'career_luck'), 
        ("💖 애정/가정운 (Love/Family)", 'love_family_luck'), ("🏠 변동운 (Change/Movement)", 'change_luck'), 
        ("🏥 건강 조언 (Health Advice)", 'health_advice')
    ]
    st.markdown("### [1] AI 심층 분석 (에세이 원본 - 전문가용)")
    st.markdown("""<div style="padding: 20px; border-radius: 10px; background: #F8FCFB;">""", unsafe_allow_html=True)
    for title, key in sections:
        content = details.get(key, "분석 데이터 없음")
        st.markdown(f"{title}")
        st.text(content.replace('\\n', '\n')) 
        st.markdown("---")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### [2] Solution Q&A")
    st.markdown("""<div style="padding: 20px; border-radius: 10px; background: #FFFDF7;">""", unsafe_allow_html=True)
    if qa.get('q1') and qa.get('a1'):
        st.markdown(f"Q1. {qa['q1']}")
        st.info(qa['a1'].replace('\\n', '\n'))
    if qa.get('q2') and qa.get('a2'):
        st.markdown(f"Q2. {qa['q2']}")
        st.info(qa['a2'].replace('\\n', '\n'))
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown(f"### [3] 최종 메시지")
    st.markdown(f"_{final_message.replace('\\n', '\n')}_")


def render_customer_analysis(customer_details: Dict):
    """고객용 쉬운 말 분석을 Streamlit에 표시합니다."""
    # (기존 UI 렌더링 로직 유지)
    sections = [
        ("💰 재물운 (쉬운 말)", 'wealth_luck'), ("👔 직업/사업운 (쉬운 말)", 'career_luck'), 
        ("💖 애정/가정운 (쉬운 말)", 'love_family_luck'), ("🏠 변동운 (쉬운 말)", 'change_luck'),
    ]
    st.markdown("### 5-1. 🍀 고객용 쉬운 말 분석 (HTML 리포트용)")
    
    for title, key in sections:
        content = customer_details.get(key, "분석 데이터 없음")
        st.markdown(f"{title}")
        st.text(content.replace('\\n', '\n')) 
        st.markdown("---")
    st.markdown("</div>", unsafe_allow_html=True)


def render_saju_pillars(manse_info: Dict, ten_gods_array: List[Dict], ui_eng: UIEngineHelper):
    """사주팔자 4주를 UI에 렌더링합니다."""
    # (기존 UI 렌더링 로직 유지)
    pillars_list = [
        {'title': '시주(말년)', 'ganji': manse_info['시주'], 'ten': ten_gods_array[3]}, 
        {'title': '일주(본인)', 'ganji': manse_info['일주'], 'ten': ten_gods_array[2]}, 
        {'title': '월주(청년)', 'ganji': manse_info['월주'], 'ten': ten_gods_array[1]}, 
        {'title': '년주(초년)', 'ganji': manse_info['년주'], 'ten': ten_gods_array[0]}   
    ]
    cols = st.columns(4)
    for i, p in enumerate(pillars_list):
        stem, branch = p['ganji'][0], p['ganji'][1]
        stem_color, branch_color = ui_eng.get_color_class(stem), ui_eng.get_color_class(branch)
        with cols[i]:
            st.markdown(f"""
                <div style="text-align: center;">
                    <span style="font-size: 0.8em; color: #555;">{p['ten']['stem_ten_god']}</span> 
                    <div style="background-color: {stem_color}; color: white; padding: 5px 0; border-radius: 5px 5px 0 0; margin-top: 2px;">
                        <span style="font-size: 1.8em; font-weight: bold;">{stem}</span>
                    </div>
                    <div style="background-color: {branch_color}; color: white; padding: 5px 0; border-radius: 0 0 5px 5px; margin-top: 0px;">
                        <span style="font-size: 1.8em; font-weight: bold;">{branch}</span>
                    </div>
                    <span style="font-size: 0.8em; color: #555;">{p['ten']['branch_ten_god']}</span>
                    <div style="font-size: 0.9em; color: #999; margin-top: 5px;">{p['title']}</div>
                </div>
            """, unsafe_allow_html=True)


def render_daewoon_sewoon(dw: Dict, manse_info: Dict, curr_age: int):
    """대운 및 세운 흐름을 UI에 렌더링합니다."""
    # (기존 UI 렌더링 로직 유지)
    day_master = manse_info['일주'][0]
    st.markdown("### 2. 대운 흐름 및 세운")
    st.info(f"{dw['대운수']}대운 ({dw['순행_역행']}, 현재 나이: {curr_age}세)")
    
    dw_cols = st.columns(len(dw['대운_간지_배열']))
    
    for i, d in enumerate(dw['대운_간지_배열']):
        is_active = (curr_age >= d['age'] and curr_age < d['age'] + 10)
        sipsin_info = calculate_sewoon_sipsin(day_master, d['ganji'])
        
        active_style = f"border:2px solid {UI_ENG.get_color_class(day_master)}; background:#F8FCFB;" if is_active else "border:1px solid #eee; background:#fff;"
        stem_color = UI_ENG.get_color_class(d['ganji'][0])
        branch_color = UI_ENG.get_color_class(d['ganji'][1])
        
        with dw_cols[i]:
            st.markdown(f"""
                <div style='text-align:center; padding:5px; border-radius:10px; {active_style}'>
                    <div style='font-size:0.8rem; color:#888;'>{d['age']}세</div>
                    <div style='font-size:0.8rem; color:#555;'>{sipsin_info['stem_ten_god']}</div>
                    <div style='font-size:1.2rem; font-weight:bold;'>
                        <span style='color:{stem_color}'>{d['ganji'][0]}</span>
                        <span style='color:{branch_color}'>{d['ganji'][1]}</span>
                    </div>
                    <div style='font-size:0.8rem; color:#555;'>{sipsin_info['branch_ten_god']}</div>
                </div>
            """, unsafe_allow_html=True)

    st.markdown("#### 2-1. 현재 대운의 세운 흐름 (Yearly Flow)")
    
    current_dw_start_age = [d['age'] for d in dw['대운_간지_배열'] if curr_age >= d['age'] and curr_age < d['age'] + 10]
    dw_start_age = current_dw_start_age[0] if current_dw_start_age else dw['대운_간지_배열'][0]['age']
    # 🔧 수정: datetime.now().year 대신 TARGET_YEAR 사용
    current_dw_start_year = TARGET_YEAR - (curr_age - dw_start_age)
             
    engine = SajuEngine()
    sewoon_list = engine.get_sewoon(current_dw_start_year, 10)
    sewoon_cols = st.columns(10)
    
    for i, sw in enumerate(sewoon_list):
        year = sw['year']
        year_ganji = sw['ganji']
        sewoon_sipsin = calculate_sewoon_sipsin(day_master, year_ganji)

        # 🔧 수정: datetime.now().year 대신 TARGET_YEAR 사용
        is_current_year = year == TARGET_YEAR
        year_style = "color:#D32F2F; font-weight:bold;" if is_current_year else "color:#555;"
        
        with sewoon_cols[i]:
            st.markdown(f"""
                <div style="text-align: center; border-radius: 5px; padding: 5px 0; background: {'#FFF5EB' if is_current_year else '#f9f9f9'};">
                    <div style="font-size: 0.7rem; color: #999;">{year}</div>
                    <div style="font-size: 0.8rem; {year_style}">{sewoon_sipsin['stem_ten_god']}</div>
                    <div style="font-size: 1.1rem; font-weight: bold; {year_style}">{year_ganji}</div>
                    <div style="font-size: 0.8rem; {year_style}">{sewoon_sipsin['branch_ten_god']}</div>
                </div>
            """, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 메인 애플리케이션 함수
# --------------------------------------------------------------------------
def render_app():
    if not MODULES_READY:
        return
        
    st.set_page_config(page_title="희구소 운영 시스템", page_icon="🔮", layout="wide")
    
    # --- 파비콘 수정 로직 (이미지 URL 반영) ---
    favicon_url = "https://i.ibb.co/vxZfjJvJ/1.png"
    st.markdown(
        f"""
        <link rel="icon" href="{favicon_url}">
        """,
        unsafe_allow_html=True,
    )
    
    # 🔑 키 로드 (Session State에서 가져옵니다)
    api_key = st.session_state.get('api_key')

    # 🚨 API 키 체크는 여기서 최종적으로 확인합니다.
    if not api_key:
        st.error("❌ Gemini API 키가 설정되지 않아 분석을 진행할 수 없습니다.")
    
    # --- CSS 스타일 ---
    st.markdown("""
    <style>
        .stButton>button { width: 100%; border-radius: 10px; height: 50px; font-weight: bold; }
        .summary-block { border: 1px solid #B0E0D5; border-radius: 15px; padding: 15px; margin-bottom: 15px; background-color: #F8FCFB; }
        .summary-block h4 { color: #FFCBA4; margin-bottom: 5px; font-size: 1.1rem; }
        .summary-block p { font-size: 0.95rem; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

    # --- Sidebar: 사용자 입력 ---
    with st.sidebar:
        st.header("🔮 희구소 입력 콘솔")
        name = st.text_input("내담자명", "고객")
        gender = st.radio("성별", ["여성", "남성"], horizontal=True)
        b_date = st.date_input(
            "생년월일", 
            datetime(1985, 10, 29),
            min_value=date(1920, 1, 1),
            max_value=date(2026, 12, 31)
        )
        
        # 정확한 시:분 입력 (절입 시각 판단을 위해 필수)
        st.markdown("태어난 시간")
        time_unknown = st.checkbox("⏰ 시간 모름", value=False)
        
        if time_unknown:
            # 시간 모름 선택 시 12:00(오시 정중앙)으로 설정
            target_time = dt_time(12, 0)
            st.info("💡 시간을 모르면 12:00(오시)로 계산합니다. 시주(時柱)는 참고용이며, 년·월·일주는 정확합니다.")
        else:
            time_col1, time_col2 = st.columns(2)
            with time_col1:
                b_hour = st.selectbox("시", list(range(0, 24)), index=10, format_func=lambda x: f"{x:02d}시")
            with time_col2:
                b_minute = st.selectbox("분", list(range(0, 60)), index=15, format_func=lambda x: f"{x:02d}분")
            target_time = dt_time(b_hour, b_minute)
            
            # 🕰️ 수정: 참고용 시진 표시 (정확한 2시간 단위 시진 반영)
            sijin_names = ["자시", "축시", "인시", "묘시", "진시", "사시", "오시", "미시", "신시", "유시", "술시", "해시"]
            
            # 현재 시를 분까지 합산하여 2시간(120분) 단위로 나눕니다.
            total_minutes = b_hour * 60 + b_minute
            
            # 23시 30분을 0시 0분으로 가정하고 전체 시간을 30분 앞당겨 계산
            # (명리학에서 자시는 23:30부터 시작하므로, 30분을 빼서 보정)
            adjusted_minutes = total_minutes - 30 
            if adjusted_minutes < 0:
                adjusted_minutes += 24 * 60 # 00:00 ~ 00:29 (전날의 해시)를 23:30 ~ 23:59로 처리
            
            # 2시간 단위 시진 인덱스 계산 (120분 = 1시진)
            sijin_idx = floor(adjusted_minutes / 120) % 12
            
            # 명리학 지지 12자 (자, 축, 인, 묘...)
            sijin_kr_hanja = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
            
            current_sijin = f"{sijin_names[sijin_idx]}({sijin_kr_hanja[sijin_idx]}時)"
            st.caption(f"📍 해당 시진: {current_sijin}")

        
        st.markdown("---")
        job = st.selectbox("직업", ["직장인", "사업가", "프리랜서", "주부", "학생", "무직"])
        marital = st.selectbox("결혼 상태", ["미혼", "기혼", "돌싱"])
        has_children = st.checkbox("자녀 있음", value=False)
        
        st.markdown("---")
        topics_options = ["총운", "2026신년운세", "재물운", "사업운", "직장운", "연애운", "건강운", "이동/이사운", "학업/시험운"]
        topics = st.multiselect("상담 주제", topics_options, default=["2026신년운세"])
        
        q1 = st.text_area("궁금한 점 1 (필수)", placeholder="예: 2026년에 사업 확장을 해도 될까요?")
        q2 = st.text_area("궁금한 점 2 (선택)", placeholder="예: 재물운이 가장 좋은 월은 언제인가요?")
        
        st.markdown("---")
        with st.expander("📜 임상 사건 일괄 입력", expanded=False):
            st.session_state.events_text = st.text_area(
                "내담자 인생의 주요 사건(년도: 사건)을 입력하세요. (AI 분석의 정확도 향상)", 
                st.session_state.events_text, 
                height=100, 
                placeholder="예: 2005 첫 직장 입사, 2012 결혼, 2020 이직 후 승진"
            )
        
        btn = st.button("🚀 분석 시작")


    # --- Main Dashboard ---
    st.title("Hidden Luck Lab : 희구소")
    st.markdown("#### 🎓 운영자 전용 대시보드")
    
    # 키 로드 상태를 체크합니다.
    if not st.session_state.get('api_key'):
        st.error("❌ Gemini API 키가 설정되지 않아 분석을 진행할 수 없습니다.")
        
    if btn:
        if not q1 or not topics:
            st.error("상담 주제와 질문 1은 필수 입력 항목입니다.")
            return
            
        if not st.session_state.get('api_key'):
             return

        # 1. 필수 변수 정의 및 나이 계산
        try:
             # TIME_ZONE은 analysis_core_final에서 import 되었음.
             # 출생 시각에 TIME_ZONE 정보를 명시적으로 붙여 Aware 객체로 만듭니다.
             dt_with_time = datetime.combine(b_date, target_time).replace(tzinfo=TIME_ZONE)
        except Exception as e:
             st.error(f"시간대 정보 결합 오류. Date/Time 입력 및 analysis_core_final.py의 TIME_ZONE 설정을 확인하세요: {e}")
             return
             
        # 🔧 한국식 세는 나이 계산 (태어나자마자 1살, 새해가 되면 +1)
        # 예: 1985년 10월 29일생 → 2025년 현재 41세 (2025 - 1985 + 1)
        today = date.today()
        curr_age = today.year - b_date.year + 1 # 한국 나이: 출생연도와 현재연도 차이 + 1
        
        gender_code = 'F' if gender == '여성' else 'M'
        st.session_state.curr_age = curr_age
        
        # 고객 정보 저장 (분석 완료 메시지용)
        st.session_state.customer_info = {
            "name": name,
            "gender": gender,
            "birth_date": b_date,
            "birth_time": target_time,
            "time_unknown": time_unknown if 'time_unknown' in dir() else False
        }

        # 2. 분석 실행
        with st.spinner("AI가 운명을 분석 중입니다..."):
            eng = SajuEngine() 
            
            try:
                # 2-1. 만세력 데이터 생성 (십성 배열 포함)
                manse_info = eng.generate_saju_palja(birth_dt=dt_with_time, gender=gender_code)
                st.session_state.manse_info = manse_info
                
                daewoon_info = manse_info['대운_정보']
                
                profile_data = {"job": job, "marital": marital, "children": has_children}
                full_q = f"주제:{','.join(topics)}, Q1:{q1}, Q2:{q2 if q2 else '없음'}"
                
                # 2-2. AI 분석 요청
                api_key = st.session_state['api_key'] # 🔑 세션에서 키를 다시 가져옴
                result_json = analyze_ai_report(manse_info, daewoon_info, full_q, profile_data, st.session_state.events_text, eng, api_key) 
                
                # 2-3. 결과 저장 및 HTML 패키지 구성
                st.session_state.last_result = result_json 
                
                dw_list_for_html = [{ "age": d['age'], "ganji": d['ganji'] } for d in daewoon_info['대운_간지_배열']]
                
                # 🔧 수정: 현재 대운 시작 연도 계산 - TARGET_YEAR(2026) 기준
                current_dw_start_year = TARGET_YEAR - (curr_age - dw_list_for_html[0]['age'])
                for d in dw_list_for_html:
                    if curr_age >= d['age'] and curr_age < d['age'] + 10:
                        current_dw_start_year = TARGET_YEAR - (curr_age - d['age'])
                        break
                        
                # 세운 10년치 정보 생성 (HTML 템플릿에 주입)
                sewoon_10yr_list = eng.get_sewoon(current_dw_start_year, 10)
                sewoon_ganji_map = {sw['year']: sw['ganji'] for sw in sewoon_10yr_list}
                
                day_master = manse_info['일주'][0]
                sewoon_sipsin_map = {y: calculate_sewoon_sipsin(day_master, g) for y, g in sewoon_ganji_map.items()}

                # 최종 리포트 패키지 구성
                st.session_state.report_package_data = {
                    "manse": {
                        "pillars": [
                            {"stem": manse_info['년주'][0], "branch": manse_info['년주'][1]},
                            {"stem": manse_info['월주'][0], "branch": manse_info['월주'][1]},
                            {"stem": manse_info['일주'][0], "branch": manse_info['일주'][1]},
                            {"stem": manse_info['시주'][0], "branch": manse_info['시주'][1]}
                        ],
                        "ten_gods_result": manse_info['십성_결과_배열'], 
                        "day_master": manse_info['일주'][0],
                        "customer_name": name, # 🔧 고객명 추가
                        "curr_age": curr_age, 
                        "daewoon_list": dw_list_for_html,
                        "current_dw_start_year": current_dw_start_year,
                        "daewoon_sipsin": {d['ganji']: calculate_sewoon_sipsin(day_master, d['ganji']) for d in dw_list_for_html},
                        "sewoon_ganji": sewoon_ganji_map,
                        "sewoon_sipsin_map": sewoon_sipsin_map
                    },
                    "analysis": result_json
                }
                st.session_state.chat_history.append({"role": "initial_query", "query": full_q, "response": result_json})

            except Exception as e:
                st.error(f"만세력/AI 분석 중 치명적인 오류 발생: {e}")
                return
            
            st.rerun()

    # --- 분석 결과 표시 영역 (여기는 render_app() 함수 외부입니다) ---
    # st.session_state는 스크립트 최상단에서 이미 초기화되었으므로 안전합니다.
    if st.session_state.last_result:
        result_json = st.session_state.last_result
        manse_info = st.session_state.manse_info
        curr_age = st.session_state.curr_age
        dw = manse_info['대운_정보']
        
        # AI 응답 실패 체크
        if "❌" in result_json.get('summary_card', {}).get('keyword', ''):
            st.error(f"AI 분석 실패: {result_json.get('summary_card', {}).get('keyword')}")
            st.code(result_json.get('raw_response', 'AI에서 JSON이 반환되지 않았습니다.'))
            st.stop()
            
        # 고객 정보 및 대운수 상세 표시
        cust = st.session_state.customer_info
        dw_precise = dw.get('대운수_정밀', dw['대운수'])
        time_str = "시간모름" if cust.get('time_unknown') else f"{cust['birth_time'].hour:02d}:{cust['birth_time'].minute:02d}"
        
        st.success(f"""분석 완료! 
        👤 {cust['name']} ({cust['gender']}) | 📅 {cust['birth_date']} {time_str}
        📜 만세력 원국: 年:{manse_info['년주']} / 月:{manse_info['월주']} / 日:{manse_info['일주']} / 時:{manse_info['시주']}
        🔮 대운수: {dw_precise}세 ({dw['순행_역행']})""")
        
        # --- 1. 사주 명식 상세 (UI) ---
        st.markdown("### 1. 사주 명식 상세")
        st.markdown(f"**일간:** <span style='font-size:1.2rem; color:{UI_ENG.get_color_class(manse_info['일주'][0])}'>{manse_info['일주'][0]}</span>", unsafe_allow_html=True)
        render_saju_pillars(manse_info, manse_info['십성_결과_배열'], UI_ENG)
        
        st.markdown("---")

        # --- 2. 대운 흐름 및 세운 (UI) ---
        render_daewoon_sewoon(dw, manse_info, curr_age)
        
        st.markdown("---")

        # --- 3. AI 분석 요약 (운영자 핵심 정보) ---
        st.markdown("### 3. AI 분석 요약 (운영자 핵심 정보)")
        summary = result_json.get('summary_card', {})
        st.markdown(f"""
        <div class='summary-block'>
            <h4>✨ 2026년 핵심 테마 (고객 카드 문구)</h4>
            <p><strong>키워드:</strong> {summary.get('keyword', '분석 불가')}</p>
            <p><strong>Best Month:</strong> {summary.get('best_month', 'N/A')}</p>
            <p><strong>Risk:</strong> {summary.get('risk', 'N/A')}</p>
            <p><strong>Action:</strong> {summary.get('action_item', 'N/A')}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")

        # --- 4. 🎓 전문가 상세 분석 (에세이 원본 전체) ---
        details = result_json.get('detailed_analysis', {})
        qa_sec = result_json.get('qa_section', {})
        final_msg = result_json.get('final_message', '최종 메시지 없음')
        
        render_expert_analysis(details, qa_sec, final_msg)
        
        st.markdown("---")

        # --- 5. 고객용 쉬운 말 분석 렌더링 추가 ---
        customer_details = result_json.get('customer_analysis', {})
        render_customer_analysis(customer_details)

        st.markdown("---")
        
        # --- 5-2. AI 분석 결과 검토 및 수정 (신규) ---
        st.markdown("---")
        st.markdown("### 5-2. ✏️ AI 분석 결과 검토 및 수정")
        st.info("💡 **고객 리포트 출력 전에 AI 분석 내용을 검토하고 수정할 수 있습니다.**")
        
        with st.expander("📝 텍스트 내용 수정하기 (클릭하여 펼치기)", expanded=False):
            st.markdown("#### 1️⃣ 요약 카드")
            
            edited_keyword = st.text_area(
                "한줄 요약 키워드",
                value=st.session_state.report_package_data['analysis']['summary_card']['keyword'],
                height=80,
                key='edit_keyword'
            )
            
            col1, col2 = st.columns(2)
            with col1:
                edited_best_month = st.text_input(
                    "최고의 달",
                    value=st.session_state.report_package_data['analysis']['summary_card']['best_month'],
                    key='edit_best_month'
                )
            with col2:
                edited_risk = st.text_input(
                    "위험 신호",
                    value=st.session_state.report_package_data['analysis']['summary_card']['risk'],
                    key='edit_risk'
                )
            
            edited_action_item = st.text_area(
                "액션 아이템",
                value=st.session_state.report_package_data['analysis']['summary_card']['action_item'],
                height=80,
                key='edit_action_item'
            )
            
            st.markdown("---")
            st.markdown("#### 2️⃣ 상세 분석")
            
            edited_wealth = st.text_area(
                "💰 재물운 분석",
                value=st.session_state.report_package_data['analysis']['detailed_analysis']['wealth_luck'],
                height=150,
                key='edit_wealth'
            )
            
            edited_career = st.text_area(
                "💼 경력/커리어 분석",
                value=st.session_state.report_package_data['analysis']['detailed_analysis']['career_luck'],
                height=150,
                key='edit_career'
            )
            
            edited_love = st.text_area(
                "❤️ 사랑/가족 관계 분석",
                value=st.session_state.report_package_data['analysis']['detailed_analysis']['love_family_luck'],
                height=150,
                key='edit_love'
            )
            
            edited_change = st.text_area(
                "🔄 변화/이동 운세",
                value=st.session_state.report_package_data['analysis']['detailed_analysis']['change_luck'],
                height=150,
                key='edit_change'
            )
            
            edited_health = st.text_area(
                "🏥 건강 조언",
                value=st.session_state.report_package_data['analysis']['detailed_analysis']['health_advice'],
                height=150,
                key='edit_health'
            )
            
            st.markdown("---")
            st.markdown("#### 3️⃣ 고객 맞춤 분석")
            
            edited_customer_wealth = st.text_area(
                "💰 재물운 (고객용)",
                value=st.session_state.report_package_data['analysis']['customer_analysis']['wealth_luck'],
                height=120,
                key='edit_customer_wealth'
            )
            
            edited_customer_career = st.text_area(
                "💼 경력 (고객용)",
                value=st.session_state.report_package_data['analysis']['customer_analysis']['career_luck'],
                height=120,
                key='edit_customer_career'
            )
            
            edited_customer_love = st.text_area(
                "❤️ 사랑/가족 (고객용)",
                value=st.session_state.report_package_data['analysis']['customer_analysis']['love_family_luck'],
                height=120,
                key='edit_customer_love'
            )
            
            edited_customer_change = st.text_area(
                "🔄 변화 (고객용)",
                value=st.session_state.report_package_data['analysis']['customer_analysis']['change_luck'],
                height=120,
                key='edit_customer_change'
            )
            
            st.markdown("---")
            st.markdown("#### 4️⃣ 최종 메시지")
            
            edited_final_message = st.text_area(
                "🌟 마무리 메시지",
                value=st.session_state.report_package_data['analysis']['final_message'],
                height=100,
                key='edit_final_message'
            )
            
            st.markdown("---")
            
            # 수정 내용 저장 버튼
            if st.button("💾 수정 내용 저장 및 적용", type="primary", key='save_edits'):
                # 요약 카드 업데이트
                st.session_state.report_package_data['analysis']['summary_card']['keyword'] = edited_keyword
                st.session_state.report_package_data['analysis']['summary_card']['best_month'] = edited_best_month
                st.session_state.report_package_data['analysis']['summary_card']['risk'] = edited_risk
                st.session_state.report_package_data['analysis']['summary_card']['action_item'] = edited_action_item
                
                # 상세 분석 업데이트
                st.session_state.report_package_data['analysis']['detailed_analysis']['wealth_luck'] = edited_wealth
                st.session_state.report_package_data['analysis']['detailed_analysis']['career_luck'] = edited_career
                st.session_state.report_package_data['analysis']['detailed_analysis']['love_family_luck'] = edited_love
                st.session_state.report_package_data['analysis']['detailed_analysis']['change_luck'] = edited_change
                st.session_state.report_package_data['analysis']['detailed_analysis']['health_advice'] = edited_health
                
                # 고객 맞춤 분석 업데이트
                st.session_state.report_package_data['analysis']['customer_analysis']['wealth_luck'] = edited_customer_wealth
                st.session_state.report_package_data['analysis']['customer_analysis']['career_luck'] = edited_customer_career
                st.session_state.report_package_data['analysis']['customer_analysis']['love_family_luck'] = edited_customer_love
                st.session_state.report_package_data['analysis']['customer_analysis']['change_luck'] = edited_customer_change
                
                # 최종 메시지 업데이트
                st.session_state.report_package_data['analysis']['final_message'] = edited_final_message
                
                st.success("✅ 수정 내용이 저장되었습니다! 아래 리포트 다운로드 버튼을 눌러 수정된 내용으로 생성하세요.")
                st.balloons()


        # --- 6. 고객용 리포트 배포 (Tier 2 통합) ---
        st.markdown("### 6. 📄 고객용 리포트 배포")

        # 무료/프리미엄 버튼 2개로 분리
        col1, col2 = st.columns(2)

        with col1:
           st.markdown("#### 🎁 무료 미리보기")
           free_html = generate_free_report_html(st.session_state.report_package_data)
           st.download_button(
                 label="📄 무료 리포트 다운로드",
               data=free_html.encode('utf-8'),
               file_name=f"{name}_무료사주_2026.html",
               mime="text/html",
                 key='download_free_btn'
             )
           st.caption("✨ 간단한 운세 미리보기 (5개 섹션)")

        with col2:
           st.markdown("#### 💎 프리미엄 리포트")
           premium_html = generate_premium_report_html(st.session_state.report_package_data)
           st.download_button(
             label="💎 프리미엄 리포트 다운로드 (₩29,000)",
             data=premium_html.encode('utf-8'),
             file_name=f"{name}_프리미엄사주_2026.html",
             mime="text/html",
             key='download_premium_btn'
           )
           st.caption("🌟 전체 분석 + 6개 특별 섹션 (재물 타이밍, 심리 해소 등)")
        st.info("💡 차이점: 무료(5개 섹션) vs 프리미엄(11개 섹션 + 액션 플랜)")

        st.markdown("""<p style="text-align:center; color:#888; margin-top:10px; font-size:0.9rem;">* 주의: **반드시 위 다운로드 버튼을 사용하여 고객에게 파일을 전달해 주세요.**</p>""", unsafe_allow_html=True)
        
        # --- 7. 실시간 추가 질문/답변 기록 (Chat) ---
        st.markdown("---")
        st.markdown("### 7. 💬 실시간 추가 질문/답변 기록")
        
        for entry in st.session_state.chat_history:
            if entry["role"] == "initial_query":
                st.subheader(f"✅ 초기 분석 (Q1/Q2 포함)")
                st.markdown(f"요청: _{entry['query']}_")
                
            elif entry["role"] == "user_follow_up":
                st.markdown(f"👨🏻‍💻 추가 질문: _{entry['query']}_")
                st.info(f"🤖 답변: \n\n{entry['response'].get('follow_up_answer', '답변 생성 오류').replace('\\n', '\n')}")

        with st.form("follow_up_form", clear_on_submit=True):
            follow_up_q = st.text_area("추가 질문 입력", placeholder="추가로 궁금한 점을 질문하세요.", key="follow_up_input_form")
            btn_follow_up = st.form_submit_button("💬 추가 질문 분석")
            
            if btn_follow_up and follow_up_q and st.session_state.last_result:
                
                with st.spinner("AI가 추가 질문을 분석 중입니다..."):
                    # Note: We are using a simple prompt for follow-up without the full system_instruction JSON block for speed
                    follow_up_prompt = f"""
                    당신은 '희구소(Hidden Luck Lab)'의 사주 전문 AI 멘토입니다. 당신의 임무는 고객의 만세력 데이터를 바탕으로 현실적이고 심리 명리 기반의 따뜻한 조언을 제공하는 것입니다.
                    
                    [Saju Info] {st.session_state.manse_info}
                    [Current Analysis Context] {json.dumps(st.session_state.last_result, ensure_ascii=False)}
                    [Query] {follow_up_q}
                    
                    *이 요청은 이전 분석을 기반으로 하는 '추가 질문'입니다.*
                    *오직 질문({follow_up_q})에 대한 'follow_up_answer' 키와 답변(300자 내외)만 포함하는 JSON을 반환하십시오.*
                    
                    예시 출력 포맷: {{"follow_up_answer": "여기에 답변을 작성하십시오."}}
                    """
                    
                    try:
                        api_key_chat = st.session_state.get('api_key') # 채팅 시에도 api_key 사용
                        if not api_key_chat:
                             raise ValueError("API Key is missing for chat")
                             
                        genai.configure(api_key=api_key_chat)
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        resp = model.generate_content(follow_up_prompt, generation_config={
                            "temperature": 0.4,
                            "response_mime_type": "application/json",
                            "response_schema": {
                                "type": "OBJECT",
                                "properties": {
                                    "follow_up_answer": {"type": "STRING"}
                                }
                            }
                        })
                        
                        follow_up_text = resp.text.strip()
                        follow_up_response = json.loads(follow_up_text)

                    except Exception as e:
                        follow_up_response = {"follow_up_answer": f"답변 생성 중 오류 발생: {str(e)}"}
                    
                    st.session_state.chat_history.append({
                        "role": "user_follow_up",
                        "query": follow_up_q,
                        "response": follow_up_response
                    })
                    
                    st.rerun()  


if __name__ == "__main__":
    render_app()

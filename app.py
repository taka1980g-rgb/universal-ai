
import streamlit as st
import google.generativeai as genai

# === 🚪 入場パスワードのチェック ===
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "1234")

if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not st.session_state["password_correct"]:
    st.title("🔒 万能 AI チャット")
    pwd = st.text_input("合言葉（パスワード）を入力してください", type="password")
    if pwd == APP_PASSWORD:
        st.session_state["password_correct"] = True
        st.rerun()
    elif pwd != "":
        st.error("パスワードが違います👀")
    st.stop() 

# === 🔑 API設定 ===
try:
    MY_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    MY_API_KEY = ""
    st.error("⚠️ Secretsを設定してください！")
    st.stop()

genai.configure(api_key=MY_API_KEY.strip())

st.title("💡 万能 AI アシスタント")

# === 🧠 AIモデルのリスト取得（ハイブリッド方式） ===
@st.cache_data(ttl=3600) # 1時間に1回だけ最新リストを取得し、あとは使い回す（爆速化）
def get_model_list():
    try:
        models_info = genai.list_models()
        # テキスト生成ができるモデルだけを抽出
        return [m.name.replace("models/", "") for m in models_info if 'generateContent' in m.supported_generation_methods]
    except:
        # エラー時は絶対に消えない固定リストを返す
        return ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-pro-exp-02-05"]

available_models = get_model_list()

# === ⚙️ サイドバー設定 ===
with st.sidebar:
    st.header("⚙️ 設定メニュー")
    
    selected_model = st.selectbox("🧠 使用するAIモデル", available_models, index=0)
    
    st.markdown("---")
    st.write("📝 AIへの全体指示（システムプロンプト）")
    system_instruction = st.text_area(
        "AIの役割やルールを自由に書いてください", 
        "あなたは優秀なAIアシスタントです。質問に対して、正確かつ分かりやすく日本語で答えてください。",
        height=150
    )
    
    st.markdown("---")
    if st.button("🗑️ 会話をリセット", use_container_width=True):
        st.session_state.uni_messages = []
        if "uni_chat_session" in st.session_state:
            del st.session_state["uni_chat_session"]
        st.rerun()

# === 💬 チャットシステムの初期化 ===
if "uni_messages" not in st.session_state:
    st.session_state.uni_messages = []

# AIの「脳みそ（チャットセッション）」を準備
if "uni_chat_session" not in st.session_state:
    model = genai.GenerativeModel(selected_model, system_instruction=system_instruction)
    st.session_state.uni_chat_session = model.start_chat(history=[])

# 過去のメッセージを画面に表示
for message in st.session_state.uni_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# === ⌨️ メッセージ入力と応答 ===
# st.chat_input は画面の一番下に固定される、チャット専用の入力欄です
if prompt := st.chat_input("AIにメッセージを送信..."):
    # ユーザーの入力を画面に表示＆保存
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.uni_messages.append({"role": "user", "content": prompt})
    
    # AIの返答を取得して画面に表示＆保存
    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            try:
                response = st.session_state.uni_chat_session.send_message(prompt)
                st.markdown(response.text)
                st.session_state.uni_messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

import streamlit as st
import google.generativeai as genai
from gtts import gTTS
import PyPDF2
import io
import json
import re

# === 🎨 画面デザインのカスタマイズ（CSS） ===
st.markdown("""
    <style>
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFDE7 !important;
        border: 2px solid #FFF59D !important;
        border-radius: 10px;
        padding: 15px;
    }
    div[data-testid="stForm"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E0E4E8 !important;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# === 🚪 入場パスワード ===
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "1234")
if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not st.session_state["password_correct"]:
    st.title("🔒 家族専用 AI英会話 (完全版)")
    pwd = st.text_input("合言葉を入力してください", type="password")
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
    st.error("⚠️ Secretsから GEMINI_API_KEY を設定してください！")
    st.stop()
genai.configure(api_key=MY_API_KEY.strip())

# === 🧹 音声読み上げ用テキストクリーナー（アスタリスク・不要なアポストロフィを削除） ===
def clean_text_for_tts(text):
    # Markdownの記号(*, _, #, ~)を完全に削除
    text = re.sub(r'[*_#~]', '', text)
    # 単語を囲むアポストロフィや引用符だけを削除（It's のような単語内のアポストロフィは残す）
    text = re.sub(r"(?<!\w)['\"]|['\"](?!\w)", '', text)
    return text.strip()

st.title("My English Roleplay AI 🗣️")

# === ⚙️ サイドバーの設定 ===
with st.sidebar:
    st.header("⚙️ 設定メニュー")
    
    model_options = {"賢い・やや遅い": "gemini-2.5-flash", "最速・低コスト": "gemini-2.5-flash-lite"}
    selected_model = model_options[st.selectbox("使用中の脳みそ", list(model_options.keys()), index=0)]
    
    st.markdown("---")
    st.write("📂 **設定の読み込み**")
    setting_file = st.file_uploader("保存した設定（.json）をアップロード", type=["json"])
    loaded_settings = json.load(setting_file) if setting_file else {}

    def_level = loaded_settings.get("level", "2: 初心者（日常会話の基礎）")
    level = st.selectbox("📈 会話のレベル", [
        "1: 超初心者（簡単な単語・短い文）", "2: 初心者（日常会話の基礎）", 
        "3: 中級者（自然な表現・標準速度）", "4: 上級者（ビジネス・専門用語）", "5: 専門家（ネイティブレベル）"
    ], index=["1: 超初心者（簡単な単語・短い文）", "2: 初心者（日常会話の基礎）", "3: 中級者（自然な表現・標準速度）", "4: 上級者（ビジネス・専門用語）", "5: 専門家（ネイティブレベル）"].index(def_level) if def_level in ["1: 超初心者（簡単な単語・短い文）", "2: 初心者（日常会話の基礎）", "3: 中級者（自然な表現・標準速度）", "4: 上級者（ビジネス・専門用語）", "5: 専門家（ネイティブレベル）"] else 1)

    user_name = st.text_input("📛 あなたの名前", value=loaded_settings.get("user_name", ""), placeholder="例: masa") or "Anata"
    questioner = st.text_input("👤 相手の役柄（詳細に）", value=loaded_settings.get("questioner", "同年代の気さくな友達"), placeholder="例: 空港の入国審査官。少し厳しめ。")
    situation = st.text_area("🎬 シチュエーション", value=loaded_settings.get("situation", "週末の予定について話しています。"), height=80)
    focus_words = st.text_input("🎯 練習したい単語・テーマ", value=loaded_settings.get("focus_words", ""), placeholder="例: 医療系頻出単語")
    
    doc_text = loaded_settings.get("doc_text", "")
    uploaded_file = st.file_uploader("参考資料 (PDF/TXT)", type=["pdf", "txt"])
    if uploaded_file:
        if uploaded_file.name.endswith('.pdf'):
            reader = PyPDF2.PdfReader(uploaded_file)
            doc_text = "".join([page.extract_text() + "\n" for page in reader.pages])
        else:
            doc_text = uploaded_file.read().decode('utf-8')
        st.success("資料を読み込みました！")

    st.markdown("---")
    current_settings = {"level": level, "user_name": user_name, "questioner": questioner, "situation": situation, "focus_words": focus_words, "doc_text": doc_text}
    st.download_button("💾 現在の設定を保存（.json）", data=json.dumps(current_settings, ensure_ascii=False, indent=2), file_name="settings.json", mime="application/json", use_container_width=True)

    start_button = st.button("▶️ 会話をスタート", type="primary", use_container_width=True)
    end_button = st.button("🛑 終了して評価をもらう", use_container_width=True)

    # 📊 進捗ダッシュボード（簡易）
    st.markdown("---")
    st.write("📊 **今日の学習記録**")
    if "stats_turns" not in st.session_state:
        st.session_state.stats_turns = 0
        st.session_state.stats_mistakes = 0
    st.write(f"- 発話ターン数: {st.session_state.stats_turns} 回")
    st.write(f"- リピート練習: {st.session_state.stats_mistakes} 回")

# === 🤖 AIへの絶対的な指示書（★お漏らし防止・パターンCの追加でガチガチに強化） ===
system_instruction = f"""
あなたは英会話のロールプレイング相手です。
【相手の役柄】: {questioner}
【ユーザーの名前】: {user_name}
【レベル】: {level}
【状況】: {situation}
【重点テーマ】: {focus_words}
【資料】: {doc_text}

【絶対に守るべき厳格なルール】
1. あなたの出力は、以下の「指定フォーマット」のブロックのみで構成してください。
2. 「はい、承知しました」などの会話のシステム的な前置きは絶対に出力しないでください。
3. 英文中で単語を強調する際は、アポストロフィ（' '）やダブルクォーテーション（" "）を使わず、必ずMarkdownの太字（**単語**）を使用してください。
4. 【重要】指定フォーマット内の括弧（ ）は説明書きです。出力する際は括弧そのものを削除し、中身のテキストだけを出力してください。

【指定フォーマット】※以下のA・B・Cのいずれかのパターンのみを出力すること。

▼ パターンA：ユーザーの英語にミス・不自然さがある場合（リピート練習）
[フィードバック]
- （日本語でのミスの指摘と解説）
- 和訳: （すぐ下の[リピート練習]の英文の日本語訳）
[リピート練習]
（ユーザーが復唱するための、正しい英語のセリフのみ。記号は使わない）

▼ パターンB：ユーザーの英語が自然、または会話の開始時（通常進行）
[フィードバック]
- （日本語で短く褒める、または相槌）
[英語の質問]
（役柄としてユーザーに投げかける英語のセリフや質問文のみ）

▼ パターンC：ユーザーから「今の質問をもう一度言って」と頼まれた場合（やり直し）
[フィードバック]
- （日本語で「もう一度言いますね」と短く返事）
[英語の質問]
（直前と全く同じ英語の質問文）
"""

if "last_played_msg_idx" not in st.session_state:
    st.session_state.last_played_msg_idx = -1
if "tool_cache" not in st.session_state:
    st.session_state.tool_cache = {}

if start_button:
    try:
        model = genai.GenerativeModel(selected_model, system_instruction=system_instruction)
        st.session_state.chat_session = model.start_chat(history=[])
        st.session_state.messages = []
        st.session_state.last_played_msg_idx = -1
        st.session_state.stats_turns = 0
        st.session_state.stats_mistakes = 0
        st.session_state.tool_cache = {}
        
        response = st.session_state.chat_session.send_message("会話を開始して、最初の質問を投げかけてください。")
        st.session_state.messages.append({"role": "assistant", "content": response.text})
    except Exception as e:
        st.error(f"準備中にエラーが発生しました: {e}")

# === 会話の描画と音声再生 ===
if "chat_session" in st.session_state:
    for i, message in enumerate(st.session_state.messages):
        if message["role"] == "user" and message["content"].startswith("（"):
            continue 
            
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            if message["role"] == "assistant":
                raw_text = ""
                if "[英語の質問]" in message["content"]:
                    raw_text = message["content"].split("[英語の質問]")[1].strip()
                elif "[リピート練習]" in message["content"]:
                    raw_text = message["content"].split("[リピート練習]")[1].strip()
                    
                if raw_text:
                    try:
                        # ★ 音声クリーナーを通す
                        speak_text = clean_text_for_tts(raw_text)
                        tts = gTTS(text=speak_text, lang='en')
                        fp = io.BytesIO()
                        tts.write_to_fp(fp)
                        fp.seek(0)
                        
                        auto_play = False
                        if i == len(st.session_state.messages) - 1 and st.session_state.last_played_msg_idx != i:
                            auto_play = True
                            st.session_state.last_played_msg_idx = i
                            
                        st.audio(fp, format="audio/mp3", autoplay=auto_play)
                    except Exception:
                        pass

    st.markdown("---")
    
    # === 通信量節約機能（スマート・トリミング） ===
    def get_trimmed_history():
        # 直近8メッセージ（4往復）だけを抽出してAPI節約
        raw_history = st.session_state.messages[-8:] if len(st.session_state.messages) > 8 else st.session_state.messages
        formatted = []
        for m in raw_history:
            formatted.append({"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]})
        return formatted

    prompt = None
    display_prompt = None
    last_msg = st.session_state.messages[-1] if len(st.session_state.messages) > 0 else None
    
    # 状態判定
    is_practice = False
    target_practice_text = ""
    if last_msg and last_msg["role"] == "assistant" and "[リピート練習]" in last_msg["content"]:
        is_practice = True
        target_practice_text = last_msg["content"].split("[リピート練習]")[1].strip()

    # ＝＝＝ 🔄 リピート練習モード ＝＝＝
    if is_practice:
        st.info("🔄 **リピート練習モード**：マイクで発音してみましょう。")
        practice_audio = st.audio_input("発音を録音する")
        
        # ★暴走防止：送信ボタンでの実行に変更
        if practice_audio:
            if st.button("🤖 AIに発音を判定してもらう", use_container_width=True):
                with st.spinner("AIが発音を判定中..."):
                    try:
                        transcriber = genai.GenerativeModel(selected_model)
                        res = transcriber.generate_content([{"mime_type": "audio/wav", "data": practice_audio.getvalue()}, "英語を文字起こししてください。文字のみ出力。"])
                        user_spoken = res.text.strip() if res.parts else ""
                        st.write(f"🎤 あなたの発音: **{user_spoken}**")
                        
                        judge_model = genai.GenerativeModel(selected_model)
                        judge_res = judge_model.generate_content(f"お手本:「{target_practice_text}」\n発音:「{user_spoken}」\n一言一句同じか厳格に判定し、違いがあれば日本語で1文で指摘してください。")
                        st.success(f"🤖 判定: {judge_res.text.strip()}")
                    except Exception:
                        st.error("聞き取れませんでした。もう一度お願いします。")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ 練習完了！次へ進む", type="primary", use_container_width=True):
                prompt = "（リピート練習完了。会話を続けるための新しい質問を【パターンB】の形式でしてください。）"
                display_prompt = "（✅ 練習を完了し、次へ進みました）"
        with col2:
            if st.button("↩️ 練習せず1つ前の質問に答え直す (Undo)", use_container_width=True):
                if len(st.session_state.messages) >= 3:
                    st.session_state.messages = st.session_state.messages[:-2]
                    st.session_state.stats_mistakes -= 1
                    
                    re_model = genai.GenerativeModel(selected_model, system_instruction=system_instruction)
                    st.session_state.chat_session = re_model.start_chat(history=get_trimmed_history())
                    st.session_state.last_played_msg_idx = -1
                    st.rerun()
                else:
                    st.warning("これ以上巻き戻せません。")

    # ＝＝＝ 🗣️ 通常モード ＝＝＝
    else:
        st.write("🗣️ **あなたのターン**")
        
        if st.button("🔄 今の質問をもう一度聞く（別の言い方で答え直したい時など）"):
            prompt = "すみません、あなたの今の質問にもう一度別の言い方で答えたいので、全く同じ質問文をもう一度言ってください。新しい質問はしないでください。"
            display_prompt = "（🔄 今の質問をもう一度繰り返してください）"

        # ★暴走防止：送信ボタンでの実行に変更
        audio_value = st.audio_input("マイクを押して回答を録音")
        if audio_value:
            if st.button("📤 この音声を文字起こしして送信する", type="primary", use_container_width=True):
                with st.spinner("文字に変換中..."):
                    try:
                        transcriber = genai.GenerativeModel(selected_model)
                        res = transcriber.generate_content([{"mime_type": "audio/wav", "data": audio_value.getvalue()}, "英語を文字起こししてください。文字のみ出力。"])
                        if res.parts:
                            prompt = res.text.strip()
                            display_prompt = prompt
                            st.session_state.stats_turns += 1
                    except Exception:
                        st.error("聞き取れませんでした。")

        st.markdown("---")
        
        # 🛠️ お助けツール群
        with st.container(border=True):
            st.write("🛠️ **お助けツール（※会話は進みません）**")
            current_q = last_msg["content"].split("[英語の質問]")[1].strip() if last_msg and "[英語の質問]" in last_msg["content"] else ""

            # 🎧 クイズ機能（★前置き禁止・超簡略化プロンプト）
            if current_q:
                with st.expander("🎧 リスニング確認クイズ"):
                    if "quiz" not in st.session_state.tool_cache:
                        if st.button("クイズを生成する"):
                            with st.spinner("作成中..."):
                                q_ai = genai.GenerativeModel(selected_model)
                                quiz_prompt = f"""
                                以下の英語セリフに対するリスニング3択クイズを作成してください。
                                【厳守事項】
                                ・「はい、作成します」などの前置きや、解説は【絶対】に出力しないこと。
                                ・問題文と選択肢は1文で極力短くシンプルにすること。
                                
                                セリフ: {current_q}
                                
                                【出力フォーマット】
                                Q. （短い問題文）
                                1. （短い選択肢）
                                2. （短い選択肢）
                                3. （短い選択肢）
                                正解: （番号のみ）
                                """
                                st.session_state.tool_cache["quiz"] = q_ai.generate_content(quiz_prompt).text
                                st.rerun()
                    if "quiz" in st.session_state.tool_cache:
                        st.markdown(st.session_state.tool_cache["quiz"])

            st.write("🇯🇵 **直前のセリフの日本語訳**")
            if st.button("日本語訳を見る"):
                if "translation" not in st.session_state.tool_cache:
                    with st.spinner("翻訳中..."):
                        t_ai = genai.GenerativeModel(selected_model)
                        st.session_state.tool_cache["translation"] = t_ai.generate_content(f"以下を日本語に翻訳して:\n{current_q}").text
                st.info(f"🇯🇵 {st.session_state.tool_cache['translation']}")

            with st.form("dictionary_form", clear_on_submit=False):
                st.write("📖 **単語辞書 / 文法**")
                dict_word = st.text_input("調べたい英単語や文法:", label_visibility="collapsed", placeholder="例: evidence, 現在完了形")
                if st.form_submit_button("調べる"):
                    with st.spinner("検索中..."):
                        d_ai = genai.GenerativeModel(selected_model)
                        res = d_ai.generate_content(f"「{dict_word}」の意味と簡単な例文を1つ教えて。簡潔に。").text
                        st.info(res)

            st.write("🧠 **ちょい足しヒント**")
            with st.form("hint_form", clear_on_submit=False):
                hint_type = st.selectbox("ヒントの種類", ["使うべき単語を3つ", "文の出だし（3語）", "日本語でのアイデア"], label_visibility="collapsed")
                if st.form_submit_button("ヒントをもらう"):
                    with st.spinner("作成中..."):
                        h_ai = genai.GenerativeModel(selected_model)
                        h_res = h_ai.generate_content(f"質問: {current_q}\n指示: {hint_type} を教えて。英語の完全な解答は書かないこと。").text
                        st.info(f"💡 {h_res}")

            st.write("🏳️ **ギブアップ**")
            if st.button("解説と回答例を見て、リピート練習へ進む"):
                st.session_state.stats_mistakes += 1
                prompt = "（今の質問の意図がわかりません。新しい質問はせず、【パターンA】の形式で、自然な回答例の解説と和訳、そしてリピート練習用の回答例を提示してください。）"
                display_prompt = "（🏳️ ギブアップしました）"

    # ＝＝＝ 送信処理（スマートトリミング適用） ＝＝＝
    if prompt and display_prompt:
        st.session_state.messages.append({"role": "user", "content": display_prompt})
        st.session_state.tool_cache = {} 
        
        with st.spinner("AIが返答を考えています..."):
            try:
                trim_model = genai.GenerativeModel(selected_model, system_instruction=system_instruction)
                st.session_state.chat_session = trim_model.start_chat(history=get_trimmed_history()[:-1])
                response = st.session_state.chat_session.send_message(prompt)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
                if "[リピート練習]" in response.text:
                    st.session_state.stats_mistakes += 1
                    
                st.rerun() 
            except Exception as e:
                st.error("エラーが発生しました。")

# === 評価処理 ===
if end_button and "chat_session" in st.session_state:
    with st.spinner("成績をまとめています..."):
        summary_prompt = "会話を終了します。学習者をたくさん褒めた後、100点満点のスコア（文法、語彙、積極性、総合）と、良かった点、今後の課題を出力してください。"
        st.session_state.messages.append({"role": "user", "content": "（終了して評価をリクエスト）"})
        try:
            res = st.session_state.chat_session.send_message(summary_prompt)
            st.session_state.messages.append({"role": "assistant", "content": res.text})
            st.rerun()
        except Exception:
            st.error("評価の作成に失敗しました。")

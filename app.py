import streamlit as st
import google.generativeai as genai
from gtts import gTTS
import PyPDF2
import io
import json
from datetime import datetime, timedelta
import os

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

# === 🚪 入場パスワードのチェック ===
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "1234")

if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not st.session_state["password_correct"]:
    st.title("🔒 家族専用 AI英会話ver2　テスト中")
    pwd = st.text_input("合言葉（パスワード）を入力してください", type="password")
    if pwd == APP_PASSWORD:
        st.session_state["password_correct"] = True
        st.rerun()
    elif pwd != "":
        st.error("パスワードが違います👀")
    st.stop() 

# ==========================================================
# 🔑 StreamlitのSecrets（金庫）からAPIキーを自動で読み込む
# ==========================================================
try:
    MY_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    MY_API_KEY = ""
    st.error("⚠️ StreamlitのSettingsから「Secrets」を開き、GEMINI_API_KEY を設定してください！")
    st.stop()

genai.configure(api_key=MY_API_KEY.strip())

st.title("My English Roleplay AI 🗣️")

# ========================================================
# 📚 文法リファレンスデータベース（組み込み版）
# ========================================================
GRAMMAR_REFERENCE = {
    "現在完了": {
        "rule": "have/has + 過去分詞。経験・変化・継続・結果を表す",
        "examples": [
            {"en": "I have visited Tokyo three times.", "ja": "私は東京に3回行ったことがあります。"},
            {"en": "She has lived here for 5 years.", "ja": "彼女は5年間ここに住んでいます。"},
            {"en": "Have you finished your homework?", "ja": "宿題は終わりましたか？"}
        ],
        "mistakes": [
            "I have been to Tokyo three times ago. （❌ agoと一緒に使わない）",
            "I have went to Tokyo. （❌ went ではなく gone）"
        ],
        "tips": "現在完了と過去形の使い分けが重要。『いつ』が明確なら過去形、『経験・継続』なら現在完了。"
    },
    "受動態": {
        "rule": "be + 過去分詞。『～される』という被動の意味",
        "examples": [
            {"en": "The book was written by Mark Twain.", "ja": "その本はマーク・トウェインによって書かれました。"},
            {"en": "This car is made in Japan.", "ja": "この車は日本で作られています。"},
            {"en": "She was invited to the party.", "ja": "彼女はパーティーに招待されました。"}
        ],
        "mistakes": [
            "The book was written to Mark Twain. （❌ by ではなく to）",
            "This car makes in Japan. （❌ is made にすべき）"
        ],
        "tips": "能動態の目的語が、受動態の主語になる。時制は変わらない（is written = 現在進行的）。"
    },
    "仮定法": {
        "rule": "if + 過去形...would/could + 動詞。『もし～だったら（仮に）』という反事実的な状況を表す",
        "examples": [
            {"en": "If I had more time, I would travel.", "ja": "もし時間があったら、旅行に行くのに。"},
            {"en": "If I were you, I wouldn't do that.", "ja": "君だったら、そんなことはしないね。"},
            {"en": "If she knew the truth, she would be upset.", "ja": "もし彼女が真実を知ったら、動揺するだろう。"}
        ],
        "mistakes": [
            "If I will have more time, I would travel. （❌ will have ではなく had）",
            "If I am you, I wouldn't do that. （❌ am ではなく were）"
        ],
        "tips": "仮定法過去：『現在の反事実』If S + V(過去形), S + would + V。仮定法過去完了：『過去の反事実』If S + had + pp, S + would have + pp。"
    },
    "前置詞": {
        "rule": "名詞の前に置いて、時間・場所・関係を表す",
        "examples": [
            {"en": "I go to school at 7 AM.", "ja": "私は朝7時に学校に行きます。"},
            {"en": "The book is on the table.", "ja": "本は机の上にあります。"},
            {"en": "She arrived in Tokyo last week.", "ja": "彼女は先週東京に到着しました。"}
        ],
        "mistakes": [
            "I go in school. （❌ in ではなく to）",
            "The book is in the table. （❌ in ではなく on）"
        ],
        "tips": "at（点の時間/小さい場所）、in（期間/大きい場所）、on（面の上）。覚える方法：図で覚える！"
    },
    "関係代名詞": {
        "rule": "先行詞を修飾する節を導く。who（人）、which（物）、that（人・物）",
        "examples": [
            {"en": "The man who lives next door is a doctor.", "ja": "隣に住んでいる男性は医者です。"},
            {"en": "The book which I read last week was interesting.", "ja": "先週読んだ本は面白かったです。"},
            {"en": "I know the reason that he was late.", "ja": "彼が遅刻した理由を知っています。"}
        ],
        "mistakes": [
            "The man who I met yesterday is a doctor. （❌ who ではなく whom または that のみ）",
            "The book which that I read was interesting. （❌ which と that は両方使わない）"
        ],
        "tips": "主語になる場合：who/which、目的語になる場合：whom/which/that。制限用法と非制限用法の違いも重要。"
    }
}

# ========================================================
# 📊 進捗管理・SRS機能の初期化
# ========================================================

def load_session_history():
    """セッション履歴をJSONから読み込む"""
    try:
        with open("session_history.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"sessions": []}

def save_session_history(history):
    """セッション履歴をJSONに保存"""
    with open("session_history.json", 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_mistake_bank():
    """ミス単語銀行を読み込む（セッション内のみ）"""
    if "mistake_bank" not in st.session_state:
        st.session_state.mistake_bank = {
            "single_pass": [],
            "repeated_mistakes": [],
            "corrected": []
        }
    return st.session_state.mistake_bank

def add_mistake_to_bank(word, feedback_text):
    """ミスを mistake_bank に記録（セッション内のみ）"""
    mistake_bank = load_mistake_bank()
    if word not in mistake_bank["single_pass"]:
        mistake_bank["single_pass"].append({
            "word": word,
            "feedback": feedback_text,
            "timestamp": datetime.now().isoformat()
        })

def initialize_session_stats():
    """現在のセッション統計を初期化"""
    if "session_stats" not in st.session_state:
        st.session_state.session_stats = {
            "total_exchanges": 0,
            "mistakes_found": 0,
            "practice_attempts": 0,
            "unique_words": set(),
            "grammar_tags": [],
            "session_start_time": datetime.now().isoformat()
        }

def update_session_stats(key, value=None):
    """セッション統計を更新"""
    if "session_stats" not in st.session_state:
        initialize_session_stats()
    
    if key == "total_exchanges":
        st.session_state.session_stats["total_exchanges"] += 1
    elif key == "mistakes_found":
        st.session_state.session_stats["mistakes_found"] += 1
    elif key == "practice_attempts":
        st.session_state.session_stats["practice_attempts"] += 1
    elif key == "grammar_tags" and value:
        st.session_state.session_stats["grammar_tags"].append(value)

initialize_session_stats()

# === ⚙️ サイドバーの設定と保存・読み込み ===
with st.sidebar:
    st.header("⚙️ 設定メニュー")
    
    st.write("🧠 AIモデル")
    model_options = {
        "賢い・やや遅い": "gemini-2.5-flash",
        "最速・低コスト": "gemini-2.5-flash-lite"
    }
    selected_display_name = st.selectbox("使用中の脳みそ", list(model_options.keys()), index=0)
    selected_model = model_options[selected_display_name]
    
    st.markdown("---")
    
    st.write("📂 **設定の読み込み**")
    setting_file = st.file_uploader("保存した設定（.json）をアップロード", type=["json"])
    
    loaded_settings = {}
    if setting_file is not None:
        try:
            loaded_settings = json.load(setting_file)
            st.success("設定を読み込みました！")
        except Exception:
            st.error("ファイルの読み込みに失敗しました。")

    def_level = loaded_settings.get("level", "2: 初心者（日常会話の基礎）")
    def_uname = loaded_settings.get("user_name", "")
    def_pq = loaded_settings.get("preset_questioner", "同年代の友達")
    def_fq = loaded_settings.get("free_questioner", "")
    def_sit = loaded_settings.get("situation", "例: 私の発表が終わった後の質疑応答の時間です。少し意地悪な質問をしてください。")
    def_fw = loaded_settings.get("focus_words", "")
    def_doc = loaded_settings.get("doc_text", "")

    level_list = [
        "1: 超初心者（簡単な単語・短い文・ゆっくり）", 
        "2: 初心者（日常会話の基礎）", 
        "3: 中級者（自然な表現・標準的な速度）", 
        "4: 上級者（ビジネスや専門的な語彙）", 
        "5: 専門家（ネイティブレベル・複雑な議論）"
    ]
    level_idx = level_list.index(def_level) if def_level in level_list else 1
    level = st.selectbox("📈 会話のレベル", level_list, index=level_idx)

    input_name = st.text_input("📛 あなたの名前（呼ばれ方）", value=def_uname, placeholder="例: masa")
    user_name = input_name if input_name else "Anata"
    
    # ★新機能：詳細ペルソナ設定
    st.markdown("---")
    st.write("👤 **質問者（AIの役割）の詳細設定**")
    pq_list = ["小学校の先生", "同年代の友達", "職場の先輩", "気さくな友達", "学会発表の聴衆", "その他（自由入力）"]
    pq_idx = pq_list.index(def_pq) if def_pq in pq_list else 1
    preset_questioner = st.selectbox("AIの役柄を選んでください", pq_list, index=pq_idx)
    
    if preset_questioner == "その他（自由入力）":
        free_questioner = st.text_input("自由に役割を入力してください", value=def_fq, placeholder="例: 空港の入国審査官")
        questioner = free_questioner
    else:
        free_questioner = ""
        questioner = preset_questioner
    
    # ★詳細ペルソナ情報
    questioner_age = st.slider("質問者の年齢", 18, 80, 35)
    questioner_gender = st.selectbox("質問者の性別", ["男性", "女性", "不明"])
    questioner_personality = st.multiselect(
        "質問者の性格（複数選択可）",
        ["親友的", "厳しい", "励ましてくれる", "皮肉的", "フレンドリー", "親切"],
        default=["フレンドリー"]
    )
    questioner_background = st.text_input(
        "質問者の背景情報（任意）",
        placeholder="例：Silicon Valley のスタートアップCEO、日本在住10年"
    )
    
    situation = st.text_area("🎬 シチュエーション", value=def_sit, height=100)
    focus_words = st.text_input("🎯 練習したい単語・テーマ (任意)", value=def_fw, placeholder="例: 医療系頻出単語")
    
    st.write("📁 資料を読み込ませる")
    doc_text = def_doc
    uploaded_file = st.file_uploader("新しい資料 (PDF/TXT) ※設定ファイル読込済なら不要", type=["pdf", "txt"])
    
    def extract_text(file):
        text = ""
        if file.name.endswith('.pdf'):
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        elif file.name.endswith('.txt'):
            text = file.read().decode('utf-8')
        return text

    if uploaded_file is not None:
        doc_text = extract_text(uploaded_file)
        st.success("新しい資料のテキストを抽出しました！")

    st.markdown("---")
    
    st.write("💾 **現在の設定を保存する**")
    current_settings = {
        "level": level,
        "user_name": input_name,
        "preset_questioner": preset_questioner,
        "free_questioner": free_questioner,
        "situation": situation,
        "focus_words": focus_words,
        "doc_text": doc_text,
        "questioner_age": questioner_age,
        "questioner_gender": questioner_gender,
        "questioner_personality": questioner_personality,
        "questioner_background": questioner_background
    }
    json_str = json.dumps(current_settings, ensure_ascii=False, indent=2)
    st.download_button("⬇️ 設定ファイル（.json）をダウンロード", data=json_str, file_name="english_settings.json", mime="application/json", use_container_width=True)

    st.markdown("---")
    
    # ★新機能：SRS履歴アップロード
    st.write("📚 **SRS（復習）機能**")
    uploaded_mistake_history = st.file_uploader("以前のSRS履歴をアップロード（復習を再開）", type=["json"], key="srs_upload")
    if uploaded_mistake_history:
        try:
            mistake_history_data = json.load(uploaded_mistake_history)
            st.session_state.mistake_bank = mistake_history_data
            st.success("SRS履歴を読み込みました！")
        except:
            st.error("SRS履歴の読み込みに失敗しました。")
    
    start_button = st.button("▶️ 会話をリセットしてスタート", type="primary", use_container_width=True)
    end_button = st.button("🛑 会話を終了して評価をもらう", use_container_width=True)

    st.markdown("---")
    
    # ★新機能：進捗管理ダッシュボード（セッション内表示）
    if "messages" in st.session_state and len(st.session_state.messages) > 0:
        st.write("📈 **本セッションの進捗**")
        col1, col2, col3 = st.columns(3)
        
        stats = st.session_state.session_stats
        with col1:
            st.metric("総Q&A数", stats["total_exchanges"])
        with col2:
            st.metric("指摘されたミス", stats["mistakes_found"])
        with col3:
            st.metric("復習試行", stats["practice_attempts"])
        
        st.markdown("---")
        
        # ★進捗履歴のダウンロード
        progress_data = {
            "session_start": stats["session_start_time"],
            "total_exchanges": stats["total_exchanges"],
            "mistakes_found": stats["mistakes_found"],
            "practice_attempts": stats["practice_attempts"],
            "grammar_tags": stats["grammar_tags"]
        }
        progress_json = json.dumps(progress_data, ensure_ascii=False, indent=2)
        st.download_button(
            "⬇️ 進捗データをダウンロード",
            data=progress_json,
            file_name="session_progress.json",
            mime="application/json",
            use_container_width=True
        )

        log_text = "【今日の英会話記録】\n\n"
        for msg in st.session_state.messages:
            if msg["role"] == "user" and msg["content"].startswith("（"):
                continue
            sender = "あなた" if msg["role"] == "user" else "AI"
            content = msg["content"].replace("[フィードバック]", "\n[フィードバック]").replace("[英語の質問]", "\n[英語の質問]").replace("[リピート練習]", "\n[リピート練習]")
            log_text += f"{sender}:\n{content.strip()}\n\n{'='*40}\n\n"
            
        st.download_button("📝 今日の会話記録を保存（.txt）", data=log_text, file_name="english_log.txt", mime="text/plain", use_container_width=True)

# ★変更点：システム指示にペルソナ詳細情報を組み込む
questioner_persona = f"""
年齢: {questioner_age}才
性別: {questioner_gender}
性格: {', '.join(questioner_personality)}
背景: {questioner_background if questioner_background else '特に指定なし'}
"""

system_instruction = f"""
あなたは英会話のロールプレイング相手です。

【あなたの役柄（AI自身）】: {questioner}
【あなたの詳細ペルソナ】:
{questioner_persona}
【ユーザーの名前】: {user_name}
【設定レベル】: {level}
【シチュエーション】: {situation}
【重点テーマ・単語】: {focus_words}
【参考資料】: {doc_text}

厳密なルール:
1. あなた自身が【あなたの役柄】です。目の前にいる会話相手が【ユーザーの名前】です。
2. ユーザーの【設定レベル】に合わせて英単語の難易度や文章の長さを調整してください。
3. 通信量削減のため、感情表現や前置きは一切不要です。客観的かつ極めて簡潔に出力してください。
4. フィードバックは、必ずMarkdown形式の箇条書き（- ）を使用し、各項目の後には必ず改行を入れて、1行ずつ独立させて表示してください。横に繋げて書くのは厳禁です。
5. 【重点テーマ・単語】が入力されている場合、そのテーマの単語をあなたの質問に含め、ユーザーにも回答で使うよう英語で促してください。
6. 【重要】英文中で単語を強調する際は、絶対にアポストロフィ（' '）やダブルクォーテーション（" "）で囲まないでください（音声読み上げソフトが記号をそのまま発音してしまうため）。強調したい場合は、必ずMarkdownの太字（**単語**）を使用してください。
7. ユーザーの回答に応じて、以下の「指定フォーマット」のいずれかで出力してください。

▼ パターンA：ユーザーの英語にミスがある、または不自然な場合（リピート練習）
[フィードバック]
- （日本語でミスの指摘と、より自然な表現の解説）
- （★重要：ここで必ず、すぐ下で提示する「リピート練習用の英文」の【日本語訳】を記載してください）
[リピート練習]
（ユーザーがそのまま復唱するための、正しい自然な英語のセリフのみ。新しい質問はしないこと）

▼ パターンB：ユーザーの英語が自然な場合、または会話の最初（通常進行）
[フィードバック]
- （日本語で良かった点の評価）
[英語の質問]
（【あなたの役柄】としてユーザーに投げかける英語のセリフや質問文のみ）
"""

if "last_played_msg_idx" not in st.session_state:
    st.session_state.last_played_msg_idx = -1

if start_button:
    try:
        model = genai.GenerativeModel(selected_model, system_instruction=system_instruction)
        st.session_state.chat_session = model.start_chat(history=[])
        st.session_state.messages = []
        st.session_state.last_played_msg_idx = -1
        initialize_session_stats()
        
        response = st.session_state.chat_session.send_message("シチュエーションを開始して、最初の質問を英語でしてください。")
        st.session_state.messages.append({"role": "assistant", "content": response.text})
    except Exception as e:
        st.error(f"AIの準備中にエラーが発生しました: {e}")

if end_button and "chat_session" in st.session_state:
    with st.spinner("AIが成績をまとめています..."):
        try:
            summary_prompt = """
            ここまでの会話を終了します。通信量削減のため、不要な前置きは省いてください。
            学習者のモチベーションが上がるように、まずはたくさん褒めてください！
            その後、本日の英会話の評価を以下のフォーマットで出力してください。

            【本日のスコア】
            - 文法: 〇/100点
            - 語彙力: 〇/100点
            - 積極性: 〇/100点
            - 総合スコア: 〇/100点

            【良かった点】
            - （具体的に良かった点を箇条書きで褒める）

            【今後の課題・アドバイス】
            - （次に繋がるよう、優しくポジティブにアドバイス）
            """
            response = st.session_state.chat_session.send_message(summary_prompt)
            st.session_state.messages.append({"role": "user", "content": "（会話を終了し、評価をリクエストしました）"})
            st.session_state.messages.append({"role": "assistant", "content": response.text})
        except Exception as e:
            st.error("評価の作成中にエラーが発生しました。")

if "chat_session" in st.session_state:
    for i, message in enumerate(st.session_state.messages):
        if "role" in message and "content" in message:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
                if message["role"] == "assistant":
                    play_text = ""
                    if "[英語の質問]" in message["content"]:
                        play_text = message["content"].split("[英語の質問]")[1].strip()
                    elif "[リピート練習]" in message["content"]:
                        play_text = message["content"].split("[リピート練習]")[1].strip()
                        
                    if play_text:
                        try:
                            tts = gTTS(text=play_text, lang='en')
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

    prompt = None
    display_prompt = None
    
    last_msg = st.session_state.messages[-1] if len(st.session_state.messages) > 0 else None
    is_practice = False
    target_practice_text = ""
    
    if last_msg and last_msg["role"] == "assistant" and "[リピート練習]" in last_msg["content"]:
        is_practice = True
        target_practice_text = last_msg["content"].split("[リピート練習]")[1].strip()

    if is_practice:
        # ＝＝＝ 🔄 リピート練習モードの画面 ＝＝＝
        st.info("🔄 **リピート練習モード**：上のお手本を聞いて、マイクで発音してみましょう。")
        
        practice_audio = st.audio_input("発音をチェックする")
        
        if practice_audio is not None:
            audio_bytes = practice_audio.getvalue()
            if "last_practice_audio" not in st.session_state or st.session_state.last_practice_audio != audio_bytes:
                st.session_state.last_practice_audio = audio_bytes
                with st.spinner("AIが発音を厳しく判定中..."):
                    try:
                        mime_type = practice_audio.type if hasattr(practice_audio, 'type') else "audio/wav"
                        audio_data = {"mime_type": mime_type, "data": audio_bytes}
                        transcriber = genai.GenerativeModel(selected_model)
                        res = transcriber.generate_content([audio_data, "聞こえた英語をそのまま文字起こししてください。文字のみを出力してください。"])
                        
                        if res.parts:
                            user_spoken_text = res.text.strip()
                            st.write(f"🎤 あなたの発音: **{user_spoken_text}**")
                            
                            judge_prompt = f"""
                            お手本の英文:「{target_practice_text}」
                            ユーザーの発音:「{user_spoken_text}」
                            
                            上記を比較し、ユーザーがお手本と【一言一句同じ】に発音できたかを厳格に判定してください。
                            - 1単語でも違いや抜け漏れ、余計な単語があれば、容赦なく「どこが違ったか」を指摘してください。
                            - 完璧に一致した場合のみ合格としてください。
                            - 忖度や過剰な励ましは一切不要です。日本語で簡潔に（1〜2文）出力してください。
                            """
                            judge_model = genai.GenerativeModel(selected_model)
                            judge_res = judge_model.generate_content(judge_prompt)
                            
                            st.success(f"🤖 AI判定: {judge_res.text.strip()}")
                            update_session_stats("practice_attempts")
                        else:
                            st.warning("音声から文字を抽出できませんでした。")
                    except Exception as e:
                        st.error("エラー: もう少しゆっくり、はっきりと話してみてください。")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ 練習完了！次へ進む", type="primary", use_container_width=True):
                prompt = "（リピート練習を完了しました。先ほどの続きから、会話を再開するための新しい質問を英語でしてください。）"
                display_prompt = "（✅ リピート練習を完了し、次へ進みました）"
        with col2:
            if st.button("↩️ 練習せず、1つ前の質問に答え直す (Undo)", use_container_width=True):
                if len(st.session_state.messages) >= 3:
                    st.session_state.messages = st.session_state.messages[:-2]
                    
                    re_model = genai.GenerativeModel(selected_model, system_instruction=system_instruction)
                    formatted_history = []
                    for m in st.session_state.messages:
                        r = "model" if m["role"] == "assistant" else "user"
                        formatted_history.append({"role": r, "parts": [m["content"]]})
                        
                    st.session_state.chat_session = re_model.start_chat(history=formatted_history)
                    st.session_state.last_played_msg_idx = -1
                    st.rerun()
                else:
                    st.warning("これ以上巻き戻せません。最初からやり直してください。")
            
    else:
        # ＝＝＝ 🗣️ 通常モードの画面 ＝＝＝
        st.write("🗣️ **あなたのターン（回答を録音して送信）**")

        if st.button("🔄 今の質問をもう一度聞く（別の言い方で答え直したい時など）"):
            prompt = "すみません、あなたの今の質問にもう一度別の言い方で答えたいので、全く同じ質問文をもう一度言ってください。新しい質問はしないでください。"
            display_prompt = "（🔄 今の質問をもう一度繰り返してください）"

        # 【メインアクション】
        audio_value = st.audio_input("マイクを押して回答を録音・送信")

        if audio_value is not None:
            audio_bytes = audio_value.getvalue()
            if "last_audio_bytes" not in st.session_state or st.session_state.last_audio_bytes != audio_bytes:
                st.session_state.last_audio_bytes = audio_bytes
                with st.spinner("音声を文字に変換しています..."):
                    try:
                        mime_type = audio_value.type if hasattr(audio_value, 'type') else "audio/wav"
                        audio_data = {"mime_type": mime_type, "data": audio_bytes}
                        transcriber = genai.GenerativeModel(selected_model)
                        res = transcriber.generate_content([audio_data, "聞こえた英語をそのまま文字起こししてください。文字のみを出力してください。"])
                        
                        if res.parts:
                            prompt = res.text.strip()
                            display_prompt = prompt
                        else:
                            st.warning("音声から文字を抽出できませんでした。")
                    except Exception as e:
                        st.error("エラー: もう少しゆっくり、はっきりと話してみてください。")

        st.markdown("---")
        
        with st.container(border=True):
            st.write("🛠️ **お助けツール（※これらを使っても会話は先に進みません）**")

            st.write("💡 **① お助け翻訳（言いたいことが英語で出てこない時）**")
            with st.form("translation_form", clear_on_submit=False):
                col1, col2 = st.columns([4, 1])
                with col1:
                    jp_text = st.text_input("日本語で入力:", label_visibility="collapsed", placeholder="例: もう一度ゆっくり言ってください")
                with col2:
                    trans_btn = st.form_submit_button("英訳する🔄")
                    
            if trans_btn and jp_text:
                with st.spinner("AIが英訳を考えています..."):
                    try:
                        translator = genai.GenerativeModel(selected_model)
                        trans_prompt = f"以下の日本語を、英会話のセリフとして自然な英語に翻訳してください。出力は英語のセリフのみとし、解説や前置きは一切不要です。\n\n日本語: {jp_text}"
                        trans_res = translator.generate_content(trans_prompt)
                        st.success(f"✨ こんな風に言ってみましょう！\n\n### {trans_res.text.strip()}\n\n👆 少し上のマイクボタンを押して、声に出して読んでみてください。")
                    except Exception as e:
                        st.error("翻訳中にエラーが発生しました。")
            
            st.write("📖 **② 英単語を調べる**")
            with st.form("dictionary_form", clear_on_submit=False):
                col1, col2 = st.columns([4, 1])
                with col1:
                    dict_word = st.text_input("わからない単語の意味を調べる:", label_visibility="collapsed", placeholder="英単語を入力 (例: evidence)")
                with col2:
                    dict_btn = st.form_submit_button("調べる🔍")
            
            if dict_btn and dict_word:
                with st.spinner("調べています..."):
                    try:
                        dictionary_ai = genai.GenerativeModel(selected_model)
                        dict_res = dictionary_ai.generate_content(f"英単語「{dict_word}」の主な意味と、簡単な例文を1つ（日本語訳付きで）教えてください。簡潔に。")
                        st.info(f"📖 **辞書:**\n{dict_res.text.strip()}")
                    except Exception as e:
                        st.error("検索に失敗しました。")
            
            st.write("🇯🇵 **③ 直前のAIのセリフの日本語訳**")
            if st.button("直前のセリフの「日本語訳」だけを見る"):
                if last_msg and last_msg["role"] == "assistant" and "[英語の質問]" in last_msg["content"]:
                    eng_q = last_msg["content"].split("[英語の質問]")[1].strip()
                    with st.spinner("翻訳中..."):
                        try:
                            translator = genai.GenerativeModel(selected_model)
                            res = translator.generate_content(f"以下の英語を日本語に翻訳してください。出力は日本語のみで簡潔に。\n\n{eng_q}")
                            st.info(f"🇯🇵 **日本語訳:**\n{res.text.strip()}")
                        except Exception as e:
                            st.error("翻訳に失敗しました。")
                else:
                    st.warning("翻訳できる質問が見つかりませんでした。")
            
            st.write("🧠 **④ ちょい足しヒント（自力で答えるためのアシスト）**")
            with st.form("hint_form", clear_on_submit=False):
                hint_col1, hint_col2 = st.columns([3, 2])
                with hint_col1:
                    hint_type = st.selectbox(
                        "どんなヒントが欲しいですか？",
                        ["使うべき英単語を3つ教えて", "文の出だし（最初の3〜4語）を教えて", "何て答えればいいか、日本語でアイデアを教えて"],
                        label_visibility="collapsed"
                    )
                with hint_col2:
                    hint_btn = st.form_submit_button("ヒントをもらう🆘")
                    
                if hint_btn:
                    if last_msg and last_msg["role"] == "assistant" and "[英語の質問]" in last_msg["content"]:
                        eng_q = last_msg["content"].split("[英語の質問]")[1].strip()
                        with st.spinner("ヒントを作成中..."):
                            try:
                                hint_ai = genai.GenerativeModel(selected_model)
                                if hint_type == "使うべき英単語を3つ教えて":
                                    hint_prompt = f"以下の質問に答えるために役立つ英単語（または熟語）を3つだけ、日本語の意味を添えて箇条書きで教えてください。英語の正解は絶対に書かないでください。\n質問: {eng_q}"
                                elif hint_type == "文の出だし（最初の3〜4語）を教えて":
                                    hint_prompt = f"以下の質問に答えるための、自然な英文の書き出し（最初の3〜5語のみ）を1パターンだけ教えてください。日本語訳や解説、文の続きは書かないでください。\n質問: {eng_q}"
                                else:
                                    hint_prompt = f"以下の質問に対して、どのような内容を答えればよいか、日本語で簡潔に2つのアイデア（方向性）を提案してください。英語の解答例は書かないでください。\n質問: {eng_q}"
                                hint_res = hint_ai.generate_content(hint_prompt)
                                st.info(f"💡 **ヒント:**\n{hint_res.text.strip()}")
                            except Exception as e:
                                st.error("ヒントの作成に失敗しました。")
                    else:
                        st.warning("ヒントを出せる質問が見つかりませんでした。")
            
            # ★新機能：文法解説機能
            st.write("📚 **⑤ 文法について詳しく学ぶ**")
            with st.form("grammar_form", clear_on_submit=False):
                col1, col2 = st.columns([4, 1])
                with col1:
                    grammar_topic = st.selectbox(
                        "文法トピックを選択:",
                        list(GRAMMAR_REFERENCE.keys()),
                        label_visibility="collapsed"
                    )
                with col2:
                    grammar_btn = st.form_submit_button("📖 詳しく学ぶ")
            
            if grammar_btn:
                if grammar_topic in GRAMMAR_REFERENCE:
                    grammar_data = GRAMMAR_REFERENCE[grammar_topic]
                    
                    st.info(f"### {grammar_topic}")
                    
                    st.write(f"**📖 ルール:** {grammar_data['rule']}")
                    
                    st.write("**✅ 正しい例文:**")
                    for example in grammar_data['examples']:
                        st.markdown(f"- **{example['en']}**\n  → {example['ja']}")
                    
                    st.write("**❌ よくある間違い:**")
                    for mistake in grammar_data['mistakes']:
                        st.markdown(f"- {mistake}")
                    
                    st.write(f"**💡 学習のコツ:** {grammar_data['tips']}")
            
            st.write("🏳️ **⑥ どうしても答えられない時**")
            
            if st.button("ギブアップ（解説と回答例を見て、リピート練習へ進む）"):
                prompt = """
                今の質問の意図がわかりません。通信量削減のため、無駄な前置きは一切省き、以下の構成で極めて簡潔に出力してください。今回は【新しい質問は行わず】、私がそのまま復唱できる回答例を提示してください。
                
                [フィードバック]
                - 直前の質問の英語と日本語訳
                - 質問の意図（1文で）
                - この状況での自然な回答例の解説と、【★重要：その回答例の日本語訳】（絶対にここに書いてください）
                
                [リピート練習]
                （私がそのまま復唱して答えるための、英語の回答例のセリフのみ。複数の場合は一番標準的なものを1つだけ。絶対に新しい質問はしないこと）
                """
                display_prompt = "（🏳️ ギブアップして、解説と回答例をリクエストしました）"

    # ========================================================
    # プロンプト送信処理 + リスニング確認クイズ
    # ========================================================
    if prompt and display_prompt:
        st.session_state.messages.append({"role": "user", "content": display_prompt})
        
        with st.spinner("AIが返答を考えています..."):
            try:
                response = st.session_state.chat_session.send_message(prompt)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
                # ★新機能：ミスを検出して統計更新
                if "[フィードバック]" in response.text and "[リピート練習]" in response.text:
                    update_session_stats("mistakes_found")
                else:
                    update_session_stats("total_exchanges")
                
                st.rerun() 
            except Exception as e:
                st.error("返答の作成中にエラーが発生しました。")
    
    # ★新機能：リスニング確認クイズ
    if "chat_session" in st.session_state and len(st.session_state.messages) > 0:
        last_msg = st.session_state.messages[-1]
        if last_msg["role"] == "assistant" and "[英語の質問]" in last_msg["content"]:
            eng_question = last_msg["content"].split("[英語の質問]")[1].strip()
            
            with st.expander("🎧 リスニング確認クイズ（オプション）"):
                st.markdown("**上のAIのセリフをもう一度よく聞いて、内容を確認しましょう**")
                
                with st.spinner("クイズを作成中..."):
                    try:
                        quiz_ai = genai.GenerativeModel(selected_model)
                        quiz_prompt = f"""
                        以下の英語のセリフについて、学習者が内容を理解したか確認する3択問題を日本語で1つだけ作成してください。
                        
                        セリフ: {eng_question}
                        
                        出力フォーマット:
                        [問題日本語]
                        質問の内容や意図を確認する質問を日本語で記載
                        
                        [選択肢]
                        A) ～
                        B) ～
                        C) ～
                        
                        [正解]
                        A（または B, C）
                        """
                        
                        quiz_res = quiz_ai.generate_content(quiz_prompt)
                        quiz_text = quiz_res.text
                        
                        # パースしやすくするために簡単に処理
                        lines = quiz_text.split('\n')
                        
                        st.markdown("**クイズ問題:**")
                        for line in lines:
                            if line.strip() and not line.startswith('['):
                                st.write(line)
                        
                    except Exception as e:
                        st.warning("クイズの作成に失敗しました。スキップしてください。")

else:
    st.info("👈 左側のメニューで役割やシチュエーションを設定し、「▶️ 会話をリセットしてスタート」ボタンを押して開始してください。")

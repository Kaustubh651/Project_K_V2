import streamlit as st
st.set_page_config(page_title="📰 News Uploader", layout="centered")
from newspaper import Article
from transformers import pipeline
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
import os
import tempfile

# --- SETTINGS ---
SHEET_NAME = "Project@KI"
# CREDS_JSON = "gen-lang-client-0709660306-d66c48c393e4.json"
import json
import tempfile

with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w") as tmp:
    creds_dict = dict(st.secrets["google_service_account"])  # Convert AttrDict to dict
    json.dump(creds_dict, tmp)
    tmp_path = tmp.name


# --- Summarizer Pipeline ---
@st.cache_resource
def get_summarizer():
    from huggingface_hub import login
    HUGGINGFACE_TOKEN = st.secrets["huggingface"]["huggingface_token"]
    login(token=HUGGINGFACE_TOKEN)
    return pipeline(
        "summarization",
        model="sshleifer/distilbart-cnn-12-6",
    )

summarizer = get_summarizer()

# --- Google Sheet Setup ---
def setup_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(tmp_path, scope)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open(SHEET_NAME)
        sheet = spreadsheet.sheet1
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(SHEET_NAME)
        sheet = spreadsheet.sheet1
        sheet.append_row(["Title", "Content", "Summary", "Top Image URL", "URL Suffix", "Deep Link URL", "Dynamic Link Name", "Image Tag"])

    return sheet, spreadsheet

# --- Article Extractor ---
def extract_article_data(url):
    article = Article(url)
    article.download()
    article.parse()
    return {
        "title": article.title,
        "content": article.text,
        "top_image": article.top_image
    }

# --- Summarize ---
def summarize_content(text, min_length=30, max_length=400):
    text = re.sub(r"[^a-zA-Z0-9 ]", "", text)
    summary = summarizer(text, max_length=max_length, min_length=min_length, do_sample=False)
    return summary[0]['summary_text'] if summary else "Could not summarize."

# --- Upload Image to Drive ---
def upload_image_to_drive(image_url, file_name):
    img_data = requests.get(image_url).content
    temp_path = os.path.join(tempfile.gettempdir(), file_name)

    with open(temp_path, 'wb') as f:
        f.write(img_data)

    scopes = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_file(tmp_path, scopes=scopes)
    drive_service = build('drive', 'v3', credentials=creds)

    file_metadata = {'name': file_name, 'mimeType': 'image/jpeg'}
    media = MediaFileUpload(temp_path, mimetype='image/jpeg')

    try:
        uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        drive_service.permissions().create(fileId=uploaded_file['id'], body={'role': 'reader', 'type': 'anyone'}).execute()
        image_drive_url = f"https://drive.google.com/uc?export=view&id={uploaded_file['id']}"
    finally:
        media.stream().close()
        os.remove(temp_path)

    return image_drive_url

# --- UI Setup ---



# --- Stylish UI ---
st.markdown("""
    <style>
        .title {
            font-size: 2.2em;
            font-weight: bold;
            color: #1db954;
            text-align: center;
        }
        .subtitle {
            font-size: 1.1em;
            color: #444;
            text-align: center;
            margin-bottom: 25px;
        }
        .stTextInput>div>div>input {
            padding: 10px;
            border-radius: 8px;
        }
        .stSlider {
            padding: 10px 5px 10px 5px;
        }
        .stButton>button {
        background: linear-gradient(90deg, #007BFF, #00C6FF);
        color: white;
        font-weight: 600;
        border: none;
        border-radius: 8px;
        padding: 10px 25px;
        box-shadow: 0 4px 6px rgba(0, 123, 255, 0.2);
        transition: all 0.3s ease;
        }
        .stButton>button:hover {
        transform: scale(1.03);
        box-shadow: 0 6px 12px rgba(0, 123, 255, 0.3);
        }

        .progress-bar-container {
            width: 100%;
            background-color: #ddd;
            border-radius: 5px;
            margin-top: 10px;
        }
        .progress-bar {
            height: 8px;
            border-radius: 5px;
            background: linear-gradient(90deg, #1db954, #1db9aa, #1d76ff);
            background-size: 200% 100%;
            animation: progress-animation 2s infinite linear;
        }
        @keyframes progress-animation {
            0% { background-position: 0% 50%; }
            100% { background-position: 200% 50%; }
        }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="title">📰 News Summarizer & Uploader</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Paste a news article URL, and this app will extract, summarize, upload the image, and save it to Google Sheets.</div>', unsafe_allow_html=True)

# --- Input Section ---
st.markdown("### 🔗 Paste News Article URL")
url_input = st.text_input("", placeholder="e.g. https://www.bbc.com/news/article")

# --- Summary Length Sliders ---
st.markdown("### ✂️ Customize Summary Length")
col1, col2 = st.columns(2)
with col1:
    min_length = st.slider("Minimum Length", min_value=20, max_value=300, value=30, step=10)
with col2:
    max_length = st.slider("Maximum Length", min_value=100, max_value=1000, value=400, step=50)

# --- Process & Upload ---
st.markdown("### 📥 Ready to Go?")
if st.button("🚀 Process and Upload"):
    if not url_input.strip():
        st.warning("⚠️ Please enter a valid URL.")
    elif min_length >= max_length:
        st.warning("⚠️ Minimum length should be less than maximum length.")
    else:
        progress_placeholder = st.empty()
        progress_placeholder.markdown("""
            <div class="progress-bar-container">
                <div class="progress-bar"></div>
            </div>
        """, unsafe_allow_html=True)

        try:
            article_data = extract_article_data(url_input)
            summary = summarize_content(article_data['content'], min_length, max_length)
            uploaded_drive_image_url = upload_image_to_drive(article_data['top_image'], "article_img.jpg")

            sheet, spreadsheet = setup_google_sheet()
            existing_rows = len(sheet.get_all_values())
            news_id = 9663 + existing_rows - 1

            url_suffix = f"News{news_id}"
            deep_link_url = f"https://travclan.com/?screen_code=news_detail&news_id={url_suffix.replace('articleshow', '')}"
            dynamic_link_name = f"News {news_id}"
            img_tag = f'<img src="{uploaded_drive_image_url}" width="200"/>'

            sheet.append_row([
                article_data['title'],
                article_data['content'],
                summary,
                uploaded_drive_image_url,
                url_suffix,
                deep_link_url,
                dynamic_link_name,
                img_tag
            ])

            progress_placeholder.empty()

            st.success("✅ Article successfully uploaded to Google Sheets!")
            st.subheader("📌 Extracted Article")
            st.markdown(f"**Title:** {article_data['title']}")
            st.markdown(f"**Summary:** {summary}")
            st.image(article_data['top_image'], width=400, caption="Top Image")
            st.markdown(f"🔗 [Open Sheet](https://docs.google.com/spreadsheets/d/{spreadsheet.id})")

        except Exception as e:
            progress_placeholder.empty()
            st.error(f"❌ Error occurred: {e}")

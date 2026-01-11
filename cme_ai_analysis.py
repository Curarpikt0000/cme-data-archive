import os
import requests
import yfinance as yf
import pdfplumber
import pandas as pd
from google import genai  # 必须配合 google-genai 库使用
from datetime import datetime, timedelta

# 配置环境变量
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", 
    "Content-Type": "application/json", 
    "Notion-Version": "2022-06-28"
}

def get_ai_analysis():
    if not GOOGLE_API_KEY:
        print("❌ 错误: GOOGLE_API_KEY 未设置")
        return

    # 初始化新版 Gemini 客户端
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
    except Exception as e:
        print(f"❌ 客户端初始化失败: {e}")
        return
    
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}

    # 提取 PDF 信息
    pdf_text = ""
    if os.path.exists("MetalsIssuesAndStopsReport.pdf"):
        with pdfplumber.open("MetalsIssuesAndStopsReport.pdf") as pdf:
            pdf_text = "\n".join([p.extract_text() for p in pdf.pages[:3] if p.extract_text()])

    for metal, sym in tickers.items():
        try:
            # 行情抓取与强制标量处理
            hist = yf.download(sym, period="5d", progress=False)
            if len(hist) < 2:
                p_info = "Price Data Unavailable"
            else:
                # 显式提取数值，防止 Series 报错
                curr_price = float(hist['Close'].iloc[-1])
                prev_price = float(hist['Close'].iloc[-2])
                change = (curr_price - prev_price) / prev_price * 100
                p_info = f"Price {curr_price:.2f} ({change:+.2f}%)"

            # 从 Notion 获取库存详情
            query = requests.post(
                f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
                headers=HEADERS,
                json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                         {"property": "Metal Type", "select": {"equals": metal}}]}}
            ).json()

            if not query.get("results"): continue
            
            page = query["results"][0]
            pid = page["id"]
            props = page["properties"]
            net_chg = props.get("Net Change", {}).get("number", 0)
            dealers = props.get("JPM/Asahi etc Stock change", {}).get("rich_text", [{}])[0].get("plain_text", "None")

            # AI 分析
            prompt = f"分析 {metal} ({date_str})：价格 {p_info}，库存变动 {net_chg}，做市商 {dealers}。PDF摘要：{pdf_text[:800]}。请给2句深度研判。"
            
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            
            # 回填 Notion
            requests.patch(
                f"https://api.notion.com/v1/pages/{pid}",
                headers=HEADERS,
                json={"properties": {
                    "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": response.text}}]}
                }}
            )
            print(f"✅ {metal} 处理成功")

        except Exception as e:
            print(f"❌ {metal} 错误: {e}")

if __name__ == "__main__":
    get_ai_analysis()

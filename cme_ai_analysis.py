import os
import requests
import yfinance as yf
import pdfplumber
from google import genai  # 注意：这里改用了新版库
from datetime import datetime, timedelta

# --- 配置区 ---
# 确保在 GitHub Repository Secrets 中设置了这些变量
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}", 
    "Content-Type": "application/json", 
    "Notion-Version": "2022-06-28"
}

def get_ai_analysis():
    if not GOOGLE_API_KEY:
        print("❌ 错误: 未找到 GOOGLE_API_KEY 环境变量")
        return

    # 初始化新版 Gemini Client
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}

    # 1. 提取 PDF 信息
    pdf_text = ""
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if os.path.exists(pdf_path):
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pdf_text = "\n".join([p.extract_text() for p in pdf.pages[:3] if p.extract_text()])
        except Exception as e:
            print(f"⚠️ PDF 读取失败: {e}")

    # 2. 遍历品种
    for metal, sym in tickers.items():
        try:
            # 价格提取
            hist = yf.download(sym, period="5d", progress=False)
            if len(hist) < 2:
                p_info = "Price data unavailable."
            else:
                last_price = float(hist['Close'].iloc[-1])
                prev_price = float(hist['Close'].iloc[-2])
                change_pct = (last_price - prev_price) / prev_price * 100
                p_info = f"Price {last_price:.2f} ({change_pct:+.2f}%)"

            # Notion 数据查询
            query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
            query_payload = {
                "filter": {
                    "and": [
                        {"property": "Date", "date": {"equals": date_str}},
                        {"property": "Metal Type", "select": {"equals": metal}}
                    ]
                }
            }
            q_res = requests.post(query_url, headers=HEADERS, json=query_payload).json()

            if not q_res.get("results"):
                print(f"ℹ️ {metal} 无记录 ({date_str})")
                continue
            
            page = q_res["results"][0]
            pid = page["id"]
            props = page["properties"]
            
            net_chg = props.get("Net Change", {}).get("number", 0)
            dealers_list = props.get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
            dealers = dealers_list[0]["text"]["content"] if dealers_list else "None"

            # 3. AI 深度研判 (使用新版 SDK 语法)
            prompt = f"分析 {metal} {date_str}：价格 {p_info}，库存变动 {net_chg}，做市商 {dealers}。PDF摘要：{pdf_text[:800]}。请给2句关于挤仓风险或看涨情绪的深度研判。"
            
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            ai_insight = response.text.strip()
            
            # 4. 回填 Notion
            update_payload = {
                "properties": {
                    "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                    "Activity Note": {"rich_text": [{"text": {"content": ai_insight}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} 同步成功")

        except Exception as e:
            print(f"❌ {metal} 错误: {str(e)}")

if __name__ == "__main__":
    get_ai_analysis()

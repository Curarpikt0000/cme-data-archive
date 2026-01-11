import os
import requests
import yfinance as yf
import pdfplumber
import google.generativeai as genai  # 改用这个稳健的导入方式
from datetime import datetime, timedelta

# 配置读取
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def get_ai_analysis():
    if not GOOGLE_API_KEY:
        print("❌ 错误: GOOGLE_API_KEY 为空，请检查 GitHub Secrets")
        return

    # 初始化 (旧版 SDK 语法更稳健)
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

    # 提取 PDF
    pdf_text = ""
    if os.path.exists("MetalsIssuesAndStopsReport.pdf"):
        try:
            with pdfplumber.open("MetalsIssuesAndStopsReport.pdf") as pdf:
                pdf_text = "\n".join([p.extract_text() for p in pdf.pages[:3] if p.extract_text()])
        except: pass

    for metal, sym in tickers.items():
        try:
            # 价格抓取 (修复 Series 报错)
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            
            curr = float(hist['Close'].iloc[-1].iloc[0]) if isinstance(hist['Close'].iloc[-1], (yf.pd.Series, yf.pd.DataFrame)) else float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2].iloc[0]) if isinstance(hist['Close'].iloc[-2], (yf.pd.Series, yf.pd.DataFrame)) else float(hist['Close'].iloc[-2])
            p_info = f"Price {curr:.2f} ({(curr-prev)/prev*100:+.2f}%)"

            # Notion 查询
            q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers,
                              json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                     {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            if not q.get("results"): continue
            
            pid = q["results"][0]["id"]
            props = q["results"][0]["properties"]
            net_chg = props.get("Net Change", {}).get("number", 0)
            
            # AI 研判
            prompt = f"分析 {metal} {date_str}: 价格{p_info}, 库存变动{net_chg}. PDF摘要:{pdf_text[:800]}. 请给2句硬核研判。"
            response = model.generate_content(prompt)
            
            # 回填
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=headers,
                           json={"properties": {
                               "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                               "Activity Note": {"rich_text": [{"text": {"content": response.text}}]}
                           }})
            print(f"✅ {metal} 同步成功")
        except Exception as e:
            print(f"❌ {metal} 出错: {e}")

if __name__ == "__main__":
    get_ai_analysis()

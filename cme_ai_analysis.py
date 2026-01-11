import os
import requests
import yfinance as yf
import pdfplumber
import google.generativeai as genai
from datetime import datetime, timedelta

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_ai_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    model = genai.GenerativeModel('gemini-1.5-flash')
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}

    # 提取 PDF 交割细节供 AI 参考
    pdf_text = ""
    if os.path.exists("MetalsIssuesAndStopsReport.pdf"):
        with pdfplumber.open("MetalsIssuesAndStopsReport.pdf") as pdf:
            pdf_text = "\n".join([p.extract_text() for p in pdf.pages[:3] if p.extract_text()])

    for metal, sym in tickers.items():
        try:
            # 修复 IndexError: 增加长度检查
            hist = yf.download(sym, period="5d")
            if len(hist) < 2: 
                p_info = "Price data unavailable."
            else:
                change = (hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100
                p_info = f"Price {hist['Close'].iloc[-1]:.2f} ({change:+.2f}%)"

            # 从 Notion 获取刚刚 Step 3 填入的库存和商家信息
            q_res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                                 json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                         {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            if not q_res.get("results"): continue
            props = q_res["results"][0]["properties"]
            pid = q_res["results"][0]["id"]
            
            net_chg = props["Net Change"]["number"]
            dealers = props["JPM/Asahi etc Stock change"]["rich_text"][0]["text"]["content"] if props["JPM/Asahi etc Stock change"]["rich_text"] else "None"

            prompt = f"""
            作为金属分析师，分析 {metal} {date_str}：
            价格动态: {p_info}
            库存净变动: {net_chg}
            做市商异动: {dealers}
            交割报告原文摘要: {pdf_text[:1000]}
            
            结合库存流向和商家接货/出货，给出 2 句深度研判。直接说明是否有挤仓风险或机构看涨情绪。
            """
            
            response = model.generate_content(prompt)
            # 修正列名为 Name
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS, 
                          json={"properties": {
                              "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                              "Activity Note": {"rich_text": [{"text": {"content": response.text}}]}
                          }})
            print(f"✅ {metal} AI 分析同步成功")
        except Exception as e: print(f"❌ {metal} AI 错误: {e}")

if __name__ == "__main__":
    get_ai_analysis()

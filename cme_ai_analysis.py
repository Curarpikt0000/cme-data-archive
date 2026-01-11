import os
import requests
import google.generativeai as genai
import yfinance as yf
from datetime import datetime, timedelta

# --- 配置 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = "2e047eb5fd3c80d89d56e2c1ad066138"
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

# 初始化
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

TICKER_MAP = {"Gold": "GC=F", "Silver": "SI=F", "Copper": "HG=F", "Platinum": "PL=F", "Palladium": "PA=F", "Aluminum": "ALI=F", "Zinc": "ZNC=F", "Lead": "LED=F"}

def run_ai_analysis():
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for metal in TICKER_MAP.keys():
        print(f"🤖 正在分析 {metal}...")
        
        # 检索 Notion 数据
        q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, 
                         json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        
        if q.get("results"):
            page = q["results"][0]
            props = page["properties"]
            net_chg = props["Net Change"]["number"] or 0
            
            # 构造 AI 提示词
            prompt = f"分析CME {metal} 今日行情：库存变动 {net_chg}。请给出一句50字内的专业分析。"
            
            try:
                response = model.generate_content(prompt)
                # 检查 Gemini 是否返回了有效内容
                if response.candidates and response.candidates[0].content.parts:
                    ai_note = response.text.strip()
                else:
                    ai_note = "AI 拒绝生成（可能触发安全过滤）"
            except Exception as e:
                # 关键：打印出具体错误到 GitHub 日志
                print(f"❌ Gemini Error for {metal}: {e}")
                ai_note = f"AI 分析生成失败: {str(e)[:50]}"

            # 更新回 Notion
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={
                "properties": {"Activity Note": {"rich_text": [{"text": {"content": ai_note}}]}}
            })
            print(f"✅ {metal} 已更新至 Notion")

if __name__ == "__main__":
    run_ai_analysis()

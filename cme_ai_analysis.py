import os
import requests
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def get_ai_analysis():
    # 强制检查 Key，避免程序静默失败
    if not GOOGLE_API_KEY:
        print("❌ 错误: GOOGLE_API_KEY 为空，请检查 GitHub Secrets 映射名是否匹配")
        return

    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

    for metal, sym in tickers.items():
        try:
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            
            # 强化版标量提取：处理 MultiIndex
            closes = hist['Close'].values.flatten()
            curr, prev = float(closes[-1]), float(closes[-2])
            p_info = f"Price {curr:.2f} ({(curr-prev)/prev*100:+.2f}%)"

            q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers,
                             json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                    {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            if not q.get("results"): continue
            
            pid = q["results"][0]["id"]
            props = q["results"][0]["properties"]
            
            # 读取 Step 3 写入的带数字的内容
            dealers_rt = props.get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
            dealers = dealers_rt[0].get("plain_text", "None") if dealers_rt else "None"
            net_chg = props.get("Net Change", {}).get("number", 0)

            prompt = f"分析 {metal} {date_str}: 价格{p_info}, 库存净变动{net_chg}, 做市商变动详情:{dealers}. 请给2句深度研判。"
            response = model.generate_content(prompt)
            
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=headers,
                           json={"properties": {
                               "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                               "Activity Note": {"rich_text": [{"text": {"content": response.text}}]}
                           }})
            print(f"✅ {metal} AI 分析成功")
        except Exception as e:
            print(f"❌ {metal} 出错: {e}")

if __name__ == "__main__":
    get_ai_analysis()

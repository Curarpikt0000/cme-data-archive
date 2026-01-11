import os, requests, yfinance as yf, google.generativeai as genai
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def run_step_4():
    if not GOOGLE_API_KEY: 
        print("❌ 错误: GOOGLE_API_KEY 为空")
        return
    
    genai.configure(api_key=GOOGLE_API_KEY)
    # 修复 404: 使用标准模型名称
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F", "Copper": "HG=F"}
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

    for metal, sym in tickers.items():
        try:
            # 获取行情并处理 MultiIndex
            hist = yf.download(sym, period="5d", progress=False)
            if hist.empty: continue
            closes = hist['Close'].values.flatten()
            curr, prev = float(closes[-1]), float(closes[-2])
            p_info = f"Price {curr:.2f} ({(curr-prev)/prev*100:+.2f}%)"

            # 查询 Notion 条目
            q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers,
                             json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                                    {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
            if not q.get("results"): continue
            
            page = q["results"][0]
            # 读取由 Step 3 写入的异动数据
            dealers_rt = page["properties"].get("JPM/Asahi etc Stock change", {}).get("rich_text", [])
            dealers = dealers_rt[0].get("plain_text", "None") if dealers_rt else "None"

            # 执行深度研判
            prompt = f"分析 {metal} ({date_str}): 价格{p_info}, 交割异动详情:{dealers}. 请给2句深度市场研判，明确是否存在机构搬货或挤仓倾向。"
            response = model.generate_content(prompt)
            
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=headers,
                           json={"properties": {
                               "Name": {"title": [{"text": {"content": f"AI Insight: {metal} {date_str}"}}]},
                               "Activity Note": {"rich_text": [{"text": {"content": response.text}}]}
                           }})
            print(f"✅ {metal} AI 研判同步成功")
        except Exception as e:
            print(f"❌ {metal} 处理出错: {e}")

if __name__ == "__main__":
    run_step_4()

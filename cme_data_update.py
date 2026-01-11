import os, requests, pdfplumber, json
import google.generativeai as genai
from datetime import datetime, timedelta

# 配置环境
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_ai_extraction(pdf_text):
    """调用 Gemini 分析 PDF 文本并提取异动"""
    if not GOOGLE_API_KEY:
        return None
    
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    你是一个贵金属交割数据专家。请分析以下 CME 报告文本，并提取 Gold, Silver, Platinum, Copper 的 Issues 和 Stops 异动。
    
    要求：
    1. 找到每个品种对应的 Firm Name, 以及它们对应的 Issued 和 Stopped 数量。
    2. 忽略合计(TOTAL)。
    3. 格式要求为 JSON 对象，键为 "Gold", "Silver", "Platinum", "Copper"，值为总结字符串。
    4. 字符串格式示例: "JPM: 500 (Issued) | BOFA: 200 (Stopped)"。如果没有异动，请写 "No significant activity."。
    
    报告文本：
    {pdf_text[:15000]} 
    """
    
    try:
        response = model.generate_content(prompt)
        # 尝试提取 JSON 内容
        content = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(content)
    except Exception as e:
        print(f"❌ AI 解析失败: {e}")
        return None

def run_update():
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path):
        print("❌ 找不到 PDF")
        return

    # 1. 提取文本
    with pdfplumber.open(pdf_path) as pdf:
        # 提取前 8 页，涵盖金银铂铜
        all_text = "\n".join([p.extract_text() for p in pdf.pages[:8] if p.extract_text()])

    # 2. AI 提取异动
    print("🤖 正在调用 Gemini 分析 PDF 异动...")
    extraction = get_ai_extraction(all_text)
    if not extraction: return

    # 3. 同步至 Notion
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    for metal, conclusion in extraction.items():
        q_payload = {
            "filter": {"and": [
                {"property": "Date", "date": {"equals": date_str}},
                {"property": "Metal Type", "select": {"equals": metal}}
            ]}
        }
        res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, json=q_payload).json()
        
        if res.get("results"):
            page_id = res["results"][0]["id"]
            update_payload = {
                "properties": {
                    "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": conclusion}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} 异动分析已更新: {conclusion}")
        else:
            print(f"⚠️ Notion 未找到 {metal} {date_str} 的记录")

if __name__ == "__main__":
    run_update()

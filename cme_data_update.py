import os
import requests
import pdfplumber
import json
from datetime import datetime, timedelta

# --- 配置区 ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def call_gemini_extraction_rest(pdf_text):
    """
    使用 REST API 解决 404 路径问题。
    由于 2.0-flash 配额可能受限，此处使用稳定性更高的 1.5-flash。
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={GOOGLE_API_KEY}"
    
    prompt = f"""
    分析以下 CME 金属交割报告文本，提取 Gold, Silver, Platinum, Copper 的异动细节。
    
    要求：
    1. 找到各个金属下 Issues 或 Stops 数量大于 0 的做市商 (Firm Name)。
    2. 生成事实结论。示例: "JPM: 500 (Issued) | BOFA: 200 (Stopped)"。
    3. 必须严格以 JSON 格式返回，不要 Markdown 标签。
       格式: {{"Gold": "结论", "Silver": "结论", "Platinum": "结论", "Copper": "结论"}}
    4. 若无显著异动，请填 "No significant activity."。

    报告文本：
    {pdf_text[:15000]}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200:
            content = res.json()['candidates'][0]['content']['parts'][0]['text']
            # 清洗 AI 可能带出的 Markdown 代码块
            clean_json = content.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_json)
        else:
            print(f"❌ AI 提取失败 ({res.status_code}): {res.text}")
            return None
    except Exception as e:
        print(f"❌ REST 请求异常: {e}")
        return None

def run_update():
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path):
        print("❌ 找不到 PDF 文件")
        return

    # 1. 提取 PDF 文本
    print("📄 正在从 PDF 提取文本...")
    all_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        # 2026 年报表通常在前 10 页涵盖所有金属
        all_text = "\n".join([p.extract_text() for p in pdf.pages[:10] if p.extract_text()])

    # 2. 调用 AI 进行事实提取
    print("🤖 正在调用 Gemini 分析交割数据...")
    extraction = call_gemini_extraction_rest(all_text)
    if not extraction:
        return

    # 3. 同步至 Notion
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"📅 准备同步日期: {date_str}")

    for metal, conclusion in extraction.items():
        try:
            # 查询 Notion 条目
            query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
            query_payload = {
                "filter": {
                    "and": [
                        {"property": "Date", "date": {"equals": date_str}},
                        {"property": "Metal Type", "select": {"equals": metal}}
                    ]
                }
            }
            res = requests.post(query_url, headers=HEADERS, json=query_payload).json()

            if res.get("results"):
                page_id = res["results"][0]["id"]
                # 更新做市商异动字段
                requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json={
                    "properties": {
                        "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": conclusion}}]}
                    }
                })
                print(f"✅ {metal} 异动填入: {conclusion}")
            else:
                print(f"⚠️ {metal} 在 Notion 中未找到记录")
        except Exception as e:
            print(f"❌ {metal} 同步失败: {e}")

if __name__ == "__main__":
    run_update()

import os, requests, pdfplumber
from datetime import datetime, timedelta

# --- 配置区 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def parse_cme_pdf_2026():
    results = {"Gold": [], "Silver": [], "Platinum": [], "Copper": []}
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): return results

    # 2026 报表核心关键字匹配
    metal_patterns = {"GOLD": "Gold", "SILVER": "Silver", "PLATINUM": "Platinum", "COPPER": "Copper"}
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:10]:
            text = page.extract_text() or ""
            # 锁定 COMEX 金属交割页
            if "EXCHANGE: COMEX" not in text.upper(): continue
            
            current_metal = next((v for k, v in metal_patterns.items() if k in text.upper()), None)
            if not current_metal: continue

            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # 适应 2026 行布局
                    if not row or len(row) < 4: continue
                    name = str(row[-3]).strip().replace('\n', ' ')
                    if any(x in name.upper() for x in ["TOTAL", "FIRM", "BUSINESS"]): continue
                    
                    try:
                        issued = str(row[-2]).replace(',', '').strip()
                        stopped = str(row[-1]).replace(',', '').strip()
                        
                        acts = []
                        if issued.isdigit() and int(issued) > 0: acts.append(f"{issued} (Issued)")
                        if stopped.isdigit() and int(stopped) > 0: acts.append(f"{stopped} (Stopped)")
                        
                        if acts and len(name) > 2:
                            results[current_metal].append(f"{name}: {' | '.join(acts)}")
                    except: continue
    return results

def run_update():
    # 修复逻辑：补全循环体，解决 IndentationError
    movement_data = parse_cme_pdf_2026()
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for metal, results in movement_data.items():
        info = " | ".join(results) if results else "No significant activity."
        # 查询 Notion
        query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
        payload = {"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                    {"property": "Metal Type", "select": {"equals": metal}}]}}
        res = requests.post(query_url, headers=HEADERS, json=payload).json()
        
        if res.get("results"):
            page_id = res["results"][0]["id"]
            update_payload = {
                "properties": {
                    "JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": info}}]}
                }
            }
            requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json=update_payload)
            print(f"✅ {metal} 同步成功: {info[:30]}...")

if __name__ == "__main__":
    run_update()

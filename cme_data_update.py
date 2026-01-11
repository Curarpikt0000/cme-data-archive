import os, requests, pdfplumber, re
from datetime import datetime, timedelta

# 配置
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def parse_cme_pdf():
    results = {"Gold": [], "Silver": [], "Platinum": [], "Copper": []}
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): return results

    metal_map = {"GOLD": "Gold", "SILVER": "Silver", "PLATINUM": "Platinum", "COPPER": "Copper"}
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:8]:
            text = page.extract_text() or ""
            current_metal = next((v for k, v in metal_map.items() if k in text.upper() and "ISSUES AND STOPS" in text.upper()), None)
            if not current_metal: continue

            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 4: continue
                    name = str(row[0]).strip().replace('\n', ' ')
                    if name in ["TOTAL", "Firm Name", "None", ""] or "SERVICE" in name.upper(): continue
                    
                    # 提取数值 (Issues 在列2, Stops 在列3)
                    issued = str(row[2]).replace(',', '').strip()
                    stopped = str(row[3]).replace(',', '').strip()
                    
                    acts = []
                    if issued.isdigit() and int(issued) > 0: acts.append(f"{issued} (Issued)")
                    if stopped.isdigit() and int(stopped) > 0: acts.append(f"{stopped} (Stopped)")
                    
                    if acts:
                        results[current_metal].append(f"{name}: {' | '.join(acts)}")
    
    return {k: (" | ".join(v) if v else "No significant activity.") for k, v in results.items()}

def run_update():
    data = parse_cme_pdf()
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for metal, info in data.items():
        q = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS,
            json={"filter": {"and": [{"property": "Date", "date": {"equals": date_str}},
                                   {"property": "Metal Type", "select": {"equals": metal}}]}}).json()
        if q.get("results"):
            pid = q["results"][0]["id"]
            requests.patch(f"https://api.notion.com/v1/pages/{pid}", headers=HEADERS,
                json={"properties": {"JPM/Asahi etc Stock change": {"rich_text": [{"text": {"content": info}}]}}})
            print(f"✅ {metal} 数据已写入: {info}")

if __name__ == "__main__": run_update()

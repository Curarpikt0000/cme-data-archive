import os, requests, pdfplumber
from datetime import datetime, timedelta

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def parse_2026_cme_pdf():
    results = {"Gold": [], "Silver": [], "Platinum": [], "Copper": []}
    pdf_path = "MetalsIssuesAndStopsReport.pdf"
    if not os.path.exists(pdf_path): return results

    # 针对 2026 年报表标题的精准匹配逻辑
    metal_patterns = {
        "GOLD": "Gold", 
        "SILVER": "Silver", 
        "PLATINUM": "Platinum", 
        "COPPER": "Copper"
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:10]:
            text = page.extract_text() or ""
            # 2026 年关键特征：EXCHANGE: COMEX 搭配具体 CONTRACT 名称
            if "EXCHANGE: COMEX" not in text.upper(): continue
            
            current_metal = None
            for key, val in metal_patterns.items():
                if key in text.upper():
                    current_metal = val
                    break
            if not current_metal: continue

            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # 2026 年行格式：[FIRM #, ORIG, FIRM NAME, ISSUED, STOPPED]
                    if not row or len(row) < 4: continue
                    row_str = " ".join([str(cell) for cell in row if cell])
                    
                    # 过滤页眉和汇总行
                    if any(x in row_str.upper() for x in ["TOTAL", "BUSINESS DATE", "CONTRACT"]): continue
                    
                    # 针对不同列数自适应提取 (ISSUED 通常在倒数第二列, STOPPED 在倒数第一列)
                    try:
                        name = str(row[-3]).strip().replace('\n', ' ')
                        issued = str(row[-2]).replace(',', '').strip()
                        stopped = str(row[-1]).replace(',', '').strip()
                        
                        acts = []
                        if issued.isdigit() and int(issued) > 0: acts.append(f"{issued} (Issued)")
                        if stopped.isdigit() and int(stopped) > 0: acts.append(f"{stopped} (Stopped)")
                        
                        if acts and len(name) > 3:
                            results[current_metal].append(f"{name}: {' | '.join(acts)}")
                    except: continue
    
    return {k: (" | ".join(v) if v else "No activity.") for k, v in results.items()}

def run_update():
    data = parse_2026_cme_pdf()
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    for metal, info in data.items():
        # 执行 Notion PATCH 逻辑 (同前)
        # ...

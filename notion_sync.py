import os
import requests
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
# 你的 Database ID
DATABASE_ID = "2e047eb5fd3c80d89d56e2c1ad066138"
GITHUB_REPO = "Curarpikt0000/cme-data-archive"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

METALS = {
    "Gold": "Gold_Stocks.xls",
    "Silver": "Silver_stocks.xls",
    "Copper": "Copper_Stocks.xls",
    "Aluminum": "Aluminum_Stocks.xls",
    "Lead": "Lead_Stocks.xls",
    "Zinc": "Zinc_Stocks.xls",
    "PA-PL": "PA-PL_Stck_Rprt.xls"
}

def get_file_property_item(name, url):
    """针对 Notion 'Files & media' 类型的格式化"""
    return {
        "files": [{
            "name": name,
            "external": {"url": url}
        }]
    }

def sync_to_notion():
    date_str = datetime.now().strftime("%Y-%m-%d")
    delivery_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/data/{date_str}/MetalsIssuesAndStopsReport.pdf"

    for metal_type, file_name in METALS.items():
        stock_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/data/{date_str}/{file_name}"
        
        # 1. 查询是否存在
        query_data = {
            "filter": {
                "and": [
                    {"property": "Date", "date": {"equals": date_str}},
                    {"property": "Metal Type", "select": {"equals": metal_type}}
                ]
            }
        }
        res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=HEADERS, json=query_data).json()
        
        # 2. 构造属性
        properties = {
            "Stock File URL": get_file_property_item(file_name, stock_url),
            "Delivery Notice URL": get_file_property_item("Delivery_Notice.pdf", delivery_url)
        }

        if res.get("results"):
            # 更新
            page_id = res["results"][0]["id"]
            requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json={"properties": properties})
            print(f"Updated {metal_type}")
        else:
            # 新建
            new_page = {
                "parent": {"database_id": DATABASE_ID},
                "properties": {
                    "Name": {"title": [{"text": {"content": f"{metal_type} - {date_str}"}}]},
                    "Date": {"date": {"start": date_str}},
                    "Metal Type": {"select": {"name": metal_type}},
                    **properties
                }
            }
            requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=new_page)
            print(f"Created {metal_type}")

if __name__ == "__main__":
    sync_to_notion()
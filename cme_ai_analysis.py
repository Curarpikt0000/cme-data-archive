import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

class CME_AI_Analyzer:
    def __init__(self):
        # 1. 初始化配置与凭据 (从 GitHub Secrets 读取)
        self.cme_client_id = os.getenv("CME_CLIENT_ID", "api_chao")
        self.cme_client_secret = os.getenv("CME_CLIENT_SECRET")
        self.notion_token = os.getenv("NOTION_TOKEN")
        self.notion_db_id = os.getenv("NOTION_DATABASE_ID", "2e047eb5fd3c80d89d56e2c1ad066138")
        
        self.tickers = {"GC=F": "Gold", "SI=F": "Silver", "PL=F": "Platinum"}
        self.market_data = {}

    def fetch_market_data(self):
        """抓取数据并修复 MultiIndex 索引问题"""
        print(f"[*] 启动数据抓取流水线: {datetime.now()}")
        for ticker in self.tickers.keys():
            df = yf.download(ticker, period="60d", interval="1d", auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df['Volatility'] = (df['High'] - df['Low']) / df['Close']
            df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
            self.market_data[ticker] = df.dropna()
        return self.market_data

    def analyze_logic_chain(self, ticker):
        """核心逻辑链条：价格 + 成交量 + 库存上下文"""
        df = self.market_data.get(ticker)
        metal_name = self.tickers[ticker]
        
        report = {
            "Ticker": ticker,
            "Metal": metal_name,
            "Price_Change": "0.00%",
            "Signal": "NEUTRAL",
            "Logic": "市场横盘整理中。",
            "Vol_Idx": "0.0000"
        }

        if df is None or len(df) < 2:
            return report

        # 转换为标量避免 ValueError
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        p_change = (float(last_row['Close']) - float(prev_row['Close'])) / float(prev_row['Close'])
        vol_surge = float(last_row['Volume']) > (float(last_row['Vol_MA5']) * 1.2)

        # 逻辑增强：结合本地库存文件 (如果 Step 1 已下载)
        inventory_context = ""
        inventory_file = f"{metal_name}_Stocks.xls" if metal_name != "Platinum" else "PA-PL_Stck_Rprt.xls"
        if os.path.exists(inventory_file):
            try:
                # 简单读取最后一行 Net Change
                inv_df = pd.read_excel(inventory_file)
                net_change = inv_df.iloc[-1, 5] # 假设位置在 F 列
                if net_change < 0:
                    inventory_context = f"且库存流出 {abs(net_change)}，供应趋紧。"
            except: pass

        # 最终逻辑判定
        if p_change > 0.01 and vol_surge:
            report.update({"Signal": "STRONG_BULLISH", "Logic": f"价升量增，机构入场显著{inventory_context}"})
        elif p_change < -0.01 and vol_surge:
            report.update({"Signal": "STRONG_BEARISH", "Logic": f"价跌量增，恐慌性抛售{inventory_context}"})
            
        report["Price_Change"] = f"{p_change:.2%}"
        report["Vol_Idx"] = f"{float(last_row['Volatility']):.4f}"
        return report

    def sync_to_notion(self, report):
        """ 更新 Notion 数据库 (由 POST 改为 PATCH 以防止重复行) """
        if not self.notion_token or not self.notion_db_id:
            return

        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 1. 查询 Step 2 创建的现有行
        query_url = f"https://api.notion.com/v1/databases/{self.notion_db_id}/query"
        query_payload = {
            "filter": {
                "and": [
                    {"property": "Date", "date": {"equals": date_str}},
                    {"property": "Metal Type", "select": {"equals": report['Metal']}}
                ]
            }
        }
        
        res = requests.post(query_url, json=query_payload, headers=headers)
        if res.status_code == 200 and res.json().get("results"):
            page_id = res.json()["results"][0]["id"]
            
            # 2. 更新该行数据
            update_url = f"https://api.notion.com/v1/pages/{page_id}"
            # 修正：Ad Name -> Name，移除不存在的 Volatility Index 避免 400 报错
            update_payload = {
                "properties": {
                    "Activity Note": {"rich_text": [{"text": {"content": f"[{report['Signal']}] {report['Logic']}"}}]}
                }
            }
            
            requests.patch(update_url, json=update_payload, headers=headers)
            print(f"✅ {report['Metal']} AI 分析已更新至 Notion 行。")
        else:
            print(f"[?] 未找到 {date_str} 的 {report['Metal']} 记录，请确认 Step 2 是否成功。")

if __name__ == "__main__":
    bot = CME_AI_Analyzer()
    bot.fetch_market_data()
    for ticker in bot.tickers.keys():
        analysis = bot.analyze_logic_chain(ticker)
        bot.sync_to_notion(analysis)

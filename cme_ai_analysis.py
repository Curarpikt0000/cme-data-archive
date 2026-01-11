import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class CME_AI_Analyzer:
    def __init__(self, ticker_list=["GC=F", "SI=F", "PL=F"]):
        """
        初始化 CME 贵金属 AI 分析器
        GC=F: Gold, SI=F: Silver, PL=F: Platinum
        """
        self.tickers = ticker_list
        self.market_data = {}



# ... (类定义保持一致)

    def fetch_data(self, period="60d"):
        for ticker in self.tickers:
            # 关键改动 1: 显式设置 auto_adjust 确保数据结构一致
            data = yf.download(ticker, period=period, interval="1d", auto_adjust=True)
            
            # 关键改动 2: 如果返回的是 MultiIndex，只保留属性层
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            
            data['Volatility'] = (data['High'] - data['Low']) / data['Close']
            data['Vol_MA5'] = data['Volume'].rolling(window=5).mean()
            self.market_data[ticker] = data
        return self.market_data

    def run_logic_chain(self, ticker):
        df = self.market_data[ticker]
        
        # 增加健壮性检查：确保数据足够
        if len(df) < 2:
            return {"Ticker": ticker, "Signal": "INSUFFICIENT_DATA"}

        # 关键改动 3: 使用 .iloc[-1] 获取最后一行 Series
        current_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        # 关键改动 4: 显式转换为标量数值 (float) 避免 Series 对比错误
        price_now = float(current_row['Close'])
        price_prev = float(prev_row['Close'])
        vol_now = float(current_row['Volume'])
        vol_ma5 = float(current_row['Vol_MA5'])
        
        price_change = (price_now - price_prev) / price_prev
        vol_surge = vol_now > (vol_ma5 * 1.2)
        
        # ... (后续信号逻辑逻辑保持一致)
        signal = "NEUTRAL"
        if price_change > 0.01 and vol_surge:
            signal = "STRONG_BULLISH"
        # ...
        
        return {
            "Ticker": ticker,
            "Price_Change": f"{price_change:.2%}",
            "Signal": signal,
            "Volatility_Index": f"{current_row['Volatility']:.4f}"
        }



    def generate_ai_summary(self, logic_results):
        """
        AI 洞察总结（此处模拟调用 LLM API）
        """
        print("\n[AI Market Insights - CME Analysis Summary]")
        print("-" * 50)
        for res in logic_results:
            summary = f"针对 {res['Ticker']}：{res['Logic']} 当前波动率系数为 {res['Volatility_Index']}。"
            print(f"> {summary}")
        
        print("\n[Next Step Suggestion]")
        print("建议密切关注 COMEX 库存变动及 CVOL 指数偏度，确认是否有挤仓风险。")

if __name__ == "__main__":
    analyzer = CME_AI_Analyzer()
    analyzer.fetch_data()
    
    all_results = []
    for t in ["GC=F", "SI=F"]:
        all_results.append(analyzer.run_logic_chain(t))
        
    analyzer.generate_ai_summary(all_results)

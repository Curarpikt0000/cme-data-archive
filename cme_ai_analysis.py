import pandas as pd
import yfinance as yf
import requests

class CME_AI_Analyzer:
    def __init__(self, client_id=None, client_secret=None):
        self.tickers = ["GC=F", "SI=F", "PL=F"]
        self.market_data = {}
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None

    def get_access_token(self):
        """ 获取 CME OAuth Token"""
        if not self.client_id or not self.client_secret:
            return None
        auth_url = "https://auth.cmegroup.com/as/token.oauth2"
        payload = {'grant_type': 'client_credentials', 'client_id': self.client_id, 'client_secret': self.client_secret}
        try:
            r = requests.post(auth_url, data=payload)
            self.token = r.json().get('access_token')
            return self.token
        except Exception as e:
            print(f"Token获取失败: {e}")
            return None

    def fetch_data(self, period="60d"):
        for ticker in self.tickers:
            data = yf.download(ticker, period=period, interval="1d", auto_adjust=True)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            
            # 计算指标并丢弃空值
            data['Volatility'] = (data['High'] - data['Low']) / data['Close']
            data['Vol_MA5'] = data['Volume'].rolling(window=5).mean()
            self.market_data[ticker] = data.dropna()
        return self.market_data

    def run_logic_chain(self, ticker):
        df = self.market_data.get(ticker)
        
        # 核心修复点：初始化所有字段，确保 Schema 一致
        result = {
            "Ticker": ticker,
            "Price_Change": "0.00%",
            "Signal": "NO_DATA",
            "Logic": "数据不足，无法分析。",
            "Volatility_Index": "0.0000"
        }

        if df is None or len(df) < 5:
            return result

        # 转换为标量避免 ValueError
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        p_change = (float(curr['Close']) - float(prev['Close'])) / float(prev['Close'])
        vol_surge = float(curr['Volume']) > (float(curr['Vol_MA5']) * 1.2)
        
        # 逻辑判定
        if p_change > 0.01 and vol_surge:
            result.update({"Signal": "STRONG_BULLISH", "Logic": "价升量增，机构吸筹显著。"})
        elif p_change < -0.01 and vol_surge:
            result.update({"Signal": "STRONG_BEARISH", "Logic": "价跌量增，空头主动杀跌。"})
        else:
            result.update({"Signal": "NEUTRAL", "Logic": "市场波动率正常，处于整理区间。"})
            
        result["Price_Change"] = f"{p_change:.2%}"
        result["Volatility_Index"] = f"{float(curr['Volatility']):.4f}"
        return result

    def generate_ai_summary(self, results):
        print("\n[AI Market Insights - CME Analysis Summary]")
        for res in results:
            # 现在可以安全访问所有 Key 了
            print(f"> {res['Ticker']} [{res['Signal']}]: {res['Logic']} (波动率: {res['Volatility_Index']})")

if __name__ == "__main__":
    # 填入您刚才创建的 api_chao 凭据
    MY_ID = "api_chao"
    MY_SECRET = "T*a@e_*RJg#e@R6g7*Yj6g9_" 
    
    analyzer = CME_AI_Analyzer(MY_ID, MY_SECRET)
    analyzer.fetch_data()
    
    analysis_results = [analyzer.run_logic_chain(t) for t in analyzer.tickers]
    analyzer.generate_ai_summary(analysis_results)

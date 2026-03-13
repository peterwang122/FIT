CREATE TABLE IF NOT EXISTS stock_data (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  ts_code VARCHAR(20) NOT NULL,
  trade_date DATE NOT NULL,
  open DECIMAL(18,4) NOT NULL,
  high DECIMAL(18,4) NOT NULL,
  low DECIMAL(18,4) NOT NULL,
  close DECIMAL(18,4) NOT NULL,
  pre_close DECIMAL(18,4) NOT NULL,
  `change` DECIMAL(18,4) NOT NULL,
  pct_chg DECIMAL(18,4) NOT NULL,
  vol DECIMAL(20,4) NOT NULL,
  amount DECIMAL(20,4) NOT NULL,
  UNIQUE KEY idx_stock_data_code_date (ts_code, trade_date),
  KEY idx_stock_data_ts_code (ts_code),
  KEY idx_stock_data_trade_date (trade_date)
);

export interface MacroPoint {
  trade_date: string
  hs300_pe_ttm: number | null
  csi1000_pe_ttm: number | null
  cn_gov_bond_10y_yield_pct: number | null
  a_share_total_market_cap_cny: number | null
  trailing_4q_nominal_gdp_cny: number | null
  household_deposit_cny: number | null
  hs300_equity_bond_spread_pp: number | null
  hs300_equity_bond_spread_pp_boll_mid: number | null
  hs300_equity_bond_spread_pp_boll_upper: number | null
  hs300_equity_bond_spread_pp_boll_lower: number | null
  csi1000_equity_bond_spread_pp: number | null
  csi1000_equity_bond_spread_pp_boll_mid: number | null
  csi1000_equity_bond_spread_pp_boll_upper: number | null
  csi1000_equity_bond_spread_pp_boll_lower: number | null
  buffett_indicator_pct: number | null
  buffett_indicator_pct_boll_mid: number | null
  buffett_indicator_pct_boll_upper: number | null
  buffett_indicator_pct_boll_lower: number | null
  household_deposit_market_cap_ratio_pct: number | null
  household_deposit_market_cap_ratio_pct_boll_mid: number | null
  household_deposit_market_cap_ratio_pct_boll_upper: number | null
  household_deposit_market_cap_ratio_pct_boll_lower: number | null
  chinext_csi_dividend_ratio: number | null
  chinext_csi_dividend_ratio_ma20: number | null
  chinext_csi_dividend_ratio_upper_1pct: number | null
  chinext_csi_dividend_ratio_lower_1pct: number | null
  chinext_csi_dividend_ratio_boll_upper: number | null
  chinext_csi_dividend_ratio_boll_lower: number | null
  star50_csi_dividend_ratio: number | null
  star50_csi_dividend_ratio_ma20: number | null
  star50_csi_dividend_ratio_upper_1pct: number | null
  star50_csi_dividend_ratio_lower_1pct: number | null
  star50_csi_dividend_ratio_boll_upper: number | null
  star50_csi_dividend_ratio_boll_lower: number | null
  gdp_period_end: string | null
  deposit_period_end: string | null
  market_cap_source: string | null
  market_cap_adjustment_factor: number | null
  gdp_source: string | null
}

export interface MacroDashboard {
  start_date: string
  end_date: string
  latest: MacroPoint | null
  points: MacroPoint[]
  methodology: {
    equity_bond_spread: string
    buffett_indicator: string
    deposit_market_cap_ratio: string
    growth_dividend_ratio: string
  }
}

export interface BankLiquidityDailyPoint {
  trade_date: string
  fr001_pct: number | null
  fr007_pct: number | null
  fdr001_pct: number | null
  fdr007_pct: number | null
  dr001_weighted_pct: number | null
  dr007_weighted_pct: number | null
  r001_weighted_pct: number | null
  r007_weighted_pct: number | null
  reverse_repo_7d_policy_rate_pct: number | null
  reverse_repo_7d_policy_source_date: string | null
  reverse_repo_7d_policy_available_at: string | null
  source_url_reverse_repo_7d_policy: string | null
  bank_bond_aaa_1y_yield_pct: number | null
  cgb_1y_yield_pct: number | null
  factor_fdr007_policy_spread_bp: number | null
  factor_overnight_pressure_bp: number | null
  factor_nonbank_layering_bp: number | null
  factor_bank_funding_spread_bp: number | null
  pct_fdr007_policy_spread: number | null
  pct_overnight_pressure: number | null
  pct_nonbank_layering: number | null
  pct_bank_funding_spread: number | null
  liquidity_tightness_score: number | null
  liquidity_state: '宽松' | '平衡' | '偏紧' | '紧张' | null
  liquidity_trend: '收紧' | '转松' | '平稳' | null
  score_change_5d: number | null
  reverse_repo_injection_cny: number | null
  reverse_repo_maturity_cny: number | null
  reverse_repo_net_cny: number | null
  reverse_repo_net_5d_cny: number | null
  reverse_repo_net_20d_cny: number | null
  frr_source_date: string | null
  frr_available_at: string | null
  closing_repo_source_date: string | null
  closing_repo_available_at: string | null
  chinabond_source_date: string | null
  chinabond_available_at: string | null
  pbc_source_date: string | null
  pbc_available_at: string | null
  source_url_frr: string | null
  source_url_closing_repo: string | null
  source_url_chinabond: string | null
  source_url_pbc: string | null
  components_json: Record<string, unknown> | null
  sources_json: Record<string, unknown> | null
}

export interface PbcLiquidityMonthlyPoint {
  period_end: string
  category: string | null
  tool_type: string
  tool_name: string
  injection_cny: number | null
  withdrawal_cny: number | null
  net_injection_cny: number | null
  coverage_status: string
  published_at: string
  source_url: string
}

export interface BankLiquidityDashboard {
  start_date: string
  end_date: string
  latest: BankLiquidityDailyPoint | null
  daily_points: BankLiquidityDailyPoint[]
  monthly_tool_points: PbcLiquidityMonthlyPoint[]
  coverage: {
    official_history_start: string | null
    score_start: string | null
    closing_repo_start: string | null
    latest_date: string | null
    latest_complete_date: string | null
    monthly_tools_start: string | null
    closing_repo_note: string
    monthly_tools_note: string
  }
  methodology: {
    score: string
    states: string
    trend: string
  }
}

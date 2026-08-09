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

export interface MacroPoint {
  trade_date: string
  hs300_pe_ttm: number | null
  csi1000_pe_ttm: number | null
  cn_gov_bond_10y_yield_pct: number | null
  a_share_total_market_cap_cny: number | null
  trailing_4q_nominal_gdp_cny: number | null
  household_deposit_cny: number | null
  hs300_equity_bond_spread_pp: number | null
  csi1000_equity_bond_spread_pp: number | null
  buffett_indicator_pct: number | null
  household_deposit_market_cap_ratio_pct: number | null
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
  }
}

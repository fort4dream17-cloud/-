# Investor charts and passive-flow interpretation

The index collector now requests 60 exchange sessions of detailed daily investor trading for each constituent. All eleven leaf categories are read directly, including explicit zero observations. Institution total is the sum of the seven institutional subcategories. Government is not separately available and remains null. Missing provider responses retain a prior verified observation when available; they are never filled with synthetic daily allocations of period totals.

The chart offers core five, seven institutions, all twelve (including institution subtotal), and personal/foreign/institution total views. Including a subtotal and its components is useful for comparison but must not be summed again. Incomplete selected series are disclosed beside the chart. Daily quantities are not backfilled by this change.

The table places name, compact two-line signals, and the three-month sparkline before daily return. Signal abbreviations have complete text in their tooltip and the selected stock detail. Extra short-term signals are counted with +N rather than silently discarded.

Passive monitoring needs three independent sources:

1. Official index/ETF announcements: record announcement and effective dates separately.
2. ETF basket/holding disclosures, units outstanding, CU, and creations/redemptions: do not equate rising AUM with net inflows. Basket transfers and actual secondary-market trades differ.
3. Trading evidence: abnormal volume, closing-auction concentration, financial-investment flows, and program/arbitrage activity. A financial-investment net purchase or unrelated block trade alone is insufficient to establish passive activity.

Current ETF/event feeds remain unconnected and are labeled unconfirmed. Confirmed relevant events plus abnormal volume can produce a suspected-passive signal; actual passive money is not deducted from foreign/pension flow. A block-trade event requires a separately verified passive link before participating in that signal.

Sources: https://regulation.krx.co.kr/contents/RGL/03/03060106/RGL03060106.jsp ; https://indices.krx.co.kr/ ; https://github.com/sharebook-kr/pykrx

On collector-code pushes the workflow retains verified NPS disclosures; scheduled and manual runs continue to refresh OpenDART. This avoids unnecessary disclosure scans during a flow-only repair.

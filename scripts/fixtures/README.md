# Operating disclosure regression fixture

`tsmc_2026q2_notes.txt` contains the two balance tables and adjacent explanatory
text extracted from page 31 of TSMC's consolidated 2026Q2 financial report.
Line wrapping is retained to exercise PDF extraction, not manually reformatted.

- Official MOPS document: `202602_2330_AI1.pdf`, downloaded via
  `https://doc.twse.com.tw/server-java/t57sb01` with `co_id=2330`, `year=115`.
- Issuer copy: https://investor.tsmc.com/sites/ir/financial-report/2026/TSMC%202026Q2%20Consolidated%20Financial%20Statements_C.pdf
- Amounts in the fixture are thousands of TWD; output JSON uses TWD.
- Current contract liabilities: 55,852,048,000.
- Customer temporary receipts: current 141,853,142,000; noncurrent 92,372,004,000;
  total 234,225,146,000. These are separate from contract liabilities.

Run `python -m unittest -v test_operating_leads.py test_note_disclosures.py`
from `scripts/`. Run `python validate_operating.py` after both collectors to
validate the saved TSMC notes and 4563 balance-sheet benchmark together.

Each quarterly row includes `data_source` for its default contract balance:
`balance_sheet`, `notes`, or null. The existing per-field `*Source` attributes
preserve the exact source of current/noncurrent/total values. `notesSource` and
`notesPdfFilename` retain acquisition details. Main-statement values take
priority; failed refreshes do not erase previously verified disclosures.

The frontend offers contract liabilities, customer temporary receipts, their
combined operating observation, inventory, and quarterly revenue. The combined
observation is computed only in the view, only for the same quarter and only
when both values exist. It uses the disclosed contract total where available,
otherwise explicitly labels the current portion. It is not an accounting item.

The text fallback requires an explicit quarter-end date column. Unrecognized,
ambiguous, undated, or absent disclosures stay null. The collector uses
consolidated filings; it does not substitute a parent's standalone accounts.

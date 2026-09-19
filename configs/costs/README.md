# configs/costs

Cost profiles per symbol and broker (F-0.2.x): spread (incl. hourly spread profile),
commission model, long/short swap, triple-swap day, slippage (fixed + fraction of ATR).
Validated by Pydantic models; a symbol without a cost profile cannot run.
Populated in task T06.

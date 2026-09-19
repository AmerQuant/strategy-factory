// Print the instrument metadata of the pinned dukascopy-node package as JSON lines:
// {"id","name","description","startHourForTicks","startDayForMinuteCandles","startMonthForHourlyCandles","startYearForDailyCandles"}
// Used by T04b to verify configs/universe/dukascopy.csv. Usage: node list_instruments.js [id ...]
const lib = require("dukascopy-node");
const meta = lib.instrumentMetaData || lib.InstrumentMetaData || {};
const wanted = process.argv.slice(2);
const ids = wanted.length ? wanted : Object.keys(meta);
for (const id of ids) {
  const m = meta[id];
  console.log(JSON.stringify(m ? { id, found: true, ...m } : { id, found: false }));
}

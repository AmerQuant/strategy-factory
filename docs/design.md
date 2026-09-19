**سند طراحی فنی**

**Strategy Factory**

معماری، رابط‌ها، اسکیما داده و رجیستری، و راهبرد تست

**نسخهٔ ۱٫۰ — خروجی فاز ۳ نقشهٔ راه**

مرجع‌ها: سند مشخصات نسخهٔ ۱٫۲ و فیچرلیست

شهریور ۱۴۰۵

**۱. مقدمه و قواعد این سند**

این سند «چطور ساختن» را تعریف می‌کند؛ «چه ساختن» در سند مشخصات نسخهٔ ۱٫۲ و فیچرلیست آمده است. هر جا این سند با سند مشخصات اختلاف داشته باشد، سند مشخصات برای رفتار و این سند برای پیاده‌سازی معتبر است. تغییر هر دو فقط با توافق در چت و ثبت در دفتر تصمیمات (بخش ۱۴) انجام می‌شود.

| **مورد**                     | **مقدار**                                                 |
|-----------------------------------------------------|----------------------------------------------------------------------------------|
| **نام پروژه**                | Strategy Factory                                          |
| **ریپو**                     | strategy-factory                                          |
| **بستهٔ پایتون**              | strategy_factory (در کد: import strategy_factory as sfac) |
| **فرمان CLI**                | sfac                                                      |
| **زبان کد، نام‌ها و کامنت‌ها** | انگلیسی؛ گزارش‌ها و مستندات کاربری فارسی                   |

**۲. استک فنی نهایی**

| **حوزه**             | **انتخاب**                                                           | **دلیل اصلی**                               | **گزینه‌های ردشده**                     |
|---------------------------------------------|---------------------------------------------------------------------------------------------|--------------------------------------------------------------------|---------------------------------------------------------------|
| **موتور بک‌تست**      | اختصاصی با NumPy و Numba                                             | کنترل کامل قراردادها و تطابق با TradingView | vectorbt، VectorBT PRO، NautilusTrader |
| **اوراکل تست موتور** | vectorbt متن‌باز (فقط در tests)                                       | پیاده‌سازی مستقل دوم برای کشف باگ            | —                                      |
| **دادهٔ بازار**       | Parquet + DuckDB                                                     | سریع، بدون سرور، تغییرناپذیری ساده          | TimescaleDB، ArcticDB                  |
| **دیتافریم**         | Polars در لایهٔ داده، pandas در لبه‌ها، NumPy در موتور                 | سرعت روی دادهٔ دقیقه‌ای چندساله               | فقط pandas، فقط Polars                 |
| **رجیستری**          | PostgreSQL (Docker) + SQLAlchemy Core + psycopg 3 + Alembic          | هم‌زمانی تیمی و نوشتن دسته‌ای با COPY         | SQLite، MLflow                         |
| **اجرای موازی**      | دوسطحی: prange در Numba + ProcessPool                                | حافظهٔ مشترک، بدون وابستگی اضافه             | Joblib، Ray                            |
| **جستجوی پارامتر**   | گرید کامل؛ بالای ۲۰۰۰ نمونه‌گیری یکنواخت (Sobol)                      | SPP و تشخیص پلاتو نااریب                    | Optuna                                 |
| **کانفیگ و CLI**     | Typer + YAML با اعتبارسنجی Pydantic                                  | سادگی و خطای زودهنگام                       | Hydra، Prefect/Dagster                 |
| **گزارش HTML**       | Jinja2 + Plotly، فایل خودبسنده                                       | بایگانی‌پذیر، سازگار با داشبوردهای فعلی      | Streamlit/Dash، Quarto                 |
| **گزارش مرحلهٔ ۸**    | پکیج JSON + پرامپت؛ Claude چت فایل ورد را می‌سازد؛ sfac report verify | بدون API و بدون رندرکنندهٔ داخلی             | API LLM، رندر docx-js                  |
| **محیط و کیفیت**     | uv، پایتون ۳٫۱۲، pytest، Hypothesis، ruff، mypy                      | سرعت و تست ویژگی‌محور موتور                  | Poetry، conda، pyright                 |
| **CI**               | GitHub Actions                                                       | تست‌های parity و leakage اجباری              | —                                      |

**۳. ساختار ریپو**

```
strategy-factory/
├── CLAUDE.md # rules for Claude Code (source of truth for conventions)
├── pyproject.toml uv.lock
├── docker-compose.yml # postgres only
├── docs/
│ ├── spec/ # specification v1.2 (docx + md export)
│ ├── features.md # feature list (generated from xlsx)
│ ├── design.md # this document (md export)
│ └── adr/ # architecture decision records
├── configs/
│ ├── universe.yaml costs/*.yaml gates/*.yaml pipeline/*.yaml
├── data/ # parquet store (git-ignored)
├── artifacts/ # run artifacts (git-ignored)
├── src/strategy_factory/
│ ├── core/ # StrategySpec, Candidate, Artifact base, RunContext, ids/hashing
│ ├── data/ # schema, adapters/, quality, resample, store, catalog, split, aux
│ ├── costs/ # cost profiles, spread profile, swap
│ ├── engine/ # numba kernels, fills, exits, intrabar modes, multi-strategy
│ ├── components/ # indicators/, entries/, exits/, filters/, sizing/, registry
│ ├── metrics/ baseline/ diagnostics/ robustness/ stats/
│ ├── registry/ # sqlalchemy tables, batch writer, queries, alembic/
│ ├── gates/ # declarative gate engine
│ ├── stages/ # s00_... s12_ one module per stage
│ ├── pipeline/ # orchestrator, executor, checkpoints
│ ├── reports/ # jinja templates, plotly figures, assets/fonts/Vazirmatn
│ ├── evidence/ # bundle builder, prompt package, verify
│ └── cli.py # typer app: sfac
├── tests/
│ ├── unit/ property/ parity/ leakage/ oracle/ selftest/ fixtures/
└── .github/workflows/ci.yml
```

**قواعد وابستگی بین ماژول‌ها**

- **engine** به هیچ ماژول دیگری جز NumPy و Numba وابسته نیست؛ ورودی آرایه، خروجی آرایه.

- **components** و **metrics** فقط به core و engine وابسته‌اند.

- **stages** تنها لایه‌ای است که همه‌چیز را کنار هم می‌گذارد؛ و فقط از طریق RunContext به داده و رجیستری دسترسی دارد.

- **data** تنها جایی است که Polars استفاده می‌شود؛ مرز خروجی آن آرایهٔ NumPy یا DataFrame پانداس برای لبه‌هاست.

- هیچ ماژولی مستقیم فایل هولدآوت را نمی‌خواند؛ فقط SplitManager.

**۴. مفاهیم هسته و رابط‌ها**

همهٔ مدل‌ها Pydantic هستند، تغییرناپذیرند (frozen) و به JSON سریال می‌شوند. شناسه‌ها از هش محتوای کانونیکال ساخته می‌شوند تا تکرارپذیری تضمین شود.

**مدل‌های استراتژی و کاندید**

```
class ComponentRef(BaseModel): # e.g. entry "rsi_threshold"
    name: str; params: dict[str, float | int | str]
 
class StrategySpec(BaseModel):
    entry: ComponentRef
    exit: list[ComponentRef] # "first-hit" combination
    filters: list[ComponentRef] = []
    sizing: ComponentRef # default: fixed_notional 100_000
    disaster_stop_atr: float = 3.0
    def spec_hash(self) -> str: ... # sha256 of canonical json
 
class Candidate(BaseModel):
    id: str # hash(symbol, tf, direction, edge, spec)
    parent_id: str | None # lineage through the funnel
    symbol: str; timeframe: str
    direction: Literal["long", "short"]
    edge_type: Literal["MR", "TF", "SEASONAL"]
    spec: StrategySpec
```

**زمینهٔ اجرا و رابط مرحله**

```
class RunContext:
    config: PipelineConfig # validated YAML
    data: DataAccess # dev segment only; bars as numpy/pandas
    split: SplitManager # the ONLY path to holdout (locked, logged)
    registry: RegistryWriter # batched writes
    executor: Executor # process pool; numba prange inside
    gates: GateEngine
    seed: int
 
class Stage(Protocol):
    name: str # "s03_entry_opt"
    def run(self, cands: list[Candidate], ctx: RunContext) -> StageResult: ...
 
class StageResult(BaseModel):
    artifacts: list[ArtifactRef]
    passed: list[Candidate]
    gate_results: list[GateResult]
```

**گیت**

```
class GateCriterion(BaseModel):
    metric: str; op: Literal[">=", "<=", ">", "<", "=="]; threshold: float
    critical: bool = False # stage-6 blocks: WF, cost x2, holdout
 
class GateResult(BaseModel):
    candidate_id: str; stage: str
    items: list[CriterionResult] # value, threshold, passed, reason
    passed: bool
    borderline: bool # exactly one non-critical fail within 10%
```

**موتور (امضای کلی — جزئیات در F-0.3.x)**

```
@njit(cache=True)
def simulate(open_, high, low, close, atr, # float64[n]
             entry_sig, exit_sig, # bool[n] (evaluated at close)
             direction, time_exit_bars,
             sl_atr, tp_atr, trail_atr, disaster_atr,
             half_spread, slippage_fixed, slippage_atr_frac, # float64[n] (hourly profile)
             swap_long, swap_short, rollover_mask, triple_mask,
             notional, intrabar_mode, # 0=tradingview, 1=pessimistic
             ) -> tuple[TradesArray, EquityArray]: ...
 
@njit(parallel=True, cache=True)
def simulate_grid(..., entry_sig_matrix): # prange over parameter sets
```

**۵. لایهٔ داده**

**اسکیما استاندارد بار**

| **ستون**                   | **نوع**             | **اجباری** | **توضیح**                               |
|---------------------------------------------------|--------------------------------------------|-----------------------------------|----------------------------------------------------------------|
| **ts**                     | datetime\[us, UTC\] | بله        | زمان شروع بار                           |
| **open, high, low, close** | float64             | بله        | قیمت trade یا mid                       |
| **volume**                 | float64             | بله        | حجم منبع؛ برای Dukascopy حجم داخلی منبع |
| **vwap, trades**           | float64, int64      | خیر        | Alpaca                                  |
| **spread**                 | float64             | خیر        | ask − bid، از Dukascopy                 |

**متادیتای سری**

source، source_symbol، symbol، asset_class، timeframe، price_type (trade/bid/ask/mid)، adjustment (raw/split/all/unknown)، session (RTH/ETH/24x5)، feed (iex/sip/—)، original_tz، downloaded_at، snapshot_hash، row_count، first_ts، last_ts.

**چیدمان ذخیره و کاتالوگ**

```
data/<source>/<symbol>/<timeframe>/<snapshot_hash>.parquet
data/catalog.parquet # one row per snapshot: metadata + quality summary + is_reference
```

- اسنپ‌شات پس از نوشتن فقط‌خواندنی است؛ هش از محتوای نرمال‌شده (نه فایل) محاسبه می‌شود.

- برای هر نماد دقیقاً یک اسنپ‌شات «مرجع» در کاتالوگ علامت دارد؛ تغییر مرجع یک رویداد ثبت‌شده است.

- **بازنمونه‌گیری:** مرز روز ۰۰:۰۰ UTC؛ ساعات یکشنبهٔ فارکس و طلا در دوشنبه ادغام می‌شود؛ حالت broker_session فقط برای Parity.

- **کیفیت:** سه سطح critical / warning / info؛ critical اجرای قیف را برای آن نماد متوقف می‌کند.

- **تقسیم داده:** SplitManager مرزهای توسعه، Embargo و هولدآوت را از کاتالوگ و کانفیگ محاسبه و در رجیستری ثبت می‌کند؛ DataAccess فقط بخش توسعه را برمی‌گرداند.

**۶. موتور: قراردادهای اجرا**

این قراردادها باید دقیقاً پیاده شوند و هر کدام تست واحد و تست ویژگی‌محور دارد.

**ترتیب رویدادها در هر کندل**

- **اوپن کندل j:** اجرای سفارش‌های زمان‌بندی‌شده در کلوز j−1 (ورود یا خروج). اگر قیمت با گپ از استاپ عبور کرده، خروج در همان اوپن (قیمت بدتر).

- **درون کندل j:** بررسی SL، TP و استاپ فاجعه با High و Low. اگر بیش از یکی لمس شد: حالت ۰ = منطق TradingView (نزدیک‌تر به اوپن اول)، حالت ۱ = بدبینانه (استاپ اول)؛ حل با دادهٔ دقیقه‌ای در P1.

- **کلوز کندل j:** ارزیابی سیگنال ورود، سیگنال خروج و خروج زمانی؛ زمان‌بندی برای اوپن j+1. ثبت اکوئیتی Mark-to-Market.

- **رول‌اور:** در ساعت رول‌اور پروفایل هزینه، سواپ برای پوزیشن باز کسر یا اضافه می‌شود؛ روز سه‌برابر از پروفایل.

**قیمت اجرا و هزینه**

- قیمت پایه trade یا mid است. ورود لانگ = قیمت + نیم‌اسپرد + اسلیپیج؛ خروج لانگ = قیمت − نیم‌اسپرد − اسلیپیج؛ شورت برعکس.

- اسلیپیج = مقدار ثابت + کسری از ATR کندل سیگنال. نیم‌اسپرد از پروفایل ساعتی (یا عدد ثابت در MVP).

- کمیسیون طبق مدل پروفایل (درصدی، سهمی یا لاتی) در ورود و خروج.

- حجم: notional ثابت ۱۰۰٬۰۰۰ دلار؛ مقدار = notional ÷ قیمت ورود. یک پوزیشن هم‌زمان برای هر استراتژی (بدون پله‌ای).

- استاپ فاجعه = قیمت ورود ∓ ۳ × ATR کندل سیگنال؛ ثابت و بهینه‌نشدنی.

**خروجی موتور**

| **آرایه**       | **فیلدها**                                                                                                                                                        |
|----------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **TradesArray** | entry_idx، exit_idx، entry_price، exit_price، qty، direction، pnl_gross، costs (spread، slippage، commission، swap)، pnl_net، exit_reason، mae، mfe، atr_at_entry |
| **EquityArray** | equity_mtm در کلوز هر کندل، in_position، realized_pnl                                                                                                             |

**ثابت‌های تست ویژگی‌محور (Hypothesis)**

- جمع pnl_net تریدها + سود باز = اکوئیتی نهایی − سرمایهٔ اولیه.

- هیچ ورود یا خروجی در همان کندلی که سیگنالش ساخته شده اجرا نمی‌شود.

- افزایش هر مؤلفهٔ هزینه هرگز سود را افزایش نمی‌دهد.

- نتیجهٔ کندل‌های ۰ تا t با حذف داده‌های بعد از t تغییر نمی‌کند (نشت).

- آینه: شورت روی سری قیمت معکوس معادل لانگ روی سری اصلی است (با هزینهٔ صفر).

**۷. رجیستری (PostgreSQL)**

| **جدول**           | **محتوا**                                                                                    | **نکته**                     |
|-------------------------------------------|---------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------|
| **pipeline_runs**  | شناسه، کانفیگ کامل، هش کانفیگ، نسخهٔ کد (git sha)، seed، زمان شروع و پایان، وضعیت             | واحد بازتولید                |
| **data_snapshots** | هش، منبع، نماد، تایم‌فریم، مرجع بودن                                                          | آینهٔ کاتالوگ                 |
| **splits**         | نماد، تایم‌فریم، مرز توسعه، Embargo، مرز هولدآوت، ترید مورد انتظار                            |                              |
| **candidates**     | شناسه، parent_id، نماد، تایم‌فریم، جهت، نوع اج، spec (JSONB)، مرحلهٔ فعلی، وضعیت               | شجرهٔ قیف                     |
| **trials**         | شناسه، run، stage، candidate، family_id، params (JSONB)، متریک‌های اصلی (ستون)، extra (JSONB) | میلیون‌ها ردیف؛ نوشتن با COPY |
| **gate_results**   | candidate، stage، معیار، مقدار، آستانه، عبور، critical، دلیل                                 |                              |
| **artifacts**      | candidate، stage، نوع، مسیر فایل، نسخهٔ اسکیما، هش                                            | فایل‌ها روی دیسک              |
| **holdout_access** | candidate، زمان، نتیجه، consumed                                                             | دسترسی دوم مسدود             |
| **reports**        | candidate، مسیر docx، نسخهٔ پرامپت، نتیجهٔ verify، تاریخ                                       | مرحلهٔ ۸                      |
| **decisions**      | candidate، تحلیلگر، تصمیم، مرحلهٔ بازگشت، دلیل                                                | مرحلهٔ ۹                      |

- **منحنی اکوئیتی و فهرست تریدها** برای همهٔ سلول‌های گرید ذخیره نمی‌شود؛ فقط برای کاندیدهای عبوری از هر گیت، به‌صورت Parquet در artifacts. بقیه با sfac reproduce قابل بازسازی‌اند.

- **نوشتن:** worker‌ها نتایج را به پردازش اصلی برمی‌گردانند؛ RegistryWriter در دسته‌های چندهزارتایی با COPY می‌نویسد.

- **Migration:** همهٔ تغییرات اسکیما فقط با Alembic.

**۸. آرتیفکت‌ها و کانفیگ**

**چیدمان آرتیفکت‌ها**

```
artifacts/<run_id>/<stage>/<candidate_id>/
    summary.json # pydantic artifact, schema_version
    trades.parquet # only for candidates that passed
    equity.parquet
    surface.parquet # stage 3/4 parameter surface
    report.html # stage report (jinja2 + plotly)
```

**نمونهٔ کانفیگ**

```
# configs/pipeline/mvp_daily.yaml
universe: configs/universe.yaml
symbols: [SPX500, US30]
timeframes: [1D]
stages: [s01_edge, s02_screen, s03_entry]
gates: configs/gates/default.yaml
intrabar_mode: pessimistic
seed: 42
 
# configs/gates/default.yaml
s01_edge:
  - {metric: probe_percentile, op: ">=", threshold: 90}
  - {metric: ess, op: ">=", threshold: 50}
overrides:
  timeframe: {1H: {s01_edge: [{metric: min_trades, op: ">=", threshold: 100}]}}
```

> قاعدهٔ طلایی کانفیگ
> هیچ آستانه، وزن یا عدد تصمیمی در کد نوشته نمی‌شود. مقدار پیش‌فرض در مدل Pydantic کانفیگ تعریف و در سند مشخصات مستند می‌شود.

**۹. مراحل و قراردادهای ورودی و خروجی**

| **ماژول**         | **ورودی**              | **آرتیفکت خروجی**                        | **اولویت** |
|------------------------------------------|-----------------------------------------------|-----------------------------------------------------------------|-----------------------------------|
| **s00_data**      | فایل‌های منبع           | اسنپ‌شات، کاتالوگ، گزارش کیفیت، split     | MVP        |
| **s01_edge**      | نماد × تایم‌فریم        | EdgeProfile (ESS، مؤلفه‌ها، پروب‌ها)       | MVP        |
| **s01s_seasonal** | نماد × تایم‌فریم        | SeasonalCalendar + کاندیدها              | P1         |
| **s02_screen**    | EdgeProfile عبوری      | ScreenResult (امتیاز خانواده، گرید درشت) | MVP        |
| **s03_entry**     | کاندیدهای s02          | EntryOptResult (سطح، پلاتو، SPP)         | MVP        |
| **s04_exit**      | کاندیدهای s03          | ExitOptResult                            | P1         |
| **s05_filter**    | کاندیدهای s04 / سیزنال | DiagnosticReport + FilterResult          | P1         |
| **s06_robust**    | کاندیدهای s05          | RobustnessReport + نتیجهٔ هولدآوت         | P1         |
| **s07_stats**     | کاندیدهای s06          | StatsReport (DSR با N مؤثر، PBO، SPA)    | P1         |
| **s08_package**   | عبوری‌ها و مرزی‌ها       | پکیج گزارش (JSON + PROMPT + SPEC)        | P1         |
| **s09_review**    | پکیج + docx            | Decision                                 | P1         |
| **s10 تا s12**    | تأییدشده‌ها             | پورتفو، سایزینگ، پایش                    | P2         |

**۱۰. اجرای موازی و ارکستراسیون**

- **سطح ۱ (درون پردازش):** simulate_grid با prange روی ستون‌های ماتریس سیگنال؛ سیگنال‌های همهٔ ترکیب‌ها برداری ساخته می‌شوند.

- **سطح ۲ (بین پردازش‌ها):** Executor بر پایهٔ ProcessPoolExecutor، واحد کار = (نماد، تایم‌فریم، مرحله). تعداد thread هر پردازش Numba طوری تنظیم می‌شود که جمع از تعداد هسته بیشتر نشود.

- **ادامه از توقف:** ارکستراتور وضعیت هر (کاندید، مرحله) را از رجیستری می‌خواند و فقط کارهای ناتمام را اجرا می‌کند.

- **تعویض‌پذیری:** Executor یک Protocol است؛ جایگزینی با Ray بدون تغییر مراحل.

**فرمان‌های CLI**

```
sfac data ingest --source dukascopy --path ... --symbol US30
sfac data quality --symbol US30
sfac parity --strategy spx500_mr_ref --tv-trades trades.csv
sfac run --config configs/pipeline/mvp_daily.yaml
sfac run --resume <run_id>
sfac reproduce --trial <trial_id>
sfac report stage --run <run_id> --stage s03_entry
sfac report package --candidate <id> # stage 8 bundle
sfac report verify --report r.docx --bundle evidence.json
sfac selftest --kind random_walk --n 200
```

**۱۱. مرحلهٔ ۸: پکیج گزارش و verify**

- **evidence.json:** یک فایل با schema_version؛ خلاصه‌ها و جدول‌های تجمیعی، بدون فهرست کامل تریدها. هر مقدار عددی کلید مسیر یکتا دارد (مثلاً metrics.annual.avg_profit).

- **PROMPT.md:** قواعد نگارش؛ الزام ذکر کلید منبع هر عدد به‌صورت پاورقی یا پرانتز کوچک.

- **REPORT_SPEC.md:** بخش‌ها و مشخصات ظاهری ورد (راست‌به‌چپ، وزیرمتن، رنگ‌ها، جدول‌ها، نمودارها از داده‌های chart_data).

- **verify:** استخراج متن docx، یافتن همهٔ اعداد (با تبدیل ارقام فارسی و ٫)، تطبیق با مقادیر JSON با تلورانس گرد کردن، و گزارش اعداد بی‌منبع یا ناهمخوان؛ سپس ثبت در جدول reports.

- نسخهٔ پرامپت و قالب در ریپو نسخه‌بندی می‌شوند؛ پکیج نسخه‌ها را در خود دارد.

**۱۲. راهبرد تست**

| **نوع**       | **پوشه**       | **هدف**                                        | **در CI**      |
|--------------------------------------|---------------------------------------|-----------------------------------------------------------------------|---------------------------------------|
| **واحد**      | tests/unit     | هر فیچر طبق معیار پذیرش فیچرلیست               | همیشه          |
| **ویژگی‌محور** | tests/property | ثابت‌های موتور و متریک‌ها با Hypothesis          | همیشه          |
| **نشت**       | tests/leakage  | تست برش داده برای همهٔ اندیکاتورها و سیگنال‌ها   | همیشه — اجباری |
| **Parity**    | tests/parity   | مقایسه با خروجی TradingView (دو استراتژی مرجع) | همیشه — اجباری |
| **اوراکل**    | tests/oracle   | مقایسه با vectorbt روی استراتژی‌های ساده        | همیشه          |
| **خودآزمایی** | tests/selftest | قدم‌زدن تصادفی و اج کاشته‌شده                    | شبانه (کند)    |

- نام هر تست با شناسهٔ فیچر شروع می‌شود (مثلاً test_F_0_3_1_next_bar_open_fill) تا پوشش فیچرلیست قابل گزارش باشد.

- fixtureها: سری‌های ساختگی کوچک با پاسخ دستی معلوم، و نمونهٔ کوچک دادهٔ واقعی هر منبع.

- mypy با حالت strict برای core، data، registry و gates؛ برای kernelهای Numba حالت ملایم‌تر.

**۱۳. ترتیب پیاده‌سازی MVP (تسک‌های Claude Code)**

هر تسک یک یا چند فیچر را پوشش می‌دهد، یک Pull Request است و با عبور از معیارهای پذیرش همان فیچرها بسته می‌شود.

| **تسک** | **فیچرها**                         | **خروجی**                                                               | **پیش‌نیاز** |
|--------------------------------|-----------------------------------------------------------|------------------------------------------------------------------------------------------------|------------------------------------|
| **T01** | F-X.9، F-X.10                      | ریپو، uv، ruff، mypy، pytest، CI، docker-compose، CLAUDE.md، اسکلت sfac | —           |
| **T02** | F-0.1.1، F-0.1.8                   | اسکیما، متادیتا، store و کاتالوگ Parquet                                | T01         |
| **T03** | F-0.7.1 تا F-0.7.4                 | رجیستری Postgres، Alembic، BatchWriter، reproduce (اسکلت)               | T01         |
| **T04** | F-0.1.3، F-0.1.2، F-0.1.5          | آداپتورها (پس از دریافت نمونه‌فایل‌ها)                                    | T02         |
| **T05** | F-0.1.6، F-0.1.7، F-0.6.1          | کیفیت، بازنمونه‌گیری، SplitManager                                       | T02، T03    |
| **T06** | F-0.2.1، F-0.2.3، F-0.2.4          | پروفایل هزینه، سواپ، استرس                                              | T02         |
| **T07** | F-0.4.1 تا F-0.4.3                 | رابط اجزا، اندیکاتورها + تست مرجع                                       | T01         |
| **T08** | F-0.3.1، F-0.3.2، F-0.3.4، F-0.3.9 | هستهٔ موتور، خروج‌های پایه، حالت‌های درون‌کندلی، تست نشت و ویژگی‌محور        | T06، T07    |
| **T09** | F-0.5.1، F-0.5.2، F-0.5.4          | متریک‌ها                                                                 | T08         |
| **T10** | F-0.3.7، F-0.8.1، F-0.8.2، F-0.9.1 | executor، موتور گیت، کانفیگ، یونیورس                                    | T03، T08    |
| **T11** | F-0.3.8، F-X.7                     | تست Parity با TradingView و رگرسیون — دروازهٔ ورود به مرحلهٔ ۱            | T04، T09    |
| **T12** | F-1.1 تا F-1.9                     | مرحلهٔ ۱                                                                 | T11         |
| **T13** | F-2.1 تا F-2.7                     | مرحلهٔ ۲                                                                 | T12         |
| **T14** | F-3.1، F-3.3 تا F-3.7              | مرحلهٔ ۳                                                                 | T13         |
| **T15** | F-X.1 تا F-X.5                     | ارکستراتور، CLI کامل، گزارش HTML، خودآزمایی تصادفی                      | T14         |

> نکتهٔ زمان‌بندی
> T02، T03، T06 و T07 به هم وابسته نیستند و می‌توانند هم‌زمان توسط اعضای مختلف تیم جلو بروند. T04 تنها تسکی است که منتظر نمونه‌فایل‌های داده است.

**۱۴. دفتر تصمیمات فنی (ADR)**

| **شماره**   | **تصمیم**                                                                                 |
|------------------------------------|------------------------------------------------------------------------------------------------------------------|
| **ADR-001** | موتور اختصاصی Numba؛ vectorbt فقط اوراکل تست                                              |
| **ADR-002** | دادهٔ بازار در Parquet + DuckDB با اسنپ‌شات تغییرناپذیر                                     |
| **ADR-003** | Polars در لایهٔ داده، pandas در لبه‌ها، NumPy در موتور                                      |
| **ADR-004** | رجیستری PostgreSQL در Docker؛ SQLAlchemy Core + psycopg 3 + Alembic؛ نوشتن دسته‌ای با COPY |
| **ADR-005** | اجرای موازی دوسطحی تک‌ماشین پشت رابط Executor                                              |
| **ADR-006** | گرید کامل؛ Sobol بالای ۲۰۰۰ ترکیب؛ بدون جستجوی بیزی                                       |
| **ADR-007** | Typer + YAML/Pydantic؛ ارکستراسیون زمان‌بندی‌شده به مرحلهٔ ۱۲ موکول                          |
| **ADR-008** | گزارش HTML با Jinja2 + Plotly                                                             |
| **ADR-009** | مرحلهٔ ۸ بدون API: پکیج JSON + پرامپت، ورد توسط Claude چت، sfac report verify              |
| **ADR-010** | uv، پایتون ۳٫۱۲، pytest + Hypothesis + ruff + mypy، GitHub Actions                        |
| **ADR-011** | نام‌ها: Strategy Factory / strategy_factory / sfac                                         |

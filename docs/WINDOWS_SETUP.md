# Windows Walkthrough: From Nothing to Downloaded Data

Complete step-by-step for Windows with IB Gateway. Assumes no prior setup.

**PowerShell is the terminal window you type commands into. Git is a program you run
inside it.** They are not alternatives. You will open PowerShell, and type `git` commands
into it. If you would rather not install Git at all, Step 2 has a no-Git alternative.

Total time: about 20 minutes of setup, then a 5-minute test, then a download of roughly 2
to 2.5 hours that runs unattended.

---

## Step 1: Install Python and Git

### Python

1. Go to <https://www.python.org/downloads/> and download the Windows installer.
2. Run it. **On the first screen, tick "Add python.exe to PATH".** This is easy to miss
   and everything fails later without it.
3. Click "Install Now".

### Git

1. Go to <https://git-scm.com/download/win> and download the installer.
2. Run it. Accept every default.

### Open PowerShell

Press the **Windows key**, type `powershell`, press **Enter**. A blue window opens. This is
where everything below gets typed.

### Verify both installed

Type these one at a time, pressing Enter after each:

```powershell
py --version
git --version
```

You should see version numbers, for example `Python 3.12.4` and `git version 2.45.1`.

> **If `py` opens the Microsoft Store instead of printing a version:** Windows has a
> placeholder alias in the way. Go to Settings → Apps → Advanced app settings → App
> execution aliases, and switch **off** the entries named `python.exe` and `python3.exe`.
> Then close PowerShell, reopen it, and try again.

> **If `git` is not recognized:** close PowerShell and open it again. The installer adds
> Git to your PATH, but only new windows pick that up.

---

## Step 2: Get the code

Pick a folder to work in, then download the project into it:

```powershell
cd $HOME\Documents
git clone https://github.com/adam005141/new-claude-bot.git
cd new-claude-bot
git checkout claude/mes-mnq-intraday-system-byzh9s
```

That creates `C:\Users\<you>\Documents\new-claude-bot` with everything in it.

GitHub may ask you to sign in the first time. Follow the browser prompt.

### No-Git alternative

If you would rather skip Git entirely:

1. Open <https://github.com/adam005141/new-claude-bot> in a browser.
2. Click the **branch dropdown** (it says `main`) and pick
   `claude/mes-mnq-intraday-system-byzh9s`.
3. Click the green **Code** button, then **Download ZIP**.
4. Extract the ZIP into `Documents`.
5. In PowerShell: `cd $HOME\Documents\new-claude-bot-claude-mes-mnq-intraday-system-byzh9s`

The tradeoff is that you cannot pull updates later with `git pull`; you would re-download
the ZIP each time.

---

## Step 3: Install the Python packages

Still in the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> **If you get "running scripts is disabled on this system":** Windows blocks scripts by
> default. Run this, then retry the activate line above. It applies only to the current
> window and changes nothing permanently:
>
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

Your prompt now starts with `(.venv)`. That means the isolated environment is active and
packages install there instead of polluting your system Python.

```powershell
pip install -r requirements.txt
```

This installs `ib_async`, `pandas`, `pyarrow`, and `pytest`. Takes a minute or two.

> **Every time you open a new PowerShell window** to work on this, you must `cd` to the
> project folder and run `.\.venv\Scripts\Activate.ps1` again. If you forget, you get
> `ModuleNotFoundError: No module named 'ib_async'`.

---

## Step 4: Check the code works before involving IB at all

```powershell
py -m pytest tests\ -q
```

Expected: `22 passed`. This needs no internet and no Gateway. If this fails, stop and send
me the output; nothing after this point will work.

Now confirm the download planner runs:

```powershell
py tools\ibkr_download.py --symbols MES --bar-size "1 hour" --years 2 --dry-run
```

Expected: something like `planned 30 requests` and an estimated runtime. Still no
connection to IB. If you see the plan, the code is fine and the only remaining variable is
Gateway.

---

## Step 5: Configure IB Gateway

Open IB Gateway and log in.

### Turn on the API

**Configure → Settings → API → Settings**

- Tick **Enable ActiveX and Socket Clients**
- Tick **Read-Only API**. This project only reads data, and read-only makes it
  structurally impossible for a bug to place an order.
- Note the **Socket port** number. Defaults:

  | | Paper | Live |
  |---|---|---|
  | IB Gateway | `4002` | `4001` |
  | TWS | `7497` | `7496` |

- Under **Trusted IPs**, make sure `127.0.0.1` is listed. Add it if not.
- Click **OK** / **Apply**.

### Stop the daily auto-logout

**Configure → Lock and Exit → Auto Logoff / Never**

Gateway logs itself out once a day by default. A multi-hour download will die partway if it
happens mid-run.

### Market data subscription

Historical CME futures data requires a **CME real-time** subscription on the account. Check
in IBKR Client Portal under **Settings → Market Data Subscriptions**.

**This is the single most common reason people think the download is broken.** Without the
subscription, requests return *empty results rather than an error*, which looks exactly
like "no data exists."

**Leave Gateway running and logged in** for everything below.

---

## Step 6: Smoke test, about 5 minutes

Do not skip this. It is cheap, and it proves the connection, the subscription, and the
contract resolution all work before you commit hours.

```powershell
py tools\ibkr_download.py --symbols MES --bar-size "1 hour" --years 2 --port 4002
```

Use whichever port matches your setup from the table in Step 5.

You should see lines scrolling like:

```
14:02:11 INFO    connecting to 127.0.0.1:4002 (clientId=17)
14:02:12 INFO    connected: server version 176
14:02:13 INFO    MES: found 8 dated contracts (202512 to 202709)
14:02:14 INFO    planned 14 requests (0 already cached, 14 to fetch)
14:02:14 INFO    estimated runtime: 2m 34s at 11.0s pacing
14:02:25 INFO    [1/14] MES 202512 TRADES end=2025-12-19 -> 477 bars
```

The important part is **`-> 477 bars`** and not `-> 0 bars`. Bars means real data.

Around 8 contracts is correct, and only about 4 of them carry usable history. The rest are
current or future contracts with nothing to fetch yet, and the planner skips them. The
offline dry-run predicts more contracts than this because it synthesizes a full quarterly
cycle; IBKR itself is the authority.

Then check the quality:

```powershell
py tools\validate_data.py data\
```

You want `PASS` lines. `QUARANTINE` means something is wrong with that file.

**Send me this output before going further.** I will tell you whether it is healthy.

---

## Step 7: The real download, about 2 to 2.5 hours

Only after Step 6 passed:

```powershell
py tools\ibkr_download.py --symbols MES MNQ --bar-size "1 min" --years 2
```

- **Expect about 2 to 2.5 hours**, roughly 700 requests. Fewer contracts exist than the
  offline dry-run predicts, because the dry-run synthesizes a full quarterly cycle while
  IBKR only serves about 8 months of expired contracts.
- **Leave the PowerShell window open** and leave Gateway logged in.
- **It is safe to interrupt.** Press `Ctrl+C`, or let the machine sleep, or lose the
  connection. Every request is cached to its own file. Rerun the exact same command and it
  skips everything it already has.
- The 11-second gap between requests is not padding. IBKR permits 60 historical requests
  per 10 minutes and throttles you for exceeding it.

Optionally add bid/ask data for more honest spread modeling, at three times the runtime:

```powershell
py tools\ibkr_download.py --symbols MES MNQ --what TRADES BID ASK --years 2
```

When it finishes:

```powershell
py tools\validate_data.py data\ --json data\validation_report.json
```

---

## Step 8: What you should end up with

```
new-claude-bot\
└── data\
    ├── MES\
    │   ├── MES_202409_1min_TRADES.parquet
    │   ├── MES_202409_1min_TRADES.meta.json
    │   ├── MES_202412_1min_TRADES.parquet
    │   └── ... (about 8 contracts)
    ├── MNQ\
    │   └── ...
    └── _cache\        (per-request chunks; safe to delete once merged)
```

Roughly 4 quarterly contracts per symbol carrying real data, each covering its ~100-day
front-month window, at 1-minute resolution, unadjusted. That is about 11.5 months of
continuous coverage per instrument, which is what the backtest needs.

Contracts dated in the future are listed by IBKR but correctly skipped by the planner,
since they have no history yet.

Send me the output of `validate_data.py` and I will start building the engine.

---

## Troubleshooting

| What you see | What it means |
|---|---|
| `py: command not found` | Python not installed, or "Add to PATH" was not ticked in Step 1 |
| `git: command not found` | Close and reopen PowerShell; if still failing, reinstall Git |
| `running scripts is disabled` | Run the `Set-ExecutionPolicy` line in Step 3 |
| `No module named 'ib_async'` | The venv is not active. Rerun `.\.venv\Scripts\Activate.ps1` |
| `ConnectionRefusedError` | Gateway not running, wrong `--port`, or API not enabled in Step 5 |
| Connects fine, every file `-> 0 bars` | Missing CME market data subscription |
| `clientId already in use` | TWS or another script is connected. Add `--client-id 42` |
| `pacing violation` in the log | Add `--pacing 15` |
| Only ~8 contracts found, oldest ~8 months back | Expected and MEASURED. IBKR's contract discovery cuts off well before the documented 2-year retention. About 11.5 months of continuous coverage is normal |
| Download died overnight | Rerun the same command; it resumes from cache |

> **Note on the code you are running:** the parts that talk to IB Gateway have never been
> executed against a real gateway, because the environment they were written in has no
> Gateway and no network access. The planning, merging, and validation logic is covered by
> 22 tests that pass. Step 6 exists precisely so the first real contact with IB is a
> 5-minute test rather than a multi-hour one.

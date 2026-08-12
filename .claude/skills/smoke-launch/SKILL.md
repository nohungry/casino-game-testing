---
name: smoke-launch
description: 跨品牌「遊戲載入冒煙檢查」—— 逐款點開，確認能不能載入到 start/splash 畫面，產一份標註哪些能載入的 md。不下注、不驗餘額，故不產生任何 PASS。適用於新測試環境盤點「哪些品牌/遊戲已開通」。當使用者說「確認遊戲能不能開」「載入測試」「盤點哪些遊戲可以玩」時用。站點隱含於當前頁面；Skill 不跨站、不登入。
---

# smoke-launch

跨品牌的**載入冒煙檢查**：把某分類（通常是電子）底下所有品牌的所有遊戲逐款點開，判定能不能載入到 **start / splash 畫面**，最後產一份 md 標註結果。典型用途是新測試環境上線前盤點「哪些品牌/遊戲已開通」。

## 🔴 這個 Skill 為什麼獨立於 test-game-brand

`test-game-brand run` 的核心是**驗餘額才能 PASS**，它的三道閘門（brand yaml 存在、`_calibration_gaps` 為空、canary 真下 1 注）就是假 PASS 的防線。本任務不下注，若在那三道閘門上加 flag 繞過，等於在防線上開後門。

**所以：本 Skill 的產出中絕不出現 `PASS`。** 成功狀態叫 `LAUNCH_OK`，它只代表**前端資產載入成功**。
🔴 **「能開起來」≠「能玩」≠「能下注」≠「能結算入後台」** —— 已知有一種樣態是「動畫照跑、主畫面可操作，但餘額永遠凍結、下注永不成立」，**本方法完全偵測不到**。這句話必須出現在每一份產出的報告裡。

## 指令格式
```
/smoke-launch [--category slots|live|fishing] [--brands a,b] [--limit-per-brand N]
              [--resume <umbrella_dir>] [--html]
```
沒給 `--brands` 就是「該分類全部品牌」。`--limit-per-brand` 用於抽樣。
`--category` 沒給就從當前 `location.pathname` 推斷；**推不出來就停下問人，不要預設 slots**。

🔴 **一個 umbrella 只放一個分類。** 三種分類的**分母單位不同**（電子＝1 款遊戲、真人＝1 張桌台、捕魚＝1 個場次/款）、**就緒判準不同**（電子看網路靜默＋畫面靜止；真人/捕魚看畫面**在動**）、**逾時不同**（90/150/120s）。混在一份報告裡算出來的 OK 率沒有對應的母體，只能誤導。要合看就人工並列兩份報告。

## 起手（所有 mode 共用）
瀏覽器由 AI 啟動（`browser_navigate` 到 `about:blank`）；**視窗大小/所在螢幕、導航到站點、登入，一律由使用者自己做**。AI 從當前頁接手，同站內切分類/品牌可代勞（先宣告）。**跨站導航與登入永不代勞。**

---

## Phase 0 — 站點與登入驗證（每次開跑都要，不可略）

`browser_tabs list` → 讀 `location.href` 與 `window.innerWidth/innerHeight` → **實際驗登入態**（頁面還有「登入/註冊」鈕＝未登入；找會員/錢包元素佐證）。

🔴 **使用者口頭說「已經登入了」不能取代這一步。** token 可能已過期，後果是整批遊戲被誤判成「未開通」，而且事後無法回溯修正。

不在目標站 / 未登入 / 多站分頁分不清 → **停下請使用者處理**。

產 `umbrella_dir` = `reports/smoke-launch-<category>-<YYYYMMDD-HHMM>/`（時間戳用 Bash `date +%Y%m%d-%H%M`），內含 `_scratch/`、`_scripts/`、`brands/`。
寫 `smoke-meta.json`：站點 host、`category_key`（`slots|live|fishing`，機器讀）與 `category`（人讀）、`ready_profile`、viewport、`login_verified` 與佐證、起始時間、參數、`method_version`、`sibling_runs`（其他分類的 umbrella 絕對路徑，方便互相參照）。

## Phase 1 — 盤點品牌

抓當前分類所有品牌 tile：顯示名、平台 id（若 DOM/URL 帶得到）、lobby URL、tile selector、進入方式。

🔴 **不要寫死任何 URL 形狀**（例如 `?somePlatformId=`）。先點一個 tile 驗當前站是不是這個形狀；不是就記「點 tile」模式與 selector。其他站的觀察只當起手假設。

### Phase 1.5 —（可選但強烈建議）用 API 預篩上游可用性

品牌數多時（>15），逐品牌開 UI 冒煙很貴（一站 40 分鐘）。可以先直接呼叫 launch API 篩掉根本開不起來的品牌，只對有回 `gameUrl` 的走 UI。2026-08-12 實測用此法把 27 個平台的篩選從 40 分鐘壓到 3 分鐘。

🔴 **三個前提缺一不可，我在同一天把三個都踩過一次：**

1. **端點要對** —— UI 走的可能是 `launchGameBySeamless` 而不是 `Game/launch`，**兩者結果不同**（實測某站同一品牌在兩支端點結果相反）。先從 network 面板看 UI 實際打哪支。
2. **間隔 ≥6 秒** —— 平台有 5 秒節流，回 `400 InvalidOperate`「您的操作過於頻繁」。我用 0.5 秒掃，25 個失敗裡有 20 個是自己造成的。
3. 🔴 **掃完要收錢** —— **自動轉移 ON 時，呼叫 launch API 會把主錢包整筆搬進供應商錢包，即使根本沒進遊戲**。實測掃完主錢包被歸零，害下一批看到「遊戲內餘額 0」而我一度誤判成平台缺陷。**掃站前後都要讀主錢包餘額**，掃完用「一鍵轉回／全部轉回」收回。

另外：**自組 API 請求前，先從 network 面板抄該站真實送出的 header**（`authorization`／`companycode`／`lang`／**`domain`**）。`domain` 常與頁面網址不同（實測過某站的 `domain` 比頁面網址多了一段後綴），填錯**不會報錯，而是安靜回一組看起來合理但全錯的資料**。

⚠️ **API 只能用來「排除」，不能用來「確認」** —— API 回得出 gameUrl 不代表 UI 開得起來（實測有品牌 API 通但 UI 轉點失敗）。可用的品牌仍要走 UI 實測。

產 `brands.json`：`[{bslug, category, display_name, platform_id, lobby_url, tile_selector, enter_mode, listed_count, phase:"pending", brand_verdict:null}]`。

🔴 **`bslug` 一律帶分類前綴**（`fish-<品牌>`、`live-<品牌>`；電子沿用無前綴以相容既有產物）。原因：同一供應商常同時供多個分類、**platform_id 完全相同**，不加前綴的話兩個分類的同名品牌會寫進同一個 `brands/<bslug>/games.jsonl`，接著 `report_common.dedupe_retries()`（只用 `idx` 當鍵）會把「A 分類第 3 款」和「B 分類第 3 款」當成重試補行、**靜默丟棄前一筆**，而報告只會顯示「收尾重試取代的舊紀錄 N 行」—— 看起來完全正常。這是唯一一種**壞了不會有任何訊號**的失敗。
`category` 另外存成獨立欄位（給報告分段用），**不要靠解析 bslug 字串**。`bslug` 由 AI 產（小寫、去空白），**只存在 reports/**。

**回報品牌名單與數量給使用者。**

## Phase 2 — 每品牌 launch-only probe

派 `game-launch-scout`（subagent_type: `game-launch-scout`），給 `brand`/`lobby_url`/`brand_dir` 絕對路徑/`umbrella_dir`。它用前 1–2 款探出清單抓法、卡片點法、啟動方式、就緒訊號、退出步驟 → `brand-probe.json` + `full-game-list.json`（**含全部款**，作為跨 resume 恆定的分母）。

單品牌 probe 硬上限 4 分鐘，最多重試 1 次；失敗記進 `brands.json` 的 `brand_verdict`（`BRAND_UNAVAILABLE` / `PROBE_FAILED`），**不為沒跑過的款產生假行**（會污染分母）。

**🛑 停損點：** 全部 probe 完後，回報「N 品牌、K 個可測、可測遊戲總數 T、預估耗時」給使用者，**等使用者選定範圍才進 Phase 3**。品牌數 > 30 時先 probe 前 5 個取平均給區間估計，問使用者要不要繼續。

## Phase 3 — 逐款開啟

派 `game-launch-runner`，**序列執行**（單一瀏覽器分頁不能並行搶操作）。批量依型態：**slots 12 / fishing 8 / live 3 款一批**（真人單桌可能 2–3 分鐘，一批就是一個品牌）。判定階梯與 status 詞彙見 agent 檔，編排層不要另訂一套。

進度回報：**每批一行**（約 5 分鐘一次），每品牌結束一段摘要。不做逐款回報（會淹沒對話）。

**早退規則**：某品牌前 **min(10, max(3, ceil(清單數 × 0.3)))** 款全部 `LAUNCH_BLOCKED` 且**警告文案相同** → 高信心判定整品牌未開通，回報並提議跳過剩餘款。（寫成比例式是因為真人品牌的桌台數常 < 10，固定「前 10 款」永遠不會觸發。）跳過的款標 `SKIPPED` 並在報告註明原因。

**停損（任一命中就停下問人）**：
- 連續 3 款 `STUCK_RECOVERED`（疑瀏覽器/session 掛了）
- **每個品牌邊界重驗登入態**；失效 → 立刻停，之後所有資料不可信
- 累計耗時超出使用者同意的預算

## Phase 3.5 — 每品牌收尾重試一輪

只重試 `LAUNCH_TIMEOUT` / `LAUNCH_NO_RESPONSE` / `STUCK_RECOVERED`。
`LAUNCH_BLOCKED` **不重試**（文案明確＝未開通），除非文案本身像暫時性（「系統繁忙」「請稍後再試」）。
重試成功 → **append 一行新紀錄**（`dedupe_retries()` 會取最後一行），note 記「重試後成功」。

## Phase 4 — 彙整

1. 每個 `brand_dir` 跑 `uv run .claude/skills/test-game-brand/gen_run_artifacts.py <brand_dir>`（零修改複用，產內部中繼的 run-summary/CSV）。
   ⚠️ 它會顯示「PASS：0 款」—— **這是正確的**，忠實反映「本輪沒驗餘額所以沒有 PASS」，不是 bug。
2. 跑 `uv run .claude/skills/smoke-launch/gen_smoke_report.py <umbrella_dir> [--html]` 產 `smoke-report.md`。
3. 回報**絕對路徑**，並明確宣告不自動複製到專案外。

🔴 **一律不跑 `gen_qa_report.py`**：它的 `abnormal = total - npass`、指標卡標籤寫死「異常款 / 假 PASS」、狀態色碼只認 `PASS`/`LOAD_FAIL`/`FAIL`/`OOPS_UNRECOVERED`，整批冒煙會被呈現成 0% 紅燈，而**標籤寫死在模板與程式碼裡、narrative JSON 覆寫不了**。要 HTML 就用本 skill 的 `--html`。

---

## 產物結構

```
reports/smoke-launch-<YYYYMMDD-HHMM>/        ← gitignored
├── smoke-meta.json      # 站點 host / viewport / login_verified / 起訖 / 參數 / method_version
├── brands.json          # 品牌盤點 + 每品牌 phase 與 brand_verdict
├── progress.jsonl       # checkpoint 快速索引 {"ts","bslug","idx","status"}
├── smoke-report.md      # ★ 最終交付
├── _scratch/glance.png  # glance 暫存（固定覆寫，唯一一個檔）
├── _scripts/            # 現場注入的判定 JS
└── brands/<bslug>/      # ★ 這一層 = 完整的單一品牌 report_dir
    ├── run-meta.json · full-game-list.json · games.jsonl
    ├── brand-probe.json · games.csv · run-summary.md
    └── screenshots/     # 只有非 LAUNCH_OK 款
```

**為什麼每品牌一個子目錄**：把所有品牌混進一個 `games.jsonl` 會讓 `idx` 撞號，`dedupe_retries()` 會把不同品牌的同 idx 誤當重試去重 —— 這會真的壞資料。切開後 `<brand_dir>` 完全符合既有工具對 report_dir 的假設，聚合器只需 glob。

## Checkpoint / Resume

canonical 真源是每品牌的 `games.jsonl`（append-only）；`progress.jsonl` 只是快速索引。
`--resume <umbrella_dir>`：讀 `brands.json` 找 `phase != done` 的品牌 → 讀該品牌 `games.jsonl` 已完成的 idx → 從 `full-game-list.json` 扣掉 → 續跑。已有 `brand-probe.json` 就不重 probe，但**一定要重驗登入態**。
`brands.json` 每品牌 `phase`：`pending → probing → running → done | unavailable`，每次轉換就落盤。

## 鐵則（沿用 CLAUDE.md，不因新任務鬆動）
- **不跨站導航、不代填帳密**；同站內切分類/品牌可代勞（先宣告）。
- **絕不 `browser_resize`**（hook 硬擋）；viewport 只讀+比對。
- **截圖 `filename` 一律完整絕對路徑**（裸檔名 hook 硬擋）；所有產物歸位 `report_dir/`。
- **卡住 60s 換新分頁**從 lobby 重啟，標 `STUCK_RECOVERED`，不在原頁 debug。
- **不編造資料**：探不到就記 `gaps`、沒量過的欄位留空，不要填 0 冒充量過。

## 型態別要多留意的（真人／捕魚）
- 🔴 **真人只驗到「影像出來」不等於「這張桌可以玩」**：串流品質、荷官是否真在發牌（可能是循環錄影）、桌台是否接受下注、限紅是否套到本帳號 —— 全部未驗。
- 🔴 **真人的桌台可入座性一律未驗證**（安全附則禁止入座）。「需入座才出影像」的桌記 `main_check="seat_required"`，那是**未量測**，既不代表壞也不代表可用。
- 🔴 **真人桌台數的分母常是未知的**（二層大廳在跨域 iframe 內列舉不到）→ `full-game-list.json` 標 `unenumerable`，報告印「—」。
- 🔴 **捕魚的獨立錢包未驗證**：常有獨立遊戲錢包需先轉帳。不讀餘額就**分不出**「錢包沒錢／錢包沒開通／品牌沒開通」，三者可能表現成同一個彈窗。
- **真人桌台清單是動態的**（會即時開關），「捲到底數量不變」的 lazy-load 檢查不成立，盤到的數字是當下快照。

## 這個方法測不到什麼（必須原文進報告）
1. 🔴 **「動畫跑但餘額凍結」會被記成 `LAUNCH_OK`** —— 前端載入完整但後端未部署，本方法完全偵測不到。
2. 無法區分「未開通」與「當下抖動」（單次量測，重試一輪只是緩解）。
3. 跨域 iframe 內只能像素判讀，警告若畫在 canvas 或用計畫外文案會漏判 → 誤標成 `LAUNCH_OK`。
4. `splash` / `main` 分界模糊，`reached` 是判讀不是事實。
5. 登入態或遊戲錢包狀態污染會讓大量款變 BLOCKED，外觀與「未開通」難以區分。
6. 不代表生產環境；跨數小時甚至跨天，不是同一時刻的快照。
7. 統計不獨立：同供應商同引擎的款多半共命運，OK 率不能當「隨機抽一款的可用機率」。

**不能下的結論**：「X 款通過測試」「品牌 Y 可以上線」「OK 率＝可用率」。
**可以下的結論只有**：「在 <時間> 的 <站點>，這 X 款前端載入到了 start/splash；這 Y 款跳出了『<原文>』」。

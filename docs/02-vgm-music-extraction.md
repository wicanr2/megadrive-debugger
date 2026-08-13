# Mega Drive 音樂擷取：從 ROM 產生逐首、可重現的 VGM／WAV

> 觸發：要把 Mega Drive／Genesis 遊戲的配樂變成可重播的音檔（remake 配樂、推廣片、
> 音源比較）；「BlastEm 錄不出 VGM」；「怎麼逐首觸發而不是整段錄」；
> 「headless 容器裡怎麼錄 VGM」。
>
> 來源：一款 1991 年 Mega Drive RPG 的實作 + vgmrips wiki，2026-08 實測。
> 標「本機實測」的是在這台機器上驗過的；其餘標來源。

## 1. 為什麼不能只靠「打開模擬器錄一段」

三個環節缺一不可，而**難的是第一個**：

| 環節 | 問題 |
|---|---|
| **觸發** | 要逐首、可重現地讓某一首播出來。玩到那個場景不可重現，而且像「全滅」「隊員死亡」這種曲子很難刻意觸發 |
| **記錄** | 模擬器要能寫 VGM，而且能在無 X 的容器裡自動開關 |
| **轉檔** | VGM 是暫存器寫入的時間序列，不是音訊，要另外合成 |

「錄一段長的再切」看起來省事，實際上切點、循環點與淡出都得手工判斷，
而且**下一次重跑不會得到同一份輸出** —— 那就不是可重現的擷取。

## 2. 觸發：第一性原理

Mega Drive 的音樂幾乎都是 **68000 指揮、Z80 演奏**：

1. 68k 搶下 Z80 匯流排（寫 `$100` 到 `$A11100`），
2. 把驅動與／或曲目資料搬進 Z80 RAM（`$A00000`–`$A01FFF` 這個窗口），
3. 寫一個**命令位元組**到 Z80 RAM 的固定 offset，
4. 放掉匯流排（寫 `0` 到 `$A11100`），Z80 自己跑。

**所以觸發點一定是「Z80 RAM 的某個 offset ＋ 一個值」。**
找到它就能用模擬器的除錯器直接寫記憶體觸發，不必玩到那個場景。

### 怎麼找那個 offset（順序很重要）

```
1. 掃直接寫入： move.b #imm,($A0xxxx).l
2. 掃間接寫入： movea.l #$A00000,aN  之後的  move.b dM,$XX(aN)
3. 找「寫的是變數不是常數」的那一筆 —— 那是曲目編號
```

**[HARD] 只做第 1 步會得到「幾乎沒有寫入」的假象。** MM2 那片 786 KB 的 ROM，
整份反組譯裡直接寫 `($A0xxxx).l` 的指令**只有兩筆**，而真正的命令介面全部走
`a0 = $A00000` 之後的 `$A(a0)`／`$B(a0)`。漏掉的長相與「這個遊戲沒有音樂驅動」
一模一樣。

典型結果會長這樣（MM2 本機實測）：

	$A0000A   參數／曲目編號（$FF = 停止）
	$A0000B   命令（$0D = 播放剛上傳的資料、$12 = 另一種播放）
	$A01600   曲目資料上傳目的地（每首 0x400 bytes）

### 觸發手段:寫執行時記憶體,不要改 ROM

**改 ROM 是陷阱** —— 商業卡帶可能有開機完整性檢查(實測 EA 1991 那片:改動
任何一個位元組、尾端 padding 除外,就開不了機,畫面全黑而 VGM 照樣產出
711 bytes 的驅動初始化)。而且改 ROM 之後錄到的東西嚴格說不是原版行為。

**headless 環境用 GDB remote stub**:`blastem ROM -D` 直接在 stdio 上講
GDB RSP,不需要終端機(原生除錯器 `-d` 靠 termhelper 開終端機視窗,
容器裡會靜默地不進除錯器)。流程:

	?                     → S05,停在進入點
	Z0,<vblank>,2         → 在每幀都會經過的地方下中斷點
	c → 命中 → M <addr>,4:<value> → 重複數十幀
	m <addr>,4            → 趁還停著驗證真的切過去了
	z0,<vblank>,2 → $c#63 → 放行,這時才送錄音熱鍵

四個會靜默失敗的地方:第一次 `cont` 要等 8 秒以上(開機),逾時設太短會誤判;
放行要送**合法封包** `$c#63` 不能寫裸的 `c` 位元組;stub 不回應 raw `0x03`
非同步中斷,送了會卡死,所以驗證只能在放行前做;停在中斷點時模擬器不處理
視窗事件,熱鍵送不進去。

### 有些遊戲的曲目是「上傳資料」不是「傳編號」

MM2 屬於這一類：68k 每次換曲都把 1 KB 的曲目資料搬進 Z80 RAM，
命令位元組只說「播放你手上那份」。**這種的觸發點是資料指標不是編號**，
要找的是那張曲目指標表，或直接呼叫 68k 那支「開始播放」的常式。

判斷方法：看命令那一段前面有沒有 `bsr` 到一支會 `move.w #$3FF,d0` ＋
搬資料到 `$A0xxxx` 的常式。有 → 屬於這一類。

### 找不到呼叫者時：先做正對照

音樂驅動常常是**連結進來的函式庫**，它的 API 入口在 ROM 裡可能一個 xref 都沒有
（IDA 連函式都不會建）。要下「沒有人呼叫它」這個結論之前，
**拿同一個掃描器去掃一支已知被呼叫的函式**。

MM2 本機實測：五個入口全 0 筆；同一支掃描器對 `sub_AF296`／`sub_AF2C0`
各掃出 4 筆，與 IDA 的 xref 完全相同 —— 正對照通過，零命中才是真的。
沒有這一步的話，「掃描器有洞」與「真的沒有」長得一模一樣。

68000 的呼叫形式要**全部**掃到，漏一種就會有假零：

	bsr.s      0x6X XX          （8-bit 位移）
	bsr.w      0x6100 + 16-bit
	jsr (d16,pc) 0x4EBA + 16-bit
	jsr abs.l    0x4EB9 + 32-bit  ← 等同「ROM 裡有這個位址的 4 bytes」
	jmp abs.l 表  0x4EF9 + 32-bit  ← 跳表／thunk

## 3. 記錄：BlastEm 是唯一實用選項，但它沒有 CLI

- **0.6.2 正式版錄不了 VGM，要 0.6.3 以上的 nightly。**（vgmrips wiki）
- 開關是**熱鍵 `m`**，按一次開、再按一次關。**沒有命令列旗標，也沒有 headless 模式。**
- 輸出位置在 `default.cfg`：`vgm_path $EXEDIR`、`vgm_template $ROMNAME/%Y%m%d_%H%M%S.vgm`。
- **[HARD] 關掉模擬器之前一定要再按一次 `m` 收尾。** 直接關會讓 VGM 的
  EOF offset 沒寫進去，而且 `vgm_ptch` 修不回來 —— 那份錄音就廢了。
- ROM 檔名太長或含非 ASCII 會讓建檔失敗。**容器裡一律把 ROM 複製成短的 ASCII 檔名。**

因為只有熱鍵，headless 化就是 **Xvfb ＋ xdotool** —— 與跑 DOSBox 當 oracle
完全同一套：起 `Xvfb :99`、跑模擬器、`xdotool key m`、等、`xdotool key m`、
再關。時間軸要寫成參數，不要寫死在腳本裡。

### [HARD] 不要寫自己的 `blastem.cfg`

**使用者設定檔是整份取代內建的 `default.cfg`，不是合併。** 只為了設 `vgm_path`
寫兩行進 `~/.config/blastem/blastem.cfg`，會把整個 `bindings` 區塊一起蓋掉，
於是 `m ui.vgm_log` 沒有綁定了。**症狀是模擬器正常跑、截圖正常、就是不產生 VGM**
—— 與「這個版本不支援 VGM」長得一模一樣，很容易誤判成版本問題再去換 nightly。

內建預設本來就是 `vgm_path $HOME`，所以**把 `HOME` 指到可寫目錄就夠了**，
不必碰設定檔。真的要改設定時，複製 `default.cfg` 再改，不要只寫要改的那幾行。

### 容器內的三個權限與相依坑（本機實測）

- **`WORKDIR` 建的目錄是 root 的**，容器以 `-u $(id -u)` 跑就寫不進去。
  症狀 `cp: cannot create regular file ...: Permission denied`，看起來像 ROM
  掛載錯了。`RUN mkdir -p /work /tmp/.X11-unix && chmod 1777` 一次解決兩個
  （非 root 的 Xvfb 也建不出 `/tmp/.X11-unix`）。
- **少了字型 BlastEm 會在啟動後隨即結束。** 它用 `fc-match` 找預設字型畫自己的
  選單，找不到就印 `Failed to find default font path` 然後退出 —— 看起來像 ROM
  載入失敗。`fontconfig` 與 `fonts-dejavu-core` **兩個都要**。
- **沒有音效裝置時要 `SDL_AUDIODRIVER=dummy`**，否則 SDL 初始化直接失敗。
  VGM 記錄取的是晶片模擬的暫存器寫入，不是輸出裝置的取樣，所以 dummy 不影響內容。
  Xvfb 沒有硬體 GL，另外要 `LIBGL_ALWAYS_SOFTWARE=1`。

### 替代路線（BlastEm 的熱鍵太脆時再考慮）

**MAME 的 VGM mod**（vgmrips wiki 有頁面）。MAME 本體可以
`-video none -sound none` 真 headless，而且有 Lua（`-autoboot_script`）
可以腳本化「跑到第 N 幀 → 寫記憶體 → 開始記錄」。代價是要自己維護一份
patched MAME，且 MD 驅動的時脈精準度不如 BlastEm。

**先試 BlastEm；它的音訊精準度是社群公認基準，而 VGM 要的就是精準的暫存器時序。**

## 4. 轉檔：VGM → WAV

VGM 存的是「第 N 個取樣點對哪個晶片的哪個暫存器寫了什麼」，
所以轉檔＝重跑一次晶片模擬。用 ValleyBell 的
[libvgm](https://github.com/ValleyBell/libvgm) 的 `vgm2wav`（cmake 自己編，
Debian 沒有套件）。同一條工具鏈要**釘死版本**，因為換晶片模擬版本會換音色。

	cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
	      -DBUILD_TESTS=OFF -DBUILD_PLAYER=OFF -DBUILD_VGM2WAV=ON
	cmake --build build --target vgm2wav      # 產物在 build/bin/vgm2wav
	vgm2wav --samplerate 48000 --loops 1 in.vgm out.wav

### [HARD] `vgm2wav` 的輸出不是標準 PCM WAV

它寫的是 **WAVE_FORMAT_EXTENSIBLE**（格式碼 `0xFFFE`、`fmt` 區塊 40 bytes）。
取樣資料本身就是 16-bit LE PCM，但很多解碼器只認格式碼 1：

- Python 的 `wave`：`unknown format: 65534`
- Ebiten 的 `audio/wav`：`wav: format must be linear PCM`

**症狀最惡劣的地方是檔案聽起來完全正常** —— 播放器打得開、波形也對，
所以會被誤判成下游程式的 bug。修法是只重寫檔頭（44 bytes 標準檔頭 ＋ 原封不動的
`data` 區塊），一個取樣點都不用動。真正的格式碼藏在 EXTENSIBLE 的 SubFormat GUID
前兩個位元組，要讀那裡確認是 PCM(1) 不是浮點(3)，浮點只改檔頭騙不過去。

## 5. 每首要保存的中介資料

擷取要能被重跑驗證，光有 WAV 不夠：

	ROM 檔名 + SHA-256
	模擬器名稱 + 版本（nightly 要記 commit）
	觸發步驟（記憶體位址與值，或按鍵時間軸）
	VGM 的 SHA-256、WAV 的 SHA-256
	取樣率、聲道數、位元深度
	錄製長度與循環點

沒有觸發步驟的擷取＝下一輪要重猜；沒有雜湊＝無法判斷重跑有沒有漂移。

## 6. 權利邊界

ROM、VGM、WAV 都是原版衍生物，**不進版控、不進公開釋出包**。
公開的只能是「怎麼從自己合法持有的 ROM 產生這些檔案」的腳本與說明。
網路曲庫（vgmrips、bandcamp 原聲帶）可以當**交叉參考**核對曲目數與曲名，
**不能下載來冒充自己的可重現輸出** —— 那會讓整條擷取鏈失去意義，
而且授權狀態不同。

## 7. 已知的坑（照順序踩過的）

- **只掃 `($A0xxxx).l` 的直接寫入** → 兩筆，看起來像沒有驅動。要追 `a0` 基底。
- **對零 xref 直接下「沒人呼叫」** → 先做正對照，否則掃描器的洞會冒充事實。
- **拿 0.6.2 試很久** → 那個版本根本沒有這個功能，症狀是按 `m` 完全沒反應。
- **為了設 `vgm_path` 寫了部分設定檔** → 整份 bindings 被蓋掉，`m` 失去綁定，
  症狀與「版本不支援」完全相同。
- **錄完直接關視窗** → VGM 的 EOF offset 沒寫，檔案救不回來。
- **把 `vgm2wav` 的輸出直接餵給遊戲引擎** → EXTENSIBLE 格式被拒，而檔案聽起來正常。
- **用「錄一長段再切」代替逐首觸發** → 不可重現，切點與循環點全靠手工。

## 8. 驗收：每一段都要有獨立的量測面

一條鏈四個環節，每一段都會「看起來成功」但實際沒動。本機實測用的判準：

| 環節 | 判準 |
|---|---|
| 模擬器真的在跑遊戲 | 截圖看得到遊戲畫面，不是黑畫面或選單 |
| VGM 是真的 | magic `Vgm `、YM2612 7670453 Hz／SN76489 3579545 Hz（NTSC MD）、**總取樣數換算的秒數等於 timeline 給的秒數** |
| VGM 有內容 | 統計 `0x52`／`0x53`（YM2612 兩個埠）與 `0x50`（SN76489）的寫入筆數，不能是 0 |
| WAV 不是靜音 | 峰值與 RMS，而且**分段算 RMS** —— 只錄到片頭的話後段會是 0 |
| 下游吃得下 | 拿**目標程式自己的解碼器**跑一次，不要用別的播放器代替 |

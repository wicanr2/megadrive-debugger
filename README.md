# megadrive-debugger

Mega Drive／Genesis ROM 的逆向與**動態除錯**工具組，外加一個給 AI coding agent
用的角色定義。全程 docker，不需要在主機裝任何東西。

核心是一件事：**讓「執行時實際發生什麼」變成可以重跑的證據**，
而不是靠猜或靠人耳。

## 為什麼需要動態

靜態反組譯能回答「這段碼在什麼條件下執行」，回答不了
「玩家實際走到旅店的時候跑的是哪一支」。老遊戲的跨模組呼叫常常走 thunk 表，
文字常常沒有指標表，於是靜態掃描很快就到頂：

- 某個分派函式有 39 個呼叫端，其中 **28 個走 thunk** —— 只掃直接呼叫會漏掉七成
- 全 ROM **沒有字串指標表**，多數印字是「先格式化進 RAM 緩衝區再印緩衝區」

這時候唯一的辦法是把遊戲跑起來，在關鍵位置下中斷點，記錄
「這一次是誰呼叫的、參數是什麼」。

## 內容

	agents/megadrive-debugger.md   給 AI coding agent 的角色定義
	docker/                        固定版 BlastEm ＋ libvgm 的環境
	  Dockerfile                   BlastEm 0.6.3-pre ＋ libvgm 的 vgm2wav
	  rsp.py                       BlastEm GDB remote stub 的客戶端
	  md_trace.py                  下中斷點、送按鍵、記錄命中
	  music_dump.py                逐首擷取配樂（GDB stub 指定曲目，不改 ROM）
	  vgm2pcmwav.py                把 vgm2wav 的輸出正規化成標準 PCM WAV
	  entrypoint.sh                timeline：送鍵、錄 VGM、截圖
	tools/                         靜態分析（不需要模擬器）
	  mdlzss.py                    LZSS 解壓（4096 環形緩衝、初值 0x20）
	  mdlzss_scan.py               全 ROM 掃壓縮區塊，不靠任何前綴
	  mdlzss_render.py             把 tile 區塊畫成 PNG
	  mdtiles.py                   調色盤辨識與 4bpp tile 繪製
	  mdview.py                    第一人稱視角貼圖（點陣圖不是 tile）
	docs/                          方法論與案例

## 快速開始

```bash
docker build -t megadrive-debugger docker/

# 靜態：全 ROM 掃壓縮區塊
docker run --rm --network none -u "$(id -u):$(id -g)" \
  -v "$PWD:/w" -w /w megadrive-debugger \
  python3 tools/mdlzss_scan.py your.md

# 動態：在某個函式下中斷點，看誰呼叫它、參數是什麼
docker run --rm --network none -u "$(id -u):$(id -g)" \
  -e HOME=/work/home -e SDL_AUDIODRIVER=dummy --entrypoint sh \
  -v "$PWD:/w" megadrive-debugger -c '
    mkdir -p /work/home
    Xvfb :99 -screen 0 640x480x24 -nolisten tcp & sleep 1
    export DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1
    cp /w/your.md /work/rom.md
    python3 -u /usr/local/bin/md-trace /work/rom.md \
      --break 0x73FC:印字 --arg-str 0 --max-hits 20'
```

ROM 要自己準備。**這個 repo 不含任何遊戲資產**，也不要把 ROM、VGM、WAV
提交進來。

## 五個會靜默失敗的地方

每一個都實際踩過，症狀都長得像「沒找到」而不是「壞了」：

1. **第一次 `cont()` 要等 8 秒以上**（開機到第一個中斷點）。
   逾時設 5 秒會在第一次就放棄，看起來像中斷點沒命中。
2. **放行要送合法封包 `$c#63`**，寫裸的 `c` 位元組會被 stub 忽略，
   模擬器一直停著，症狀是「什麼都沒發生」。
3. **stub 不回應 raw `0x03` 非同步中斷** —— 送了會永遠等不到回覆。
   放行之後就再也停不下來，只能等下一個中斷點命中。
   **要讀的狀態都要在放行前讀完。**
4. **按鍵在停著的時候送。** 模擬器當下不處理視窗事件，但 X 會排隊，
   續跑之後才處理。反過來「為了送鍵而先放行」會踩到第 3 條。
5. **BlastEm 的原生除錯器 `-d` 在容器裡不能用** —— 它靠 `termhelper`
   另開終端機視窗，headless 環境會**靜默地**不進除錯器。一律用 `-D`。

## 兩條鐵則

**[HARD] 不要改 ROM。** 商業卡帶可能有開機完整性檢查：實測某片改動任何一個
位元組（尾端 padding 除外）就開不了機，畫面全黑，而 VGM 照樣產出 711 bytes 的
驅動初始化 —— 只看「有沒有檔案」會誤判成「錄到了但很短」。
要確認是不是防竄改，**改一個字串裡的字母**再開機：純文字位元組不可能讓遊戲
當掉，掛了就是防竄改。要改變執行時狀態就用 `M` 封包寫記憶體。

**[HARD] 零命中之前先做正對照。** 拿同一組設定去測一個已知會命中的目標。
但正對照只證明「你測的那一種形式」找得到，不證明你測完了 ——
實際踩過的例子：掃了 `move.l d0,X`／`d1`／`a0`／`#imm` 就是沒掃
`move.l (sp)+,X`，於是得出「沒有人寫這個變數」，而真正的 18 個寫入端
全部是 `(sp)+` 形式，正對照當時還是通過的。

## 文件

	docs/01-architecture-and-tables.md   68k/Z80 分工、音樂的兩種家族、表與分派的四種形式
	docs/02-vgm-music-extraction.md      VGM→WAV 工具鏈、headless 化、要保存的中介資料
	docs/03-dynamic-tracing.md           GDB stub 的實務：中斷點、讀寫記憶體、送按鍵
	docs/04-case-study.md                完整案例：從「這片怎麼播音樂」到 16 個角色全部定出來

## 授權與邊界

工具與文件採 MIT。只做靜態分析、格式保存與互通性研究；
不協助破解 DRM、繞過授權或修改付費驗證。ROM 與從 ROM 產生的音檔、圖檔
都是原版衍生物，自己留著，不要散布。

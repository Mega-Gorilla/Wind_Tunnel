# GPIO17 定常Low高速測定・統合結果（2026-09-10）

## 結論

現配線（GPIO17、C2印字103＝公称10 nF）のまま測定を完了した。定常Lowの保存高速波形は0.52-0.64 Vで、0.9 V超の変動を確認できなかった。一方、IRQ要求なしのPython/CによるGPLEV0読取りでは多数の変化を再現した。GPIO入力・読出し異常の原因は未確定。外部ノイズの不存在やPi故障を証明したものではない。

## 採用した追加試験

測定フォルダー：`measurements/simultaneous_20260910_`＋下記ID。

| ID | 入力／OSC | OSC保存波形 | Python約0.25秒 | C変化数／時間 |
|---|---|---|---:|---|
| 174904 | DC Low、100 MS/s | 50 µs、0.52-0.64 V | 172 | 8192上限／202.44 ms |
| 175002 | DC Low、500 kS/s | 10 ms、0.52-0.64 V | 176 | 8192上限／207.79 ms |
| 175512 | 50 Hz、100 MS/s | 50 µs、0.50-2.60 V、立上り取得 | 125 | 5207／250.00 ms |

- Low：ON後0.4秒待ち、25 kS/s定常基準波形を確認して高速RISE・0.9 V・ONCEを設定。約1秒の待受けで自然トリガーなし。AUTOへ切替え、スナップショットを保存した。
- 50 Hz：同じ高速トリガー経路で自然立上りを取得。50 µsではRCの立上り途中までで、2.60 VはHigh定常値ではない。
- 波形取得完了がWF OFF指令より前であることをPCログで照合。OSCとPiのハードウェア同期はなく、同一瞬間の異常を対応付けた結果ではない。
- Python/Cの取得前後のREN/FEN/HEN/LEN/AREN/AFEN対象bitは0。今回はON中のカーネルイベント要求を省略。
- 各試験のOFF前後約3秒は0イベント。最終WF CH1/CH2 OFF、CH1はSQU/50 Hz/2.4 Vpp/+1.5 V/High-Z。GPIO17入力、GPIO18 High。共有PADS0x1Bは読取りのみ。起動設定、配線、容量、GPIO18を変更していない。
- ファンは切断中という最新申告を前提としており、ファン回転・実RPMは測定していない。

## 不採用試行

174623、174755は単発DC取得の強制トリガーが待ちを解除せず、親側の時間上限でOFFにした。scope_summaryだけにはcompletedが残るが、run_logはerrorであり、正常完了試験として扱わない。主報告の数値・波形比較から除外した。原ログは保存。

## 過去結果の訂正と次の判断

- 103交換以前の追加後試験は、実装が104＝100 nFだった。訂正台帳 `measurements/capacitance_corrections.json` を適用する。
- GPIO27での再現は104条件。GPIO27＋103は未測定。
- 次の優先試験：発振器を切り離し、R3の信号源側をPi GNDへ接続する静的Low対照。R4との分圧でGPIO点は概算0.30 Vになる。電源OFFでの配線変更が必要なため今回未実施。
- 生イベントによる回転数フィードバックは検証完了まで保留。候補は安定時間デバウンス、RC＋3.3 Vシュミット入力、Pico等の別マイコン計数とUSB数値転送。効果は今後検証する。

## 成果物・再生成

- 最新PDF：`Docs/tests/gpio-legacy/WindTunnel_GPIO_Investigation_2026-09-10.pdf`（6ページ・日本語2段組）
- 生成：`Electronics/build_gpio_investigation_consolidated.py`
- 実行引数：`simultaneous_20260910_174904 simultaneous_20260910_175002 simultaneous_20260910_175512`
- 集計：`Docs/tests/gpio-legacy/figures/gpio_consolidated/summary.json`
- 原データ：各試験の `run_log.json`、`scope/scope_summary.json`、`scope/waveforms.npz`、`settled_level_poll.json`、`settled_native_poll.json`。
- 今回はユーザー指定に従い印刷しない。

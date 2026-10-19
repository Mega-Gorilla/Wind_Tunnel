# GPIO17：定常50 Hz・DC Low/High試験（2026-09-08）

## 現在の状態

- 最新のユーザー申告：ファン自体が切断されている。
- WF1974 CH1 → R3 1 kΩ → GPIO17（物理11番）、R4 10 kΩで3.3 Vプルアップ、GND共通。OSC CH1はGPIO17、×1、DC。
- 試験は既知信号入力系を対象とし、ファン回転・停止の実動作は確認していない。
- GPIO18は出力High（反転回路の停止側設定）を維持。Piの起動設定、共有PADS、配線は変更していない。
- 最後の照会：WF CH1/CH2 OFF。CH1 SQU、50 Hz、2.4 Vpp、+1.5 Vへ復帰。

## 結果

測定フォルダ接頭辞：`measurements/simultaneous_20260908_`

| ID | フォルダ末尾 | 条件 | Pythonレベル変化/約0.25秒 | Pi保存イベント | GPIO17 IRQ増分 |
|---|---|---|---:|---:|---:|
| S1 | 210040 | 定常50 Hz | 405 | 251・上限中断 | 2428 |
| S2 | 210159 | 定常50 Hz | 351 | 251・上限中断 | 2479 |
| L1 | 210725 | DC 0.3 V設定 | 800 | 251・上限中断 | 3308 |
| H1 | 210809 | DC 2.7 V設定 | 0 | 0・約0.505秒完了 | 0 |
| L2 | 210955 | DC Low + C読取り | 826 | 251・上限中断 | 3361 |
| H2 | 211202 | DC High + C読取り | 0 | 0・約0.504秒完了 | 0 |

OSC：100 kS/s連続取得。DC Low定常窓は中央値0.58 V、最小0.42 V、最大0.88 V。DC Highは中央値2.74 V、最小2.50 V、最大2.96 V。OSC窓とPiの各取得窓は精密同期していない。10 µs未満の変動を排除した結果ではない。

Cによるread-only volatile uint32_t GPLEV0読取り（dmb sy前後、逆アセンブルで32 bit ldr確認）：

- L2：52.393721 ms、404605読取り、High4096、8192変化で上限終了。
- H2：250.000208 ms、1982973読取り、すべてHigh、変化0。
- Python/CともREN/FEN/HEN/LEN/AREN/AFEN bit17は前後全0。取得は非等間隔で、物理波形・校正済み周波数ではない。
- 全試験のOFF前後約3秒カーネル取得で0イベント。PADSは0x1BでHYST有効。

## 結論と限界

従来のPythonコールバックだけ、IRQ処理だけ、出力開始の過渡だけでは全結果を説明できない。一定Lowのレベル読取りで異常が現れる。一方、外部の短い電気的変動とPi入力・レジスタ読出し経路の異常をまだ区別できていない。GPIO17故障、64 bitカーネル原因は未確定。フィードバックへの採用は保留。

次の判別力が高い試験：出力安定後のDC Lowを高速トリガ捕捉。現配線で可能だが今回未実施。別GPIO対照は配線変更、別OS/カーネル対照は環境変更が必要。

## 成果物

- PDF：`Docs/archive/gpio-legacy/WindTunnel_GPIO17_Investigation_2026-09-08_Rev6.pdf`
- 解析：`Electronics/analyze_gpio17_settled.py`
- PDF生成：`Electronics/build_gpio17_report_rev6.py`
- データ：各フォルダの`settled_analysis.json`、`scope/waveforms.npz`、イベントCSV、レベルJSON、run_log。
- 機器アクセスを伴わず再生成可能。レポートは7ページ・日本語2段組。OSC/Pi LEVEL/Pi EVENT/Pi IRQを区別し、過去の5 V電源・プローブ問題は記載していない。

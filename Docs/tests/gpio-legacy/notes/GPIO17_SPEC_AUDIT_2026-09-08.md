# GPIO17仕様・起動設定の監査

2026-09-08。GPIO17の外部配線を切り離した状態で、仕様調査とread-only SSH確認のみ実施。設定変更、発振器通信、ファン操作なし。正式PDF未更新。

## 追加のユーザーテスター結果

依頼順と会話の解釈に基づく値（手動測定、機種・確度・抵抗実測値不明）：

| 状態 | R4供給側 | R4の元GPIO17側 |
|---|---:|---:|
| GPIO17とCH1を接続 | 3.296 V | 2.702 V |
| CH1先端のみ切り離し | 3.296 V | 2.718 V |
| GPIO17も切り離し | 3.295 Vと報告された点 | 3.281 V |

最後の測定は、Pi本体の裸ピンではなく外した配線のR4側として会話上解釈した。点名称に再度疑義が生じる場合は再確認する。

## 18:00 JSTのSSH読取

生ログ：`gpio17_config_20260908_180031.json`。実機はRaspberry Pi 3 Model B Plus Rev 1.3、6.18.34+rpt-rpi-v8。pinctrlでbcm2835互換コントローラを検出。GPIO17はinput Low、GPIO18はoutput High。gpioinfoはGPIO17 input（consumer表示なし）。読み取ったconfig.txtにGPIO17の明示設定はなく、GPIO18の停止設定のみ。停止サービスもGPIO18のみ設定していた。他の全プロセスの過去の書込みまで否定したわけではない。

## 公式仕様と重要な訂正

1. BCM2837系GPIO：内部プルアップ／プルダウン50～65 kΩ、入力漏れ最大5 µA（85℃）、Low最大0.9 V、High最小1.6 V（ヒステリシス有効条件）。2.7 V自体をHigh保証外や故障証拠として扱ってはならない。
   https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#voltage-specifications
2. 公式firmwareのdt-blob.dts、pins_3bplusのpin@defaultはinput/pull_down、GPIO17の個別上書きなし。起動後の実状態を保証するものではないが、既定プルダウンが残る仮説を支持する。
   https://github.com/raspberrypi/firmware/blob/master/extra/dt-blob.dts
3. この世代のpinctrl実装bcm2835_gpio_get_pullはwrite-only機構としてPULL_MAXを返し、表示名は「--」。プルなしは別値pnである。「--」から無効状態を証明できず、読み取りだけで現在の内部プル状態を確定できるとする説明は訂正する。
   https://github.com/raspberrypi/utils/blob/master/pinctrl/gpiochip_bcm2835.c
   https://github.com/raspberrypi/utils/blob/master/pinctrl/gpiolib.c
4. 既存試験コードはBias.AS_ISを指定していた。これは内部プル無効化ではなく既存条件を維持する指定。従来試験で入力や検出ビットを確認しても、内部プル無効を確認したことにはならない。

## 数値比較と限界

供給3.296 V、公称外付け10 kΩ、内部プルダウン50～65 kΩなら分圧は約2.747～2.857 V。実測2.718 Vから単純に逆算した等価負荷は約47.02 kΩで、公式下限50 kΩと厳密には一致しない。抵抗実値、入力漏れ、テスター負荷等が未分離であり、数値だけで内部プルダウンとは断定しない。ただし同程度の抵抗負荷を持つ既定プルダウンは優先して検証すべき仮説である。

内部プルの影響はDC電圧低下の説明候補であり、過去の大量イベントまで説明したことにはならない。GPIO故障・カーネル不具合の確定もしない。

## 次に必要な試験（未実施）

外付けR4をGPIO17へ戻し、発振器／ファンTachは外したまま、まず現在条件の電圧を測る。その後、明示的にGPIO17をinput/pull-noneへ設定し、再起動せず同じ点の電圧を比較する。コマンド候補は `pinctrl set 17 ip pn`（実機の権限によりsudo）。これは設定変更であり今回の仕様調査では実行しない。`pinctrl get`表示ではなく電圧応答で評価する。恒久設定は因果関係の確認後に検討し、設定後すぐの再起動で条件が戻らないよう測定順に注意する。

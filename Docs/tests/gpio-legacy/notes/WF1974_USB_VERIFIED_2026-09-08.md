# WF1974 USB通信確認（ドライバー導入後）

2026-09-08 16:09 JST。ユーザーによるNI-VISAインストール完了後に確認。

## 結果

- Windows: USB Test and Measurement Device (IVI)、Status OK、ProblemCode 0。
- USB InstanceId: `USB\VID_0D4A&PID_000E\9184397`。
- ドライバー: `oem235.inf`、サービス: `Usbtmc`。
- OWON VDS1022もStatus OK、既存libusb-win32ドライバーを維持。
- PyVISA 1.16.2から機器情報と設定値の問い合わせに成功。
- VISA resource: `USB0::0x0D4A::0x000E::9184397::INSTR`。
- 識別応答: `NF Corporation,WF1974,9184397,Ver2.30`。

| 読み取り項目 | 現在値 |
|---|---|
| CH1 / CH2出力 | 両方OFF（取得開始・終了時に確認） |
| チャンネルモード | IND（独立） |
| CH1負荷表示設定 | INF（High-Z） |
| CH1周波数 | 10,500 Hz |
| CH1振幅 | 5.000 Vpp |
| CH1 DCオフセット | 0 V |

現在の振幅・オフセットはGPIO17の0～3.3 V入力試験に不適切。例えばゼロ中心の対称波なら±2.5 Vとなるため、この設定のまま出力ONにしない。波形種類は今回未照会。設定値の取得は実端子電圧の測定ではない。

## 実施範囲と次の段階

この確認では問い合わせのみ。出力ON、設定変更、初期化、ファームウェア更新、PC/Pi再起動は実施していない。

次は出力OFFのままGPIO17への信号経路を切り離し、発振器側をオシロスコープで確認できる配線にする。High-Z・矩形波50 Hz・50% duty・3.0 Vpp・DCオフセット+1.5 V（目標0～3.0 V）を設定して実電圧と過渡応答を確認後、出力OFFでGPIO17へ再接続する。GPIO17接続中の出力試験はこの確認では実施していない。

読み取り専用スクリプト: `hardware/wf1974_readonly.py`。
通信記録: `measurements/wf1974_usb_readonly_20260908_160941.json`。
初回スクリプトの接続管理エラー記録は `wf1974_usb_readonly_20260908_160917.json`。機器コマンド送信前のPythonエラーであり、修正後は全問い合わせに成功した。

コマンド仕様: [NF WF1973/WF1974外部制御マニュアル](https://www.nfcorp.co.jp/files/WF1973_74_InstructionManual_ExternalControl_En.pdf)。

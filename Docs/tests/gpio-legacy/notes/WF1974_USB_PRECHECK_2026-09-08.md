# WF1974 USB接続後の事前確認

2026-09-08 15:26 JST頃。ユーザーからUSB接続・試験配線完了の報告を受け、読み取り確認を実施した。

## USB

- Windows PnPで `WF1974` を検出。
- InstanceId: `USB\VID_0D4A&PID_000E\9184397`。
- Status: Error、ProblemCode: **28**。
- DriverInfPathおよびServiceは空。USB機器は列挙されたがドライバが関連付いていない。
- 標準的なVISA DLL・レジストリ・インストールフォルダーの確認範囲では既存VISA環境を見つけられなかった。使用中のPythonにPyVISAも未導入。
- `*IDN?`等の通信はまだ実施できていない。発振器の出力状態・設定値はUSB経由で未確認。

## Piと電圧波形

- GPIO17: input / hi。変更せず。
- GPIO18: output / hi。停止指令を維持。
- `windtunnel-fan-stop.service`: active。
- CH1が接続図どおりGPIO17側にあるとの前提で、オシロをDC・×1・25 kS/s・5,000点で3回取得。
- 各200 msの記録で平均2.661-2.665 V、全記録の瞬時範囲2.460-2.860 V。
- Lowへの遷移・矩形波は記録されていない。発振器出力OFF、高インピーダンス、DC設定等のどれによる状態かはこの測定だけでは断定しない。
- 測定フォルダー: `tach_retest_20260908_152608_wf1974_connected_readonly`。
- 既存取得スクリプトの名称・JSONにTachの項目があるが、本試験は発振器接続ノードの電圧確認であり、RPM評価はしていない。

## 次の作業

NFのUSB-TMC導入手順に沿ってVISAドライバ（NI-VISA等）を導入し、USB認識と識別問い合わせから再確認する。管理者権限を使うホストへのドライバ導入は未実施。発振器の出力ON・振幅変更・初期化・Pi再起動も行っていない。

根拠：

- [Microsoft Code 28](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/cm-prob-failed-install)：ドライバ未インストールを示す。
- [NF USBTMC導入手順](https://www.nfcorp.co.jp/files/WF1973_74_USBTMC_InstructionManual_En.pdf)：事前のVISAドライバ導入。
- [NI-VISA USB機器の設定](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA03q000000x1qzCAA&l=en-US)：USBTMC機器の認識手順。

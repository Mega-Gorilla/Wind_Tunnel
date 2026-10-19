# WindTunnel 回路CAD導入・作図方針

調査日: 2026-09-06

導入結果: KiCad 10.0.6を現在のWindowsユーザー向けにインストール済み。
保存先の例: `%LOCALAPPDATA%\Programs\KiCad\10.0`（インストール方式により異なる）。
起動: WindowsスタートメニューのKiCad。

確認結果: CLIバージョン表示、PDF/ERCヘルプ、標準シンボルの存在を確認。付属のsallen_key回路図を実際にSVGへ書き出し、終了コード0と生成ファイルを確認済み（`Docs/tests/mechanical/cad-verification/sallen_key.svg`）。

初回の制限環境内でのCLI起動時に設定フォルダーへのアクセス拒否が発生し、実行を中断した。その後ユーザーからメモリ参照エラーのダイアログ2件の報告あり。設定フォルダーの作成を許可した再実行とサンプル書き出しは正常終了。メモリエラーとの因果関係は未確定。GUIエディターの対話操作は未検証。

## 選定

KiCad（Windows版）を使用する。無料の回路・基板設計ソフトで、編集可能な回路図、電気的ルールチェック（ERC）、PDF/SVG、部品表・ネットリスト出力に対応する。Raspberry Piへのインストールは不要。

公式配布: https://www.kicad.org/download/windows/
CLI資料: https://docs.kicad.org/10.0/en/cli/cli.html

導入コマンド（今回選定した安定版）:

```powershell
winget install --id KiCad.KiCad --exact --version 10.0.6 --source winget --silent --accept-source-agreements --accept-package-agreements --disable-interactivity
```

GUIから導入する場合は、公式ページのWindows x64安定版インストーラーを実行し、回路シンボルなど標準ライブラリを含めてインストールする。

## 作図方法

1. 各モジュールの品番・端子配列・実配線を照合する。
2. KiCadプロジェクトに回路図を作成する。標準部品は標準シンボル、モジュールは端子を明示した専用シンボルまたはコネクタとして表す。
3. 電源、Raspberry Pi、ファン制御、センサーを機能別に配置し、コネクタ端子番号・GPIOのBCM番号と物理ピン番号を併記する。
4. ERCとネットリストで意図した接続を確認し、PDFを目視確認する。ERCだけで実配線や部品の安全性まで保証されるわけではない。
5. 編集用 `.kicad_pro` / `.kicad_sch`、必要な独自ライブラリ、閲覧用PDF、部品表、配線表をまとめる。

回路図ファイルはテキスト形式で作成・編集でき、KiCad CLIで読み込み、ERC、PDF/SVG出力を検証できる。CLI単独で自動配線・回路設計を行うわけではない。基板製造用レイアウトは別工程。

## 現時点で図面へ反映する構成

- 外部12 V安定化電源 → ARCTIC P14 Pro PST。
- 外部12 V → DFR0205 → 調整済み5 V → micro-USB → Raspberry Pi 3 Model B。
- BCM GPIO18（物理12）→ ベース抵抗 → C1815、コレクタ → ファンPWM、エミッタ → 共通GND。ベース–エミッタ間にプルダウン抵抗。
- ファンTach → BCM GPIO17（物理11）。3.3 Vプルアップと直列抵抗を含める。
- SDP810-125Pa差圧センサー、BME280基板、ほか購入済み基板。
- ファンPWM制御は25 kHz、C1815で反転。GPIO側High 100%がファン停止指令。

## 最終図面前に照合する点

- 使用電源がWX-DC2412（12 Vモデル）かJC-360-12か。
- Adafruit製品2点の正式品番、SDP810接続基板／ケーブルと実際の端子配列。
- C1815の製造元・端子配列、実装済み抵抗値（直近の案: ベース2.2 kΩ、B–E間10 kΩ、Tach直列1 kΩ、3.3 Vプルアップ10 kΩ）。案と実装を区別する。
- タッチパネルの製品と電源・信号の接続。
- センサーの電源電圧、I2C信号電圧とプルアップの接続先。

GPIO18のPWM段階試験は実施済み。GPIO17の回転数信号は異常なエッジを観測した段階で、正常な回転数計測は未確認。PWM初期状態では最大回転する可能性があるため、最大回転を一律に「安全側」とは扱わない。

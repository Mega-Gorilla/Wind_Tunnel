# Wind Tunnel

**株式会社ながれ技術研究所の「オープンソース風洞 / MyWindTunnel」の吸込型風洞をベースに開発しています。** 原設計と風洞本体のCADは、[公式のMyWindTunnelページ](https://nagare-giken.jp/mywindtunnel/)から取得してください。原設計の公開に感謝します。

このリポジトリは、独自の電子回路・制御ソフト・追加固定部品と、その検証資料をまとめたものです。**公式配布の風洞CADは同梱しません。** 本体を含む結合CADや、その形状を変換・抽出したデータも配布対象にしません。独自部品のCAD、回路図、測定結果・図・報告書は別の公開対象として扱います。

現行基板は **Pico Carrier Rev E**、制御ソフトは **0.3.0 実機有限運転版・タッチ操作対応**です。

## 原設計からの変更

- ファンをARCTIC P12 MaxからP14 Pro PSTへ変更。
- Raspberry Pi Picoによるセンサー接続・回転数取得・ファン制御と、独自のPico Carrier基板を追加。
- Raspberry Pi上のタッチUIと、遠隔モードON/OFF・許可IP・APIトークン認証を備えたAPIを追加。
- 画面・基板・電源を固定する独自の樹脂部品を設計。

これらの変更を含む装置の測定結果は、原設計の性能値と同一ではありません。公式サイトの名称に「オープンソース」を含むことから、CADの再配布許諾を独自に推定しないでください。[第三者資料の扱い](THIRD_PARTY_NOTICES.md)を参照してください。

## 目的から探す

| 目的 | 開く資料 |
|---|---|
| 文書・試験結果の一覧 | [Docs 索引](Docs/README.md) |
| 基板を組み立てる | [Rev E 組立ガイド](Docs/assembly/WindTunnel_Pico_Carrier_RevE_Assembly_Guide.pdf) |
| センサーを接続する | [ピン別接続ガイド](Docs/assembly/WindTunnel_RevE_Sensor_Pin_Guide.pdf) |
| 回路・基板を編集する | [Electronics 案内](Electronics/README.md) |
| 樹脂部品とフレームを組み立てる | [組付けマニュアル](Docs/assembly/Item_Holder_Assembly_Manual.pdf)・[独自CAD](Mechanical/README.md) |
| UIとAPIを使う・開発する | [制御ソフト](software/control/README.md)・[基本設計](Docs/software/control-software/README.md) |
| 固定板のCFD結果を見る | [論文形式PDF](Docs/tests/cfd/2026-10-19_fixed_plate_refined/WindTunnel_FixedPlate_CFD_Paper_2026-10-19.pdf)・[詳細とデータ](Docs/tests/cfd/2026-10-19_fixed_plate_refined/REPORT.md) |

CFDは未収束の予備結果で、校正値には使用できません。実装済みの機能と、風速校正・長時間評価などの未完了事項は各資料で区別します。

## 公開する内容

| フォルダー | 内容 |
|---|---|
| `Docs` | 組立手順、設計説明、試験報告、調査、部品表 |
| `Electronics` | 現行KiCad回路・PCB、製造データ、Pico FW、診断ソース |
| `Mechanical` | 独自のホルダー・電源支持部品・圧入テスト片の単体CAD |
| `software` | UI・API・配備用ソースとテスト |
| `measurements` | 個人情報を含む管理ログを除いた測定データ |
| `analysis` | 解析コード・設定・比較図。風洞形状、格子、計算場、実行環境は別途準備 |
| `tools/repository` | 公開範囲・秘密情報・リンク・KiCad依存ファイルの検査 |

接続設定、実機IP・ユーザーを含む管理記録、個人情報を含む旧記録、外部ツール、キャッシュは公開しません。ローカルに残る除外ファイルはcloneには含まれません。公開前の確認内容は[公開準備記録](Docs/maintenance/publication-review/README.md)にまとめます。

## 開発と安全

開発手順は [CONTRIBUTING](CONTRIBUTING.md)、Git管理方針と初回pushは [Gitセットアップ](Docs/operations/GIT_SETUP.md)を参照してください。新しい試験報告は `Docs/tests/<分野>/<日付と試験名>/` へ保存し、測定条件と生データへの参照を付けます。

模擬テストは実機接続なしで実施できます。実機運転・配線変更・FW書込みは対象と停止条件を確認して行います。ソフト停止は安全認証された非常停止ではありません。

本プロジェクト独自部分の公開ライセンスは未選定です。公開リポジトリであることと、任意の再利用を許諾することは異なります。第三者部分の既存のライセンス・著作権表記は維持します。

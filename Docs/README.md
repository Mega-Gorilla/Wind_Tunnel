# Wind Tunnel 文書索引

現在の装置を組み立て、操作し、測定結果を確認するための入口です。現行基板はPico Carrier Rev Eです。旧Pi GPIO直結回路や旧PCB版は現行の配線指示ではありません。

## 組立と配線

- [Rev E 基板の組立](assembly/WindTunnel_Pico_Carrier_RevE_Assembly_Guide.pdf)
- [実装後の外部配線](assembly/WindTunnel_Pico_Carrier_RevE_External_Wiring.pdf)
- [センサーのピン別接続](assembly/WindTunnel_RevE_Sensor_Pin_Guide.pdf)
- [Item Holderとフレームの組付け](assembly/Item_Holder_Assembly_Manual.pdf)
- [回路とPCB原本](../Electronics/README.md)・[機械CADと印刷部品](../Mechanical/README.md)

## 操作とソフトウェア

- [UIとAPIの使い方](../software/control/README.md)
- [Piへの配備と運用](../software/control/deploy/pi/README.md)
- [現在の基本設計と未実装の拡張](software/control-software/README.md)
- [GitとIssue運用の準備](operations/GIT_SETUP.md)・[開発手順](../CONTRIBUTING.md)
- [実機接続情報の管理](operations/SSH_SETUP.md) — 実接続メモはローカル専用でGit対象外
- [KiCad導入メモ](operations/CIRCUIT_CAD_SETUP.md)

## 試験結果

| 分野 | 優先して読む結果 | 状態 |
|---|---|---|
| CFD | [固定板CFD再評価 論文形式PDF 2026年10月19日](tests/cfd/2026-10-19_fixed_plate_refined/WindTunnel_FixedPlate_CFD_Paper_2026-10-19.pdf)・[詳細とデータ](tests/cfd/2026-10-19_fixed_plate_refined/REPORT.md) | 形状再現を改善。Linux比較実行済み。定量影響・校正は未確定 |
| センサーとファン | [全センサーと100%段階試験](tests/fan-sensors/2026-10-17/TEST_RESULT.txt) | 短時間動作試験。風速校正ではない |
| 回転数取得 | [Pico移行後の改善確認](tests/fan-sensors/2026-10-17/TACH_IMPROVEMENT_RESULT.txt) | 取得方式と確認範囲を区別 |
| UIとAPI | [Pico有限運転版](tests/software/pico-control/README.md)・[タッチ対応](tests/software/touch-ui/README.md) | 実装・受入検証の記録 |
| 旧GPIO問題 | [統合報告書](tests/gpio-legacy/WindTunnel_GPIO_Investigation_2026-09-10.pdf) | 旧構成の調査履歴。現行配線には使わない |

[試験結果の保存方針](tests/README.md)。生データは [measurements](../measurements)、CFDコード・設定の公開範囲は [analysis](../analysis) を参照してください。風洞形状・計算場・実行環境は別途準備が必要です。

## 調査と調達

- [市販機比較に基づくソフト開発優先順位 2026年10月19日](research/wind-tunnel-20261018/FEATURE_ROADMAP_2026-10-19.md) — 固定板の再設計を保留して進める機能と受入条件
- [市販風洞の測定機能・規格・モード調査](research/wind-tunnel-20261018/README.md)
- 公開UI画像の比較ギャラリー（ローカル保管・公開版には未同梱）
- [ピトー管固定治具のCADレビュー](research/wind-tunnel-20261018/pitot-fixture-review.md)
- [部品購入記録と発注資料](procurement/README.md)
- WF1974の外部制御マニュアル（ローカル保管・公開版には未同梱）

## 公開範囲と旧記録

[公開準備記録](maintenance/publication-review/README.md)に、個人情報監査と配布対象の判断を記します。公式の風洞CADは同梱せず、独自部品のみ公開します。

旧回路・個人情報を含む整理記録・注文や印刷の管理履歴はローカル保管です。旧資料の「現在」「未実装」は作成当時を示し、再配線や再発注の根拠にする前に現行資料を確認してください。

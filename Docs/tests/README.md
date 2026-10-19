# 試験結果の分類と保存

報告書・比較図・集計値はこのフォルダーへまとめます。実測と数値解析を混ぜず、実施日、装置構成、条件、測定主体、採否と限界を明示します。

最新のCFD評価は [2026年10月19日 固定板CFD再評価の論文形式PDF](cfd/2026-10-19_fixed_plate_refined/WindTunnel_FixedPlate_CFD_Paper_2026-10-19.pdf)（2段組み5ページ）。[詳細と解析データ](cfd/2026-10-19_fixed_plate_refined/REPORT.md)も保存しています。形状再現・計算環境の検証と、校正に採用できる精度の検証を区別しています。

| カテゴリー | 内容 |
|---|---|
| `cfd` | 数値解析。収束・格子依存性・モデル化条件を結果と一緒に保存 |
| `fan-sensors` | Picoとセンサー、PWMと回転数の実機動作確認 |
| `software` | 模擬試験、配備、Pico有限運転、タッチUIの受入記録と画面画像 |
| `mechanical` | CAD形状と干渉などの確認記録 |
| `gpio-legacy` | Pico移行前のPi GPIO直結方式の調査結果と波形比較 |

`software/pico-monitor` は旧停止専用版、`simulation-v0.1` は初期模擬版の記録です。現行の操作仕様は [制御ソフトREADME](../../software/control/README.md)、実装検証は [pico-control](software/pico-control/README.md) と [touch-ui](software/touch-ui/README.md) を優先します。旧記録は試験の出所を追うために保持しています。

新規保存先は `<カテゴリー>/YYYY-MM-DD_試験名/` とします。生データ・取得時のソースは [measurements](../../measurements)、CFDの再計算データは [analysis](../../analysis) に置き、報告からリンクします。過去のJSONに保存された旧パスやソースハッシュは測定時の証跡として書き換えません。

移動前後の対応は パス移動計画（ローカル保管・公開版には未同梱） にあります。CFDの「整合性確認合格」は、解の収束や物理的妥当性の確認とは別です。
